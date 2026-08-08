/** Canonical frontend paths for Iraq E-Com Traders. */

export const APP_BASE = '/iraq-ecom-traders';

export const ROUTES = {
  REGISTRATION: `${APP_BASE}/registration`,
  ADMIN: `${APP_BASE}/admin`,
  ADMIN_LOGIN: `${APP_BASE}/admin/login`,
  ADMIN_PRINT: `${APP_BASE}/admin/print`,
  ADMIN_USERS: `${APP_BASE}/admin/users`,
  ADMIN_BRAND_SETTINGS: `${APP_BASE}/admin/brand-settings`,
  ADMIN_FORM_SETTINGS: `${APP_BASE}/admin/form-settings`,
  ADMIN_MEMBERSHIP_REPORT: `${APP_BASE}/admin/membership-report`,
  ADMIN_FINANCIAL: `${APP_BASE}/admin/financial`,
} as const;

/** Map legacy `/admin...` pathname (+ search/hash) to canonical admin path. */
export function legacyAdminToCanonical(pathname: string, search = '', hash = ''): string {
  const rest = pathname.replace(/^\/admin/, '') || '';
  return `${ROUTES.ADMIN}${rest}${search}${hash}`;
}
