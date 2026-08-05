/**
 * API / site URL resolution.
 * Prefer VITE_API_BASE_URL (or alias VITE_API_URL) baked in at Vite build time.
 * Do not fetch /api/config — the static frontend has no such route.
 */

const PRODUCTION_API_BASE = 'https://iraqecomtraders-production.up.railway.app';

/**
 * Resolve API base URL from env, then sensible defaults.
 * Local → http://127.0.0.1:8000; production → Railway backend.
 */
function envApiBase(): string {
  const fromVite = (
    (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim() ||
    (import.meta.env.VITE_API_URL as string | undefined)?.trim() ||
    ''
  );
  if (fromVite) return fromVite.replace(/\/$/, '');

  if (
    typeof window === 'undefined' ||
    window.location.hostname === 'localhost' ||
    window.location.hostname === '127.0.0.1'
  ) {
    return 'http://127.0.0.1:8000';
  }

  return PRODUCTION_API_BASE;
}

const defaultConfig = {
  API_BASE_URL: envApiBase(),
  SITE_URL: (import.meta.env.VITE_SITE_URL as string | undefined)?.trim() || '',
  ADMIN_URL: (import.meta.env.VITE_ADMIN_URL as string | undefined)?.trim() || '',
};

/** Kept for startup sequencing in main.tsx — no network call. */
export async function loadRuntimeConfig(): Promise<void> {
  // API base comes from VITE_API_BASE_URL / VITE_API_URL (or production fallback).
}

export function getConfig() {
  return {
    API_BASE_URL: envApiBase(),
    SITE_URL: defaultConfig.SITE_URL,
    ADMIN_URL: defaultConfig.ADMIN_URL,
  };
}

export function getAPIBaseURL(): string {
  return getConfig().API_BASE_URL;
}

export function getSiteURL(): string {
  return getConfig().SITE_URL || (typeof window !== 'undefined' ? window.location.origin : '');
}

export function getAdminURL(): string {
  return getConfig().ADMIN_URL || (typeof window !== 'undefined' ? window.location.origin : '');
}

export const config = {
  get API_BASE_URL() {
    return getAPIBaseURL();
  },
  get SITE_URL() {
    return getSiteURL();
  },
  get ADMIN_URL() {
    return getAdminURL();
  },
};
