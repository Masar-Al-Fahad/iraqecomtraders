import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { getAPIBaseURL } from '@/lib/config';

export type BrandSettings = {
  system_logo: string;
  report_logo: string;
  favicon: string;
  system_name: string;
  company_name: string;
  org_abbr: string;
  primary_color: string;
  secondary_color: string;
  button_color: string;
  header_color: string;
  sidebar_color: string;
  background_color: string;
  card_color: string;
  table_header_color: string;
  table_alt_row_color: string;
  text_color: string;
  border_color: string;
  hover_color: string;
  active_nav_color: string;
  success_color: string;
  warning_color: string;
  danger_color: string;
  info_color: string;
  footer_text: string;
  website: string;
  email: string;
  phone: string;
  address: string;
  header_text: string;
  footer_text_secondary: string;
  report_title: string;
  copyright: string;
  // Appearance
  font_family: string;
  page_title_size: string;
  subtitle_size: string;
  body_text_size: string;
  field_size: string;
  button_size: string;
  border_radius: string;
  form_width: string;
  banner_height: string;
  report_logo_size: string;
  element_spacing: string;
  watermark_enabled: string;
  watermark_opacity: string;
  whatsapp_welcome_message: string;
};

const DEFAULT_WELCOME = `مرحبًا بك في تجمع تجار التجارة الإلكترونية في العراق 🌹

تمت الموافقة على طلب انضمامك بنجاح، وأصبحت عضوًا في التجمع.
رقم عضويتك: {membership_number}

يمكنك الآن الانضمام إلى كروب الواتساب الرسمي عبر الرابط التالي:

https://chat.whatsapp.com/K7mtcycs8bBAnryQk3UgLc

نتمنى لك التوفيق، ونسعد بانضمامك إلى تجمع تجار التجارة الإلكترونية في العراق.`;

const DEFAULT_BRAND: BrandSettings = {
  system_logo: '/brand/mfec-logo.png',
  report_logo: '/brand/mfec-logo.png',
  favicon: '/favicon.svg',
  system_name: 'تجمع تجار التجارة الإلكترونية في العراق',
  company_name: 'شركة مسار الفهد للتجارة العامة والنقل العام',
  org_abbr: 'MFEC',
  primary_color: '#1e506b',
  secondary_color: '#C89B3C',
  button_color: '#C89B3C',
  header_color: '#1e506b',
  sidebar_color: '#0f2740',
  background_color: '#f5f7fa',
  card_color: '#ffffff',
  table_header_color: '#1e506b',
  table_alt_row_color: '#F3F4F6',
  text_color: '#172033',
  border_color: '#d5dbe3',
  hover_color: '#e8eef3',
  active_nav_color: '#C89B3C',
  success_color: '#15803d',
  warning_color: '#b45309',
  danger_color: '#b91c1c',
  info_color: '#1d4ed8',
  footer_text: 'برعاية شركة مسار الفهد للتجارة العامة والنقل العام',
  website: 'www.masaralfahad.com',
  email: 'management@masaralfahad.com',
  phone: '07748077716',
  address: 'العراق',
  header_text: 'لوحة إدارة تجمع تجار التجارة الإلكترونية',
  footer_text_secondary: 'تعاون • نمو • فرص • نجاح',
  report_title: 'تقرير أعضاء تجمع تجار التجارة الإلكترونية في العراق',
  copyright: '© جميع الحقوق محفوظة — تجمع تجار التجارة الإلكترونية في العراق',
  font_family: 'Tahoma, Arial, "Segoe UI", sans-serif',
  page_title_size: '28',
  subtitle_size: '16',
  body_text_size: '14',
  field_size: '14',
  button_size: '16',
  border_radius: '12',
  form_width: '640',
  banner_height: '180',
  report_logo_size: '72',
  element_spacing: '16',
  watermark_enabled: 'true',
  watermark_opacity: '7',
  whatsapp_welcome_message: DEFAULT_WELCOME,
};

type BrandContextValue = {
  brand: BrandSettings;
  loading: boolean;
  refresh: () => Promise<void>;
  resolveAssetUrl: (path: string) => string;
};

const BrandContext = createContext<BrandContextValue>({
  brand: DEFAULT_BRAND,
  loading: true,
  refresh: async () => {},
  resolveAssetUrl: (p) => p,
});

function hexToHslChannels(hex: string): string | null {
  const raw = (hex || '').trim();
  const m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(raw);
  if (!m) return null;
  const r = parseInt(m[1], 16) / 255;
  const g = parseInt(m[2], 16) / 255;
  const b = parseInt(m[3], 16) / 255;
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  let h = 0;
  let s = 0;
  const l = (max + min) / 2;
  if (max !== min) {
    const d = max - min;
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    switch (max) {
      case r:
        h = (g - b) / d + (g < b ? 6 : 0);
        break;
      case g:
        h = (b - r) / d + 2;
        break;
      default:
        h = (r - g) / d + 4;
        break;
    }
    h /= 6;
  }
  return `${Math.round(h * 360)} ${Math.round(s * 100)}% ${Math.round(l * 100)}%`;
}

