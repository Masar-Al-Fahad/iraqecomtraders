import { getAPIBaseURL } from './config';

const TOKEN_KEY = 'admin_access_token';

function apiBase() {
  return getAPIBaseURL().replace(/\/$/, '');
}

async function readError(res: Response): Promise<string> {
  try {
    const data = await res.json();
    if (typeof data?.detail === 'string') return data.detail;
    if (Array.isArray(data?.detail)) {
      return data.detail.map((d: any) => d.msg || JSON.stringify(d)).join(', ');
    }
    return data?.message || res.statusText;
  } catch {
    return res.statusText || 'Request failed';
  }
}

export const localAuth = {
  getToken(): string | null {
    return localStorage.getItem(TOKEN_KEY);
  },
  setToken(token: string) {
    localStorage.setItem(TOKEN_KEY, token);
  },
  clearToken() {
    localStorage.removeItem(TOKEN_KEY);
  },
  isLoggedIn(): boolean {
    return !!localStorage.getItem(TOKEN_KEY);
  },
};

export function getApiBase() {
  return apiBase();
}

export async function downloadAuthorizedFile(urlPath: string, filename: string) {
  const token = localAuth.getToken();
  const res = await fetch(`${apiBase()}${urlPath.startsWith('/') ? urlPath : `/${urlPath}`}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) {
    throw Object.assign(new Error(await readError(res)), { status: res.status });
  }
  const raw = await res.arrayBuffer();
  const blob = new Blob([raw], {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  });
  // Basic ZIP/XLSX signature check — reject CSV disguised as xlsx
  const sig = new Uint8Array(raw.slice(0, 2));
  if (sig[0] !== 0x50 || sig[1] !== 0x4b) {
    throw new Error('الملف المُرجع ليس ملف Excel صالحًا');
  }
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = filename.endsWith('.xlsx') ? filename : `${filename}.xlsx`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(link.href);
}

/** Drop-in replacement for @metagptx/web-sdk client (local mode). */
export const client = {
  auth: {
    async me() {
      const token = localAuth.getToken();
      if (!token) return { data: null };
      const res = await fetch(`${apiBase()}/api/v1/auth/me`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        if (res.status === 401) {
          localAuth.clearToken();
          return { data: null };
        }
        throw Object.assign(new Error(await readError(res)), { status: res.status });
      }
      return { data: await res.json() };
    },
    toLogin() {
      window.location.href = '/admin/login';
    },
    async login(username: string, password: string) {
      const res = await fetch(`${apiBase()}/api/v1/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });
      if (!res.ok) {
        throw Object.assign(new Error(await readError(res)), { status: res.status });
      }
      const data = await res.json();
      localAuth.setToken(data.token);
      return data;
    },
    async logout() {
      try {
        const token = localAuth.getToken();
        await fetch(`${apiBase()}/api/v1/auth/logout`, {
          method: 'POST',
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
      } catch {
        // ignore
      }
      localAuth.clearToken();
    },
  },
  apiCall: {
    async invoke({
      url,
      method = 'GET',
      data,
    }: {
      url: string;
      method?: string;
      data?: any;
    }) {
      const token = localAuth.getToken();
      const upper = (method || 'GET').toUpperCase();
      const headers: Record<string, string> = {};
      if (token) headers.Authorization = `Bearer ${token}`;

      const init: RequestInit = { method: upper, headers };
      if (upper !== 'GET' && upper !== 'HEAD') {
        headers['Content-Type'] = 'application/json';
        init.body = JSON.stringify(data ?? {});
      }

      const res = await fetch(`${apiBase()}${url.startsWith('/') ? url : `/${url}`}`, init);
      if (!res.ok) {
        const err: any = new Error(await readError(res));
        err.status = res.status;
        err.response = { status: res.status, data: { detail: err.message } };
        throw err;
      }
      if (res.status === 204) return { data: null };
      const text = await res.text();
      if (!text) return { data: null };
      try {
        return { data: JSON.parse(text) };
      } catch {
        return { data: text };
      }
    },
  },
  storage: {
    async getUploadUrl({ bucket_name, object_key }: { bucket_name: string; object_key: string }) {
      const res = await fetch(`${apiBase()}/api/v1/public/upload-url`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ bucket_name, object_key }),
      });
      if (!res.ok) throw new Error(await readError(res));
      const data = await res.json();
      return { data };
    },
    async getDownloadUrl({ bucket_name, object_key }: { bucket_name: string; object_key: string }) {
      void bucket_name;
      const key = object_key.startsWith('registrations/')
        ? object_key
        : `registrations/${object_key}`;
      return {
        data: {
          download_url: `${apiBase()}/api/v1/public/files/${key}`,
        },
      };
    },
  },
};
