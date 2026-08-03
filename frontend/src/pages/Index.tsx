import { useEffect, useMemo, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Card, CardContent } from '@/components/ui/card';
import { useToast } from '@/hooks/use-toast';
import { Toaster } from '@/components/ui/toaster';
import { CheckCircle, Upload } from 'lucide-react';
import { Checkbox } from '@/components/ui/checkbox';
import { useBrand } from '@/lib/brand';
import { getAPIBaseURL } from '@/lib/config';
import { WatermarkLayer } from '@/lib/Watermark';

type FormField = {
  id: string;
  type: string;
  label: string;
  placeholder: string;
  required: boolean;
  visible: boolean;
  order: number;
  options: string[];
  maps_to?: string | null;
};

type FormSettings = {
  identity: Record<string, any>;
  texts: Record<string, string>;
  fields: FormField[];
};

const CORE_KEYS = ['business_name', 'merchant_name', 'phone', 'governorate', 'area', 'business_type', 'notes'] as const;

export default function Index() {
  const { toast } = useToast();
  const { brand, resolveAssetUrl } = useBrand();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [loading, setLoading] = useState(false);
  const [booting, setBooting] = useState(true);
  const [submitted, setSubmitted] = useState(false);
  const [requestNumber, setRequestNumber] = useState('');
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [formCfg, setFormCfg] = useState<FormSettings | null>(null);
  const [values, setValues] = useState<Record<string, any>>({});
  const [agreedToTerms, setAgreedToTerms] = useState(false);

  useEffect(() => {
    const load = async () => {
      try {
        const base = (getAPIBaseURL() || '').replace(/\/$/, '');
        const res = await fetch(`${base}/api/v1/public/app-settings/registration-form`);
        if (res.ok) {
          const data = await res.json();
          setFormCfg(data);
          const init: Record<string, any> = {};
          (data.fields || []).forEach((f: FormField) => {
            if (f.type === 'checkbox') init[f.id] = false;
            else if (f.type === 'multi_select') init[f.id] = [];
            else init[f.id] = '';
          });
          setValues(init);
        } else {
          setFormCfg({
            identity: {
              logo: '/brand/mfec-logo.png',
              title: 'طلب انضمام لتجمع تجار التجارة الإلكترونية',
              subtitle: 'املأ البيانات التالية للانضمام',
              primary_color: '#1F2937',
              secondary_color: '#C89B3C',
              background_color: '#F9FAFB',
              button_color: '#C89B3C',
              field_color: '#FFFFFF',
              logo_size: 72,
              form_width: 640,
              border_radius: 12,
              logo_position: 'center',
            },
            texts: {
              page_title: 'بوابة الانضمام',
              description: 'تجمع تجار التجارة الإلكترونية في العراق',
              submit_button: 'إرسال طلب الانضمام',
              success_message: 'تم استلام طلبك بنجاح',
              error_message: 'حدث خطأ أثناء الإرسال',
              success_page_title: 'تم إرسال الطلب',
              new_request_button: 'إرسال طلب جديد',
            },
            fields: [],
          });
        }
      } catch {
        // keep null → fallback UI defaults via empty
      } finally {
        setBooting(false);
      }
    };
    load();
  }, []);

  const idn = formCfg?.identity || {};
  const texts = formCfg?.texts || {};
  const fieldsSorted = useMemo(
    () => [...(formCfg?.fields || [])].sort((a, b) => (a.order || 0) - (b.order || 0)),
    [formCfg]
  );
  const visibleFields = fieldsSorted.filter((f) => f.visible);

  const setVal = (id: string, v: any) => setValues((prev) => ({ ...prev, [id]: v }));

  const handleImageChange = (e: React.ChangeEvent<HTMLInputElement>, fieldId: string) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const allowedTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp'];
    if (!allowedTypes.includes(file.type) && !file.type.startsWith('image/')) {
      toast({ title: 'خطأ', description: 'صيغة الملف غير مدعومة', variant: 'destructive' });
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      toast({ title: 'خطأ', description: 'الحد الأقصى 5MB', variant: 'destructive' });
      return;
    }
    setImageFile(file);
    setVal(fieldId, file.name);
    const reader = new FileReader();
    reader.onloadend = () => setImagePreview(reader.result as string);
    reader.readAsDataURL(file);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const errMsg = texts.error_message || 'حدث خطأ أثناء الإرسال';

    for (const f of visibleFields) {
      if (!f.required) continue;
      if (f.type === 'image_upload' || f.maps_to === 'image_key') {
        if (!imageFile) {
          toast({ title: 'خطأ', description: `يرجى رفع: ${f.label}`, variant: 'destructive' });
          return;
        }
        continue;
      }
      if (f.type === 'checkbox' || f.id === 'terms') {
        if (!values[f.id] && !agreedToTerms) {
          toast({ title: 'خطأ', description: f.label || 'يرجى الموافقة على الشروط', variant: 'destructive' });
          return;
        }
        continue;
      }
      const v = values[f.id];
      if (v === undefined || v === null || v === '' || (Array.isArray(v) && v.length === 0)) {
        toast({ title: 'خطأ', description: `يرجى ملء: ${f.label}`, variant: 'destructive' });
        return;
      }
    }

    setLoading(true);
    try {
      const API_BASE = (getAPIBaseURL() || '').replace(/\/$/, '');
      let finalKey = 'manual_entry';

      if (imageFile) {
        const timestamp = Date.now();
        const safeName = imageFile.name.replace(/[^A-Za-z0-9._-]/g, '_');
        const objectKey = `registrations/${timestamp}_${safeName}`;
        const uploadRes = await fetch(`${API_BASE}/api/v1/public/upload-url`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ bucket_name: 'business-images', object_key: objectKey }),
        });
        if (!uploadRes.ok) {
          const errData = await uploadRes.json().catch(() => ({}));
          throw new Error(errData.detail || 'فشل في رفع الصورة');
        }
        const uploadData = await uploadRes.json();
        const putRes = await fetch(uploadData.upload_url, {
          method: 'PUT',
          body: imageFile,
          headers: { 'Content-Type': imageFile.type || 'application/octet-stream' },
        });
        if (!putRes.ok) throw new Error('فشل في رفع الصورة إلى الخادم');
        const putData = await putRes.json().catch(() => ({}));
        finalKey = putData.object_key || objectKey;
      }

      const payload: Record<string, any> = {
        business_name: '',
        merchant_name: '',
        phone: '',
        governorate: '',
        area: '',
        business_type: '',
        notes: '',
        image_key: finalKey,
        extra_fields: {},
      };

      const extrasNotes: string[] = [];
      const extraFields: Record<string, { label: string; value: any }> = {};
      for (const f of fieldsSorted) {
        const raw = values[f.id];
        if (f.maps_to && CORE_KEYS.includes(f.maps_to as any)) {
          if (f.visible) {
            payload[f.maps_to] = Array.isArray(raw) ? raw.join(', ') : (raw ?? '');
          } else if (f.required) {
            payload[f.maps_to] = payload[f.maps_to] || '-';
          }
        } else if (f.maps_to === 'image_key') {
          // handled
        } else if (f.id !== 'terms' && f.visible && raw !== undefined && raw !== '' && raw !== false) {
          const shown = Array.isArray(raw) ? raw.join(', ') : raw;
          extraFields[f.id] = { label: f.label, value: shown };
          extrasNotes.push(`${f.label}: ${Array.isArray(shown) ? shown.join(', ') : String(shown)}`);
        }
      }

      // ensure required API fields have values even if hidden
      for (const k of ['business_name', 'merchant_name', 'phone', 'governorate', 'area', 'business_type']) {
        if (!payload[k]) payload[k] = '-';
      }

      payload.extra_fields = extraFields;
      // Keep notes for human readability / backward compatibility
      if (extrasNotes.length) {
        payload.notes = [payload.notes, ...extrasNotes].filter(Boolean).join('\n');
      }

      const registerRes = await fetch(`${API_BASE}/api/v1/public/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!registerRes.ok) {
        const errData = await registerRes.json().catch(() => ({}));
        throw new Error(errData.detail || errMsg);
      }
      const responseData = await registerRes.json();
      setRequestNumber(responseData.request_number || '');
      setSubmitted(true);
      toast({ title: 'نجاح', description: texts.success_message || 'تم استلام طلبك بنجاح' });
    } catch (error: any) {
      toast({
        title: 'خطأ',
        description: error?.message || errMsg,
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  };

  const resetForm = () => {
    setSubmitted(false);
    setRequestNumber('');
    setImageFile(null);
    setImagePreview(null);
    setAgreedToTerms(false);
    const init: Record<string, any> = {};
    fieldsSorted.forEach((f) => {
      if (f.type === 'checkbox') init[f.id] = false;
      else if (f.type === 'multi_select') init[f.id] = [];
      else init[f.id] = '';
    });
    setValues(init);
  };

  if (booting) {
    return <div className="min-h-screen flex items-center justify-center text-gray-500" dir="rtl">جاري التحميل...</div>;
  }

  const bg = idn.background_color || '#F9FAFB';
  const primary = idn.primary_color || brand.primary_color || '#1F2937';
  const button = idn.button_color || brand.button_color || '#C89B3C';
  const fieldBg = idn.field_color || '#FFFFFF';
  const radius = Number(idn.border_radius) || 12;
  const formWidth = Number(idn.form_width) || 640;
  const logoSize = Number(idn.logo_size) || Number(brand.report_logo_size) || 72;
  const logoPos = idn.logo_position || 'center';
  const spacing = Number(brand.element_spacing) || 16;

  if (submitted) {
    return (
      <div className="min-h-screen flex items-center justify-center p-4" style={{ background: bg }} dir="rtl">
        <Toaster />
        <Card className="w-full shadow-xl border-0" style={{ maxWidth: formWidth, borderRadius: radius }}>
          <CardContent className="pt-10 pb-10 space-y-6 text-center">
            <div className="mx-auto w-20 h-20 bg-green-100 rounded-full flex items-center justify-center">
              <CheckCircle className="w-12 h-12 text-green-600" />
            </div>
            <h2 className="text-2xl font-bold" style={{ color: primary }}>
              {texts.success_page_title || 'تم إرسال الطلب'}
            </h2>
            <p className="text-gray-600">{texts.success_message || 'تم استلام طلبك بنجاح'}</p>
            {requestNumber && (
              <div className="rounded-lg p-4 border" style={{ borderColor: brand.secondary_color }}>
                <p className="text-sm font-medium">رقم طلبك:</p>
                <p className="text-2xl font-bold font-mono mt-1">{requestNumber}</p>
              </div>
            )}
            <Button onClick={resetForm} className="w-full text-white" style={{ background: button }}>
              {texts.new_request_button || 'إرسال طلب جديد'}
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen" style={{ background: bg }} dir="rtl">
      <Toaster />
      <header className="shadow-sm border-b text-white" style={{ background: primary }}>
        <div className="max-w-7xl mx-auto px-4 py-4 flex items-center justify-center gap-3">
          <img
            src={resolveAssetUrl(idn.logo || brand.system_logo)}
            alt="logo"
            className="object-contain bg-white/10 rounded"
            style={{ width: 40, height: 40 }}
          />
          <h1 className="text-lg font-bold">{texts.page_title || brand.system_name}</h1>
        </div>
      </header>

      <section className="py-8 px-4">
        <div
          className="mx-auto bg-white shadow-xl border overflow-hidden relative"
          style={{
            maxWidth: formWidth || Number(brand.form_width) || 640,
            borderRadius: radius || Number(brand.border_radius) || 12,
            fontFamily: brand.font_family,
          }}
        >
          <WatermarkLayer
            logoUrl={resolveAssetUrl(brand.system_logo || idn.logo)}
            brand={brand}
          />
          <div className="p-6 relative" style={{ gap: spacing, zIndex: 1 }}>
          <div
            className={`mb-6 ${logoPos === 'left' ? 'text-left' : logoPos === 'right' ? 'text-right' : 'text-center'}`}
            style={{ marginBottom: spacing }}
          >
            <img
              src={resolveAssetUrl(idn.logo || brand.system_logo)}
              alt="logo"
              className="object-contain inline-block"
              style={{ width: logoSize, height: logoSize }}
            />
            <h2
              className="font-bold mt-3"
              style={{ color: primary, fontSize: `var(--mfec-title-size, ${brand.page_title_size || 28}px)` }}
            >
              {idn.title}
            </h2>
            <p
              className="text-gray-600 mt-1"
              style={{ fontSize: `var(--mfec-subtitle-size, ${brand.subtitle_size || 16}px)` }}
            >
              {idn.subtitle || texts.description || 'عضوية مجانية بدون أي رسوم أو اشتراك لدعم تجار التجارة الإلكترونية في العراق.'}
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4" style={{ fontSize: `var(--mfec-text-size, ${brand.body_text_size || 14}px)` }}>
            {visibleFields.map((f) => {
              if (f.type === 'checkbox' || f.id === 'terms') {
                return (
                  <div key={f.id} className="flex items-start gap-3 bg-gray-50 p-4 rounded-lg">
                    <Checkbox
                      checked={!!values[f.id] || agreedToTerms}
                      onCheckedChange={(c) => {
                        setVal(f.id, !!c);
                        if (f.id === 'terms') setAgreedToTerms(!!c);
                      }}
                      className="mt-1"
                    />
                    <Label className="text-sm cursor-pointer leading-relaxed">{f.label}</Label>
                  </div>
                );
              }
              if (f.type === 'image_upload' || f.maps_to === 'image_key') {
                return (
                  <div key={f.id} className="space-y-2 text-right">
                    <Label>{f.label}{f.required ? ' *' : ''}</Label>
                    <div
                      onClick={() => fileInputRef.current?.click()}
                      className="border-2 border-dashed rounded-lg p-6 text-center cursor-pointer hover:opacity-90"
                      style={{ borderColor: brand.secondary_color }}
                    >
                      {imagePreview ? (
                        <img src={imagePreview} alt="معاينة" className="max-h-40 mx-auto rounded-lg object-cover" />
                      ) : (
                        <div className="space-y-2">
                          <Upload className="w-10 h-10 mx-auto text-gray-400" />
                          <p className="text-gray-600 text-sm">اضغط لرفع ملف</p>
                        </div>
                      )}
                    </div>
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept={f.type === 'file_upload' ? undefined : 'image/*'}
                      className="hidden"
                      onChange={(e) => handleImageChange(e, f.id)}
                    />
                  </div>
                );
              }
              if (f.type === 'textarea') {
                return (
                  <div key={f.id} className="space-y-2 text-right">
                    <Label>{f.label}{f.required ? ' *' : ''}</Label>
                    <Textarea
                      placeholder={f.placeholder}
                      value={values[f.id] || ''}
                      onChange={(e) => setVal(f.id, e.target.value)}
                      className="text-right"
                      style={{ background: fieldBg }}
                    />
                  </div>
                );
              }
              if (f.type === 'dropdown' || f.type === 'radio') {
                return (
                  <div key={f.id} className="space-y-2 text-right">
                    <Label>{f.label}{f.required ? ' *' : ''}</Label>
                    <Select value={values[f.id] || ''} onValueChange={(v) => setVal(f.id, v)}>
                      <SelectTrigger className="text-right" style={{ background: fieldBg }}>
                        <SelectValue placeholder={f.placeholder || 'اختر'} />
                      </SelectTrigger>
                      <SelectContent>
                        {(f.options || []).map((o) => (
                          <SelectItem key={o} value={o}>{o}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                );
              }
              if (f.type === 'multi_select') {
                const selected: string[] = Array.isArray(values[f.id]) ? values[f.id] : [];
                return (
                  <div key={f.id} className="space-y-2 text-right">
                    <Label>{f.label}{f.required ? ' *' : ''}</Label>
                    <div className="space-y-1 border rounded p-2" style={{ background: fieldBg }}>
                      {(f.options || []).map((o) => (
                        <label key={o} className="flex items-center gap-2 text-sm">
                          <Checkbox
                            checked={selected.includes(o)}
                            onCheckedChange={(c) => {
                              const next = c ? [...selected, o] : selected.filter((x) => x !== o);
                              setVal(f.id, next);
                            }}
                          />
                          {o}
                        </label>
                      ))}
                    </div>
                  </div>
                );
              }
              return (
                <div key={f.id} className="space-y-2 text-right">
                  <Label>{f.label}{f.required ? ' *' : ''}</Label>
                  <Input
                    type={f.type === 'number' ? 'number' : f.type === 'email' ? 'email' : f.type === 'date' ? 'date' : f.type === 'phone' ? 'tel' : 'text'}
                    placeholder={f.placeholder}
                    value={values[f.id] || ''}
                    onChange={(e) => setVal(f.id, e.target.value)}
                    className="text-right"
                    style={{ background: fieldBg }}
                    dir={f.type === 'phone' || f.type === 'email' ? 'ltr' : undefined}
                  />
                </div>
              );
            })}

            <Button type="submit" disabled={loading} className="w-full h-12 font-bold text-white" style={{ background: button, fontSize: `var(--mfec-button-size, ${brand.button_size || 16}px)` }}>
              {loading ? 'جاري الإرسال...' : (texts.submit_button || 'إرسال طلب الانضمام')}
            </Button>
          </form>
          </div>
        </div>
      </section>

      <footer className="border-t py-6 text-center text-sm text-gray-600 bg-white">
        <p>{brand.footer_text}</p>
        <p className="mt-1 font-medium">{brand.company_name}</p>
        <p className="mt-1">{brand.website} | {brand.email} | {brand.phone}</p>
        <p className="mt-2 text-xs text-gray-500">{brand.copyright}</p>
      </footer>
    </div>
  );
}
