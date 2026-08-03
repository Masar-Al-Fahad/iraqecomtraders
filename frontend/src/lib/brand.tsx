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
  table_header_color: string;
  table_alt_row_color: string;
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
  primary_color: '#1F2937',
  secondary_color: '#C89B3C',
  button_color: '#C89B3C',
  header_color: '#1F2937',
  table_header_color: '#1F2937',
  table_alt_row_color: '#F3F4F6',
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

function applyCssVars(brand: BrandSettings) {
  const root = document.documentElement;
  root.style.setProperty('--mfec-navy', brand.primary_color || '#1F2937');
  root.style.setProperty('--mfec-gold', brand.secondary_color || '#C89B3C');
  root.style.setProperty('--mfec-header', brand.header_color || brand.primary_color || '#1F2937');
  root.style.setProperty('--mfec-button', brand.button_color || brand.secondary_color || '#C89B3C');
  root.style.setProperty('--mfec-table-header', brand.table_header_color || '#1F2937');
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
