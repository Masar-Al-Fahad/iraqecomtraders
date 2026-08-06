import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useToast } from '@/hooks/use-toast';
import { Toaster } from '@/components/ui/toaster';
import { client } from '@/lib/localApi';
import { getAPIBaseURL } from '@/lib/config';
import { useBrand, DEFAULT_BRAND, type BrandSettings } from '@/lib/brand';
import { ROUTES } from '@/lib/routes';
import { ArrowRight, Save, RotateCcw, Upload } from 'lucide-react';

const IDENTITY_FIELDS: { key: keyof BrandSettings; label: string; type?: string }[] = [
  { key: 'system_name', label: 'اسم النظام' },
  { key: 'org_abbr', label: 'الاختصار' },
  { key: 'header_text', label: 'نص الهيدر' },
  { key: 'report_title', label: 'عنوان التقرير' },
  { key: 'primary_color', label: 'اللون الرئيسي', type: 'color' },
  { key: 'secondary_color', label: 'اللون الثانوي', type: 'color' },
  { key: 'button_color', label: 'لون الأزرار', type: 'color' },
  { key: 'header_color', label: 'لون الهيدر', type: 'color' },
  { key: 'table_header_color', label: 'لون رؤوس الجداول', type: 'color' },
  { key: 'table_alt_row_color', label: 'لون صفوف الجداول المتناوبة', type: 'color' },
];

const FOOTER_FIELDS: { key: keyof BrandSettings; label: string }[] = [
  { key: 'company_name', label: 'اسم الشركة' },
  { key: 'website', label: 'الموقع الإلكتروني' },
  { key: 'email', label: 'البريد الإلكتروني' },
  { key: 'phone', label: 'الهاتف' },
  { key: 'footer_text', label: 'نص الرعاية' },
  { key: 'copyright', label: 'حقوق النشر' },
  { key: 'address', label: 'العنوان' },
  { key: 'footer_text_secondary', label: 'نص تذييل ثانوي' },
];

const APPEARANCE_FIELDS: { key: keyof BrandSettings; label: string }[] = [
  { key: 'font_family', label: 'نوع الخط' },
  { key: 'page_title_size', label: 'حجم عنوان الصفحة (px)' },
  { key: 'subtitle_size', label: 'حجم العنوان الفرعي (px)' },
  { key: 'body_text_size', label: 'حجم النص (px)' },
  { key: 'field_size', label: 'حجم الحقول (px)' },
  { key: 'button_size', label: 'حجم الأزرار (px)' },
  { key: 'border_radius', label: 'Border Radius (px)' },
  { key: 'form_width', label: 'عرض الاستمارة (px)' },
  { key: 'banner_height', label: 'ارتفاع الـ Banner (px) — مهجور' },
  { key: 'report_logo_size', label: 'حجم شعار التقارير (px)' },
  { key: 'element_spacing', label: 'المسافات بين العناصر (px)' },
  { key: 'watermark_enabled', label: 'تفعيل العلامة المائية (true/false)' },
  { key: 'watermark_opacity', label: 'شفافية العلامة المائية % (5–10)' },
];

function FieldRow({
  label,
  value,
  onChange,
  type,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
}) {
  return (
    <div className="space-y-1 text-right">
      <Label>{label}</Label>
      <div className="flex gap-2 items-center">
        <Input type="text" value={value} onChange={(e) => onChange(e.target.value)} className="text-right" />
        {type === 'color' && (
          <input type="color" value={value || '#000000'} onChange={(e) => onChange(e.target.value)} className="w-10 h-10 rounded border" />
        )}
      </div>
    </div>
  );
}