function applyCssVars(brand: BrandSettings) {
  const root = document.documentElement;
  const primary = brand.primary_color || '#1e506b';
  const secondary = brand.secondary_color || '#C89B3C';
  const button = brand.button_color || secondary;
  const header = brand.header_color || primary;
  const sidebar = brand.sidebar_color || primary;
  const background = brand.background_color || '#f5f7fa';
  const card = brand.card_color || '#ffffff';
  const text = brand.text_color || '#172033';
  const border = brand.border_color || '#d5dbe3';
  const danger = brand.danger_color || '#b91c1c';
  const success = brand.success_color || '#15803d';
  const warning = brand.warning_color || '#b45309';
  const info = brand.info_color || '#1d4ed8';
  const hover = brand.hover_color || '#e8eef3';
  const activeNav = brand.active_nav_color || secondary;

  root.style.setProperty('--mfec-navy', primary);
  root.style.setProperty('--mfec-gold', secondary);
  root.style.setProperty('--mfec-header', header);
  root.style.setProperty('--mfec-sidebar', sidebar);
  root.style.setProperty('--mfec-button', button);
  root.style.setProperty('--mfec-bg', background);
  root.style.setProperty('--mfec-card', card);
  root.style.setProperty('--mfec-text', text);
  root.style.setProperty('--mfec-border', border);
  root.style.setProperty('--mfec-hover', hover);
  root.style.setProperty('--mfec-active-nav', activeNav);
  root.style.setProperty('--mfec-success', success);
  root.style.setProperty('--mfec-warning', warning);
  root.style.setProperty('--mfec-danger', danger);
  root.style.setProperty('--mfec-info', info);
  root.style.setProperty('--mfec-table-header', brand.table_header_color || primary);
  root.style.setProperty('--mfec-table-alt', brand.table_alt_row_color || '#F3F4F6');
  root.style.setProperty('--mfec-font', brand.font_family || 'Tahoma, Arial, sans-serif');
  root.style.setProperty('--mfec-title-size', `${brand.page_title_size || 28}px`);
  root.style.setProperty('--mfec-subtitle-size', `${brand.subtitle_size || 16}px`);
  root.style.setProperty('--mfec-text-size', `${brand.body_text_size || 14}px`);
  root.style.setProperty('--mfec-field-size', `${brand.field_size || 14}px`);
  root.style.setProperty('--mfec-button-size', `${brand.button_size || 16}px`);
  root.style.setProperty('--mfec-radius', `${brand.border_radius || 12}px`);
  root.style.setProperty('--mfec-form-width', `${brand.form_width || 640}px`);
  root.style.setProperty('--mfec-banner-height', `${brand.banner_height || 180}px`);
  root.style.setProperty('--mfec-spacing', `${brand.element_spacing || 16}px`);
  root.style.fontFamily = brand.font_family || 'Tahoma, Arial, sans-serif';

  // Bridge into shadcn / Tailwind semantic tokens (H S% L%)
  const setHsl = (name: string, hex: string, fallback: string) => {
    const channels = hexToHslChannels(hex) || hexToHslChannels(fallback);
    if (channels) root.style.setProperty(name, channels);
  };
  setHsl('--primary', primary, '#1e506b');
  setHsl('--ring', primary, '#1e506b');
  setHsl('--secondary', secondary, '#C89B3C');
  setHsl('--background', background, '#f5f7fa');
  setHsl('--card', card, '#ffffff');
  setHsl('--foreground', text, '#172033');
  setHsl('--card-foreground', text, '#172033');
  setHsl('--border', border, '#d5dbe3');
  setHsl('--input', border, '#d5dbe3');
  setHsl('--destructive', danger, '#b91c1c');
  setHsl('--sidebar-background', sidebar, '#0f2740');
  setHsl('--sidebar-primary', activeNav, '#C89B3C');
  setHsl('--sidebar-accent', hover, '#e8eef3');
  root.style.setProperty('--primary-foreground', '0 0% 100%');
  root.style.setProperty('--secondary-foreground', '0 0% 100%');

  const fav = brand.favicon || '/favicon.svg';
  let link = document.querySelector("link[rel='icon']") as HTMLLinkElement | null;
  if (!link) {
    link = document.createElement('link');
    link.rel = 'icon';
    document.head.appendChild(link);
  }
  const base = (getAPIBaseURL() || '').replace(/\/$/, '');
  link.href = fav.startsWith('/api/') ? `${base}${fav}` : fav;
}

export function BrandProvider({ children }: { children: React.ReactNode }) {
  const [brand, setBrand] = useState<BrandSettings>(DEFAULT_BRAND);
  const [loading, setLoading] = useState(true);

  const resolveAssetUrl = useCallback((path: string) => {
    if (!path) return `${typeof window !== 'undefined' ? window.location.origin : ''}/brand/mfec-logo.png`;
    if (path.startsWith('http') || path.startsWith('data:')) return path;
    if (path.startsWith('/api/')) {
      const base = getAPIBaseURL().replace(/\/$/, '');
      return base ? `${base}${path}` : path;
    }
    if (path.startsWith('/')) {
      const origin = typeof window !== 'undefined' ? window.location.origin : '';
      return `${origin}${path}`;
    }
    return path;
  }, []);

  const refresh = useCallback(async () => {
    try {
      const base = getAPIBaseURL().replace(/\/$/, '');
      const res = await fetch(`${base}/api/v1/public/app-settings/brand`);
      if (res.ok) {
        const data = await res.json();
        const merged = { ...DEFAULT_BRAND, ...data };
        setBrand(merged);
        applyCssVars(merged);
      } else {
        applyCssVars(DEFAULT_BRAND);
      }
    } catch {
      applyCssVars(DEFAULT_BRAND);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const value = useMemo(
    () => ({ brand, loading, refresh, resolveAssetUrl }),
    [brand, loading, refresh, resolveAssetUrl]
  );

  return <BrandContext.Provider value={value}>{children}</BrandContext.Provider>;
}

export function useBrand() {
  return useContext(BrandContext);
}

export { DEFAULT_BRAND };
