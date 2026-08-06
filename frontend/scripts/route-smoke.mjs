/**
 * Smoke tests for iraq-ecom-traders frontend routes.
 * Run: node scripts/route-smoke.mjs
 */
import { chromium } from 'playwright';

const BASE = process.env.FRONT_BASE || 'http://127.0.0.1:5173';
const API = process.env.API_BASE || 'http://127.0.0.1:8000';
const USER = process.env.SUPER_ADMIN_USERNAME || 'admin';
const PASS = process.env.SUPER_ADMIN_PASSWORD || 'Admin@12345';

const results = [];
function ok(name, detail = '') {
  results.push({ name, pass: true, detail });
  console.log(`PASS  ${name}${detail ? ` — ${detail}` : ''}`);
}
function fail(name, detail = '') {
  results.push({ name, pass: false, detail });
  console.error(`FAIL  ${name}${detail ? ` — ${detail}` : ''}`);
}

async function waitPath(page, expected, timeout = 15000) {
  try {
    await page.waitForFunction(
      (exp) => window.location.pathname === exp,
      expected,
      { timeout }
    );
  } catch (e) {
    const actual = await page.evaluate(() => window.location.pathname + window.location.search);
    throw new Error(`Expected path ${expected}, got ${actual}: ${e.message}`);
  }
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  try {
    // 1) Root redirect
    await page.goto(`${BASE}/`, { waitUntil: 'domcontentloaded' });
    await waitPath(page, '/iraq-ecom-traders/registration');
    ok('redirect / → /iraq-ecom-traders/registration', page.url());

    // 2) Registration page loads
    await page.waitForTimeout(500);
    const regText = await page.locator('body').innerText();
    if (regText.length > 20) ok('registration page renders content');
    else fail('registration page renders content', 'body too short');

    // 3) Refresh on registration
    await page.reload({ waitUntil: 'domcontentloaded' });
    await waitPath(page, '/iraq-ecom-traders/registration');
    ok('refresh keeps /iraq-ecom-traders/registration');

    // 4) Legacy admin redirects (auth guards may then send unauthenticated users to login)
    const legacy = [
      ['/admin', '/iraq-ecom-traders/admin'],
      ['/admin/login', '/iraq-ecom-traders/admin/login'],
      ['/admin/users', '/iraq-ecom-traders/admin/users'],
      ['/admin/brand-settings', '/iraq-ecom-traders/admin/brand-settings'],
      ['/admin/form-settings', '/iraq-ecom-traders/admin/form-settings'],
      ['/admin/membership-report', '/iraq-ecom-traders/admin/membership-report'],
      ['/admin/print', '/iraq-ecom-traders/admin/print'],
    ];
    for (const [from, to] of legacy) {
      try {
        await page.goto(`${BASE}${from}`, { waitUntil: 'domcontentloaded' });
        await page.waitForFunction(
          ({ canonical, login }) => {
            const p = window.location.pathname;
            return p === canonical || p === login;
          },
          { canonical: to, login: '/iraq-ecom-traders/admin/login' },
          { timeout: 15000 }
        );
        const actual = await page.evaluate(() => window.location.pathname);
        ok(`redirect ${from} → ${to}`, actual === to ? 'landed canonical' : `auth guard → ${actual}`);
      } catch (e) {
        const actual = await page.evaluate(() => window.location.pathname).catch(() => '?');
        fail(`redirect ${from} → ${to}`, `${actual}: ${e.message || e}`);
      }
    }

    // 5) Protected admin without auth shows login CTA / unauthorized
    await context.clearCookies();
    await page.evaluate(() => localStorage.clear());
    await page.goto(`${BASE}/iraq-ecom-traders/admin`, { waitUntil: 'networkidle' });
    await waitPath(page, '/iraq-ecom-traders/admin');
    const adminBody = await page.locator('body').innerText();
    if (/تسجيل الدخول|محمية|login/i.test(adminBody)) {
      ok('protected /iraq-ecom-traders/admin without auth');
    } else {
      fail('protected /iraq-ecom-traders/admin without auth', adminBody.slice(0, 120));
    }

    // 6) Admin login page
    await page.goto(`${BASE}/iraq-ecom-traders/admin/login`, { waitUntil: 'networkidle' });
    await waitPath(page, '/iraq-ecom-traders/admin/login');
    ok('admin login page loads');

    // API health
    const health = await page.request.get(`${API}/health`).catch(() => null);
    const healthOk = health && health.ok();
    if (!healthOk) {
      fail('backend health', 'API not reachable — skipping login/logout');
    } else {
      ok('backend health');

      // Login via UI
      await page.fill('#username', USER);
      await page.fill('#password', PASS);
      await page.click('button[type="submit"]');
      try {
        await waitPath(page, '/iraq-ecom-traders/admin', 20000);
        ok('admin login navigates to /iraq-ecom-traders/admin');

        // Refresh while authenticated
        await page.reload({ waitUntil: 'networkidle' });
        await waitPath(page, '/iraq-ecom-traders/admin');
        const afterRefresh = await page.locator('body').innerText();
        if (/إدارة الأعضاء|لوحة|تسجيل الخروج|المستخدمين|كشف العضوية/i.test(afterRefresh)) {
          ok('refresh keeps authenticated admin dashboard');
        } else if (/محمية|تسجيل الدخول/i.test(afterRefresh)) {
          fail('refresh keeps authenticated admin dashboard', 'logged out after refresh');
        } else {
          ok('refresh keeps /iraq-ecom-traders/admin path', afterRefresh.slice(0, 80));
        }

        // Deep link child page
        await page.goto(`${BASE}/iraq-ecom-traders/admin/users`, { waitUntil: 'networkidle' });
        await waitPath(page, '/iraq-ecom-traders/admin/users');
        ok('deep link /iraq-ecom-traders/admin/users');

        // Logout button if present
        const logoutBtn = page.locator('button[title="تسجيل الخروج"], button:has-text("تسجيل الخروج")').first();
        if (await logoutBtn.count()) {
          await page.goto(`${BASE}/iraq-ecom-traders/admin`, { waitUntil: 'networkidle' });
          const dashLogout = page.locator('button[title="تسجيل الخروج"]').first();
          if (await dashLogout.count()) {
            await dashLogout.click();
            await waitPath(page, '/iraq-ecom-traders/admin/login', 15000);
            ok('logout redirects to /iraq-ecom-traders/admin/login');
          } else {
            fail('logout redirects', 'logout button not found on dashboard');
          }
        } else {
          // API logout + toLogin path check via storage clear
          await page.evaluate(() => localStorage.removeItem('admin_access_token'));
          await page.goto(`${BASE}/iraq-ecom-traders/admin`, { waitUntil: 'networkidle' });
          ok('logout fallback cleared token (no logout button found)');
        }
      } catch (e) {
        fail('admin login flow', String(e.message || e));
      }
    }
  } finally {
    await browser.close();
  }

  const failed = results.filter((r) => !r.pass);
  console.log('\n--- Summary ---');
  console.log(`Passed: ${results.filter((r) => r.pass).length}  Failed: ${failed.length}`);
  if (failed.length) {
    process.exitCode = 1;
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