export default function BrandSettingsPage() {
  const navigate = useNavigate();
  const { toast } = useToast();
  const { refresh, resolveAssetUrl } = useBrand();
  const [form, setForm] = useState<BrandSettings>(DEFAULT_BRAND);
  const [saving, setSaving] = useState(false);
  const [authOk, setAuthOk] = useState(false);

  useEffect(() => {
    const boot = async () => {
      try {
        const me = await client.auth.me();
        if (!me?.data) {
          navigate(ROUTES.ADMIN_LOGIN);
          return;
        }
        const check = await client.apiCall.invoke({
          url: '/api/v1/admin/registrations/check-admin',
          method: 'GET',
          data: {},
        });
        const perms = check.data?.permissions || me.data.permissions || {};
        if (!check.data?.is_super_admin && !me.data.is_super_admin && !perms.manage_brand_settings) {
          toast({ title: 'غير مسموح', description: 'ليس لديك صلاحية إدارة الهوية', variant: 'destructive' });
          navigate(ROUTES.ADMIN);
          return;
        }
        const res = await client.apiCall.invoke({
          url: '/api/v1/admin/app-settings/brand',
          method: 'GET',
          data: {},
        });
        setForm({ ...DEFAULT_BRAND, ...res.data });
        setAuthOk(true);
      } catch {
        navigate(ROUTES.ADMIN_LOGIN);
      }
    };
    boot();
  }, [navigate, toast]);

  const set = (key: keyof BrandSettings, value: string) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const uploadLogo = async (target: 'system_logo' | 'report_logo' | 'favicon', file: File) => {
    const token = localStorage.getItem('admin_access_token');
    const base = getAPIBaseURL().replace(/\/$/, '');
    const body = new FormData();
    body.append('file', file);
    const res = await fetch(`${base}/api/v1/admin/app-settings/upload-brand-asset`, {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body,
    });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    set(target, data.url);
    toast({ title: 'تم الرفع', description: 'تم رفع الملف بنجاح' });
  };

  const save = async () => {
    let opacity = Number(form.watermark_opacity);
    if (!Number.isFinite(opacity)) opacity = 7;
    opacity = Math.min(10, Math.max(5, opacity));
    const payload = {
      ...form,
      watermark_opacity: String(opacity),
      watermark_enabled:
        String(form.watermark_enabled || 'true').toLowerCase() === 'false' ? 'false' : 'true',
    };
    setSaving(true);
    try {
      await client.apiCall.invoke({
        url: '/api/v1/admin/app-settings/brand',
        method: 'PUT',
        data: { settings: payload },
      });
      setForm(payload);
      await refresh();
      toast({ title: 'تم الحفظ', description: 'تم تطبيق إعدادات الهوية والمظهر والفوتر' });
    } catch (e: any) {
      toast({ title: 'خطأ', description: e?.message || 'فشل الحفظ', variant: 'destructive' });
    } finally {
      setSaving(false);
    }
  };

  const reset = async () => {
    if (!confirm('استعادة الإعدادات الافتراضية؟')) return;
    setSaving(true);
    try {
      const res = await client.apiCall.invoke({
        url: '/api/v1/admin/app-settings/brand/reset',
        method: 'POST',
        data: {},
      });
      setForm({ ...DEFAULT_BRAND, ...(res.data?.settings || {}) });
      await refresh();
      toast({ title: 'تمت الاستعادة' });
    } catch (e: any) {
      toast({ title: 'خطأ', description: e?.message || 'فشلت الاستعادة', variant: 'destructive' });
    } finally {
      setSaving(false);
    }
  };

  if (!authOk) {
    return <div className="min-h-screen flex items-center justify-center text-gray-500">جاري التحميل...</div>;
  }

  return (
    <div className="min-h-screen bg-[#F9FAFB]" dir="rtl">
      <Toaster />
      <header className="sticky top-0 z-10 border-b text-white" style={{ background: form.header_color || '#1F2937' }}>
        <div className="max-w-5xl mx-auto px-4 py-3 flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-3">
            <img src={resolveAssetUrl(form.system_logo)} alt="logo" className="w-10 h-10 object-contain bg-white/10 rounded" />
            <div>
              <h1 className="font-bold">إعدادات الهوية</h1>
              <p className="text-xs opacity-80">الهوية · المظهر · الفوتر</p>
            </div>
          </div>
          <div className="flex gap-2">
            <Button variant="secondary" size="sm" onClick={() => navigate(ROUTES.ADMIN)} className="gap-1">
              <ArrowRight className="w-4 h-4" /> رجوع
            </Button>
            <Button size="sm" onClick={reset} variant="outline" className="bg-white/10 text-white border-white/30 gap-1">
              <RotateCcw className="w-4 h-4" /> افتراضي
            </Button>
            <Button size="sm" onClick={save} disabled={saving} style={{ background: form.button_color || '#C89B3C' }} className="text-white gap-1">
              <Save className="w-4 h-4" /> حفظ
            </Button>
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto p-4 space-y-4">
        <Card>
          <CardHeader><CardTitle className="text-right">الشعارات</CardTitle></CardHeader>
          <CardContent className="grid md:grid-cols-3 gap-4">
            {([
              ['system_logo', 'شعار النظام'],
              ['report_logo', 'شعار التقارير'],
              ['favicon', 'Favicon'],
            ] as const).map(([key, label]) => (
              <div key={key} className="space-y-2 text-right border rounded-lg p-3">
                <Label>{label}</Label>
                <img src={resolveAssetUrl(form[key])} alt={label} className="h-16 object-contain mx-auto" />
                <Input value={form[key]} onChange={(e) => set(key, e.target.value)} className="text-right text-xs" />
                <label className="inline-flex items-center gap-2 text-sm cursor-pointer">
                  <Upload className="w-4 h-4" /> رفع ملف
                  <input
                    type="file"
                    accept="image/*,.ico,.svg"
                    className="hidden"
                    onChange={async (e) => {
                      const f = e.target.files?.[0];
                      if (!f) return;
                      try {
                        await uploadLogo(key, f);
                      } catch (err: any) {
                        toast({ title: 'خطأ', description: err?.message || 'فشل الرفع', variant: 'destructive' });
                      }
                    }}
                  />
                </label>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle className="text-right">النصوص والألوان</CardTitle></CardHeader>
          <CardContent className="grid md:grid-cols-2 gap-4">
            {IDENTITY_FIELDS.map(({ key, label, type }) => (
              <FieldRow key={key} label={label} value={String(form[key] || '')} onChange={(v) => set(key, v)} type={type} />
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle className="text-right">إعدادات المظهر (Appearance)</CardTitle></CardHeader>
          <CardContent className="grid md:grid-cols-2 gap-4">
            {APPEARANCE_FIELDS.map(({ key, label }) => (
              <FieldRow key={key} label={label} value={String(form[key] || '')} onChange={(v) => set(key, v)} />
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle className="text-right">الفوتر (قابل للتعديل بالكامل)</CardTitle></CardHeader>
          <CardContent className="grid md:grid-cols-2 gap-4">
            {FOOTER_FIELDS.map(({ key, label }) => (
              <FieldRow key={key} label={label} value={String(form[key] || '')} onChange={(v) => set(key, v)} />
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle className="text-right">رسالة ترحيب واتساب (رسالة الانضمام)</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-right">
            <Label>استخدم {'{membership_number}'} و {'{system_name}'} كمتغيرات</Label>
            <textarea
              className="w-full min-h-[180px] border rounded-md p-3 text-right text-sm"
              value={form.whatsapp_welcome_message || ''}
              onChange={(e) => set('whatsapp_welcome_message', e.target.value)}
            />
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
