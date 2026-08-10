import { chromium } from 'playwright';
import assert from 'node:assert/strict';

const base=process.env.SMOKE_BASE_URL||'http://127.0.0.1:4190';
const browser=await chromium.launch({headless:true});
const page=await browser.newPage({viewport:{width:1440,height:1000},locale:'ar-IQ'});
page.on('pageerror',error=>console.error('PAGE_ERROR',error.stack||error.message));
const permissions=Object.fromEntries([
  'dashboard.view','companies.view','companies.create','companies.edit','contracts.manage','pricing.manage',
  'member_links.view','member_links.create','member_links.edit','annexes.manage','monthly.view','monthly.enter',
  'monthly.approve','monthly.reopen','reports.view','reports.xlsx','reports.print','settlements.view',
  'settlements.create','settlements.reverse','revenues.view','revenues.create','revenues.edit',
  'expenses.view','expenses.create','expenses.edit',
].map(key=>[`financial.${key}`,true]));
Object.assign(permissions,{'backups.view':true,'backups.create':true,'backups.download':true,'backups.restore':true,'backups.delete':true});
const company={id:1,name:'شركة الرافدين للتوصيل',service_type_id:1,service_type_name:'التوصيل',status:'active',cooperation_status:'active',owner_name:'أحمد محمد',mobile:'07700000000',address:'بغداد'};

await page.route('**/api/**',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({})}));
await page.route('**/api/v1/admin/financial/**',async route=>{
  const path=new URL(route.request().url()).pathname;
  let body={items:[]};
  if(path.endsWith('/access'))body={permissions,is_super_admin:false};
  else if(path.endsWith('/companies'))body={items:[company]};
  else if(path.endsWith('/service-types'))body={items:[{id:1,name:'التوصيل',code:'delivery'}]};
  else if(path.endsWith('/backups'))body={items:[]};
  else if(path.endsWith('/revenues'))body={items:[{id:1,receipt_number:'REC-1',company_id:1,received_at:'2026-08-01',amount:500000,allocated:0,remaining:500000,receipt_method:'نقدي',category:'خدمات',description:'وصل اختبار',created_by:'admin',deleted:false}]};
  else if(path.endsWith('/dashboard/erp'))body={accrued_revenue:8500000,actual_revenue:6200000,expenses:1400000,estimated_profit:7100000,outstanding_receivable:2300000,actual_net_result:4800000,gross_business_amount:42000000,by_company:[{name:company.name,due:8500000,gross:42000000,received:6200000}],by_service:[{name:'التوصيل',gross:42000000,due:8500000}]};
  await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(body)});
});

for(const route of ['/iraq-ecom-traders/registration','/iraq-ecom-traders/admin','/iraq-ecom-traders/admin/financial/dashboard']){
  const response=await page.goto(`${base}${route}`);
  assert.equal(response?.status(),200,`deep link failed: ${route}`);
}
await page.waitForSelector('text=لوحة المؤشرات');
assert.equal(await page.getByText('ارتباطات الأعضاء').count(),1);
assert.equal(await page.getByText('الإيرادات الفعلية').count(),1);
assert.equal(await page.getByText('المستحق المتراكم').count(),1);
assert.ok(await page.getByText('شركة الرافدين للتوصيل').count()>=1);
assert.ok((await page.locator('body').getAttribute('dir'))==='rtl'||await page.locator('[dir="rtl"]').count()>0);
if(process.env.SMOKE_SCREENSHOT)await page.screenshot({path:process.env.SMOKE_SCREENSHOT,fullPage:true});

await page.getByRole('link',{name:'الشركات والعقود'}).click();
await page.waitForURL('**/financial/companies');
await page.waitForSelector('h2:has-text("الشركات والعقود")');
await page.getByRole('link',{name:'المصاريف'}).click();
await page.waitForURL('**/financial/expenses');
await page.goBack();
await page.waitForURL('**/financial/companies');

for(const [route,title] of [['companies','الشركات والعقود'],['links','ارتباطات الأعضاء'],['monthly','الإدخال الشهري'],['reports','التقارير المالية'],['settlements','التسويات'],['revenues','الإيرادات الفعلية'],['expenses','المصاريف'],['backups','النسخ الاحتياطية']]){
  await page.goto(`${base}/iraq-ecom-traders/admin/financial/${route}`);
  await page.waitForSelector(`h2:has-text("${title}")`);
}

await page.goto(`${base}/iraq-ecom-traders/admin/financial/expenses`);
const beforeDatePath=new URL(page.url()).pathname;
const dateInput=page.locator('input[type="date"]').first();
await dateInput.focus();
await dateInput.pressSequentially('01082026');
await dateInput.press('Enter');
await dateInput.press('Tab');
assert.equal(new URL(page.url()).pathname,beforeDatePath,'date typing must never mutate route');

await page.goto(`${base}/iraq-ecom-traders/admin/financial/revenues`);
await page.getByTitle('معاينة الوصل').click();
await page.waitForSelector('text=وصل قبض إلكتروني');

const inputPage=await browser.newPage({viewport:{width:1200,height:800},locale:'ar-IQ'});
await inputPage.route('**/api/**',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({})}));
await inputPage.route('**/api/v1/admin/financial/**',async route=>{
  const path=new URL(route.request().url()).pathname;
  const body=path.endsWith('/access')?{permissions:{'financial.monthly.view':true,'financial.monthly.enter':true},is_super_admin:false}:
    path.endsWith('/companies')?{items:[company]}:path.endsWith('/service-types')?{items:[{id:1,name:'التوصيل',code:'delivery'}]}:{items:[]};
  await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(body)});
});
await inputPage.goto(`${base}/iraq-ecom-traders/admin/financial/monthly`);
await inputPage.waitForSelector('h2:has-text("الإدخال الشهري")');
assert.equal(await inputPage.getByText('التقارير',{exact:true}).count(),0,'input-only role must not see reports');
assert.equal(await inputPage.getByText('حصة MFEC',{exact:true}).count(),0,'input-only role must not see financial amounts');
await inputPage.close();
console.log('financial route, registration, admin deep links: PASS');
await browser.close();
