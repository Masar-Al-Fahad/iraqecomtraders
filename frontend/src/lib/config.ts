// Runtime configuration
let runtimeConfig: {
  API_BASE_URL: string;
  SITE_URL?: string;
  ADMIN_URL?: string;
} | null = null;

let configLoading = true;

/**
 * Resolve API base URL from environment only — never hardcode production hosts.
 * Local fallback keeps development working when env is unset.
 */
function envApiBase(): string {
  const fromVite = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim();
  if (fromVite) return fromVite.replace(/\/$/, '');
  // Same-origin / reverse-proxy production (mfec / mfec-admin → API via gateway)
  if (typeof window !== 'undefined' && window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1') {
    return '';
  }
  return 'http://127.0.0.1:8000';
}

const defaultConfig = {
  API_BASE_URL: envApiBase(),
  SITE_URL: (import.meta.env.VITE_SITE_URL as string | undefined)?.trim() || '',
  ADMIN_URL: (import.meta.env.VITE_ADMIN_URL as string | undefined)?.trim() || '',
};

export async function loadRuntimeConfig(): Promise<void> {
  try {
    const response = await fetch('/api/config');
    if (response.ok) {
      const contentType = response.headers.get('content-type');
      if (contentType && contentType.includes('application/json')) {
        runtimeConfig = await response.json();
      }
    }
  } catch {
    // use env / defaults
  } finally {
    configLoading = false;
  }
}

export function getConfig() {
  if (configLoading && !runtimeConfig) {
    return {
      API_BASE_URL: envApiBase(),
      SITE_URL: defaultConfig.SITE_URL,
      ADMIN_URL: defaultConfig.ADMIN_URL,
    };
  }
  if (runtimeConfig) {
    return {
      API_BASE_URL: (runtimeConfig.API_BASE_URL || envApiBase()).replace(/\/$/, ''),
      SITE_URL: runtimeConfig.SITE_URL || defaultConfig.SITE_URL,
      ADMIN_URL: runtimeConfig.ADMIN_URL || defaultConfig.ADMIN_URL,
    };
  }
  if (import.meta.env.VITE_API_BASE_URL) {
    return {
      API_BASE_URL: String(import.meta.env.VITE_API_BASE_URL).replace(/\/$/, ''),
      SITE_URL: defaultConfig.SITE_URL,
      ADMIN_URL: defaultConfig.ADMIN_URL,
    };
  }
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
