import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Checkbox } from '@/components/ui/checkbox';
import { useToast } from '@/hooks/use-toast';
import { Toaster } from '@/components/ui/toaster';
import { client } from '@/lib/localApi';
import { ROUTES } from '@/lib/routes';
import { ArrowRight, Eye, Plus, RotateCcw, Save, Trash2 } from 'lucide-react';

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

const FIELD_TYPES = [
  'text', 'textarea', 'number', 'phone', 'email', 'date',
  'dropdown', 'radio', 'checkbox', 'multi_select', 'image_upload', 'file_upload',
];

const emptySettings = (): FormSettings => ({
  identity: {
    logo: '/brand/mfec-logo.png',
    image_type: 'logo',
    title: 'طلب انضمام لتجمع تجار التجارة الإلكترونية',
    subtitle: 'عضوية مجانية بدون أي رسوم أو اشتراك لدعم تجار التجارة الإلكترونية في العراق.',
    primary_color: '#1F2937',
    secondary_color: '#C89B3C',
    background_color: '#F9FAFB',
    button_color: '#C89B3C',
    field_color: '#FFFFFF',
    logo_size: 72,
    form_width: 640,
    border_radius: 12,
    logo_position: 'center',
    banner_width: '100%',
    banner_height: 180,
    object_fit: 'cover',
  },
  texts: {
    page_title: 'بوابة الانضمام',
    description: 'عضوية مجانية بدون أي رسوم أو اشتراك لدعم تجار التجارة الإلكترونية في العراق.',
    submit_button: 'إرسال طلب الانضمام',
    success_message: 'تم استلام طلبك بنجاح',
    error_message: 'حدث خطأ أثناء الإرسال',
    success_page_title: 'تم إرسال الطلب',
    new_request_button: 'إرسال طلب جديد',
  },
  fields: [],
});

export default function FormSettingsPage() {
  const navigate = useNavigate();
  const { toast } = useToast();
  const [form, setForm] = useState<FormSettings>(emptySettings());
  const [saving, setSaving] = useState(false);
  const [authOk, setAuthOk] = useState(false);
  const [preview, setPreview] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);

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
        if (!check.data?.is_super_admin && !me.data.is_super_admin && !perms.manage_registration_form_settings) {
          toast({ title: 'غير مسموح', description: 'ليس لديك صلاحية إعدادات الاستمارة', variant: 'destructive' });
          navigate(ROUTES.ADMIN);
          return;
        }
        const res = await client.apiCall.invoke({
          url: '/api/v1/admin/app-settings/registration-form',
          method: 'GET',
          data: {},
        });
        setForm({ ...emptySettings(), ...res.data, fields: res.data?.fields || [] });
        setAuthOk(true);
      } catch {
        navigate(ROUTES.ADMIN_LOGIN);
      }
    };
    boot();
  }, [navigate, toast]);

  const fieldsSorted = useMemo(
    () => [...(form.fields || [])].sort((a, b) => (a.order || 0) - (b.order || 0)),
    [form.fields]
  );
  const selected = fieldsSorted.find((f) => f.id === selectedId) || null;

  const updateField = (id: string, patch: Partial<FormField>) => {
    setForm((prev) => ({
      ...prev,
      fields: prev.fields.map((f) => (f.id === id ? { ...f, ...patch } : f)),
    }));
  };

  const addField = () => {
    const id = `custom_${Date.now()}`;
    const nextOrder = (fieldsSorted[fieldsSorted.length - 1]?.order || 0) + 1;
    const field: FormField = {
      id,
      type: 'text',
      label: 'حقل جديد',
      placeholder: '',
      required: false,
      visible: true,
      order: nextOrder,
      options: [],
      maps_to: null,
    };
    setForm((prev) => ({ ...prev, fields: [...prev.fields, field] }));
    setSelectedId(id);
  };

  const removeField = (id: string) => {
    const f = form.fields.find((x) => x.id === id);
    if (f?.maps_to) {
      toast({ title: 'تنبيه', description: 'الحقول الأساسية تُخفى بدل الحذف', variant: 'destructive' });
      updateField(id, { visible: false });
      return;
    }
    setForm((prev) => ({ ...prev, fields: prev.fields.filter((x) => x.id !== id) }));
    if (selectedId === id) setSelectedId(null);
  };

  const moveField = (id: string, dir: -1 | 1) => {
    const list = [...fieldsSorted];
    const idx = list.findIndex((f) => f.id === id);
    const j = idx + dir;
    if (idx < 0 || j < 0 || j >= list.length) return;
    const a = list[idx].order;
    const b = list[j].order;
    updateField(list[idx].id, { order: b });
    updateField(list[j].id, { order: a });
  };

  const save = async () => {
    setSaving(true);
    try {
      await client.apiCall.invoke({
        url: '/api/v1/admin/app-settings/registration-form',
        method: 'PUT',
        data: { settings: form },
      });
      toast({ title: 'تم الحفظ', description: 'تم تطبيق إعدادات الاستمارة على بوابة الانضمام' });
    } catch (e: any) {
      toast({ title: 'خطأ', description: e?.message || 'فشل الحفظ', variant: 'destructive' });
    } finally {
      setSaving(false);
    }
  };

  const reset = async () => {
    if (!confirm('استعادة التصميم الافتراضي؟')) return;
    setSaving(true);
    try {
      const res = await client.apiCall.invoke({
        url: '/api/v1/admin/app-settings/registration-form/reset',
        method: 'POST',
        data: {},
      });
      setForm({ ...emptySettings(), ...res.data?.settings });
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

  const idn = form.identity || {};

  return (
    <div className="min-h-screen" style={{ background: idn.background_color || '#F9FAFB' }} dir="rtl">
      <Toaster />
      <header className="sticky top-0 z-10 text-white border-b" style={{ background: idn.primary_color || '#1F2937' }}>
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between gap-2 flex-wrap">
          <div>
            <h1 className="font-bold">إعدادات استمارة التسجيل</h1>
            <p className="text-xs opacity-80">تخصيص بوابة الانضمام</p>
          </div>
          <div className="flex gap-2 flex-wrap">
            <Button variant="secondary" size="sm" onClick={() => navigate(ROUTES.ADMIN)} className="gap-1">
              <ArrowRight className="w-4 h-4" /> رجوع
            </Button>
            <Button size="sm" variant="outline" className="bg-white/10 text-white border-white/30 gap-1" onClick={() => setPreview((v) => !v)}>
              <Eye className="w-4 h-4" /> {preview ? 'إخفاء المعاينة' : 'معاينة'}
            </Button>
            <Button size="sm" variant="outline" className="bg-white/10 text-white border-white/30 gap-1" onClick={reset}>
              <RotateCcw className="w-4 h-4" /> افتراضي
            </Button>
            <Button size="sm" disabled={saving} onClick={save} style={{ background: idn.button_color || '#C89B3C' }} className="text-white gap-1">
              <Save className="w-4 h-4" /> حفظ
            </Button>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto p-4 grid lg:grid-cols-2 gap-4">
        <div className="space-y-4">
          <Card>
            <CardHeader><CardTitle className="text-right text-base">الهوية والنصوص</CardTitle></CardHeader>
            <CardContent className="grid sm:grid-cols-2 gap-3 text-right">
              {[
                ['title', 'عنوان الاستمارة'],
                ['subtitle', 'النص التعريفي'],
                ['image_type', 'نوع الصورة (logo أو banner)'],
                ['primary_color', 'اللون الرئيسي'],
                ['secondary_color', 'اللون الثانوي'],
                ['background_color', 'لون الخلفية'],
                ['button_color', 'لون الأزرار'],
                ['field_color', 'لون الحقول'],
                ['logo', 'رابط الشعار / البانر'],
                ['logo_size', 'حجم الشعار (Logo)'],
                ['banner_width', 'عرض البانر (مثلاً 100% أو 800)'],
                ['banner_height', 'ارتفاع البانر'],
                ['object_fit', 'طريقة العرض (contain أو cover)'],
                ['form_width', 'عرض الاستمارة'],
                ['border_radius', 'نصف قطر الزوايا'],
                ['logo_position', 'مكان الشعار (center/right/left)'],
              ].map(([key, label]) => (
                <div key={key} className="space-y-1">
                  <Label>{label}</Label>
                  <Input
                    value={String(idn[key] ?? '')}
                    onChange={(e) =>
                      setForm((prev) => ({
                        ...prev,
                        identity: { ...prev.identity, [key]: e.target.value },
                      }))
                    }
                    className="text-right"
                  />
                </div>
              ))}
              {Object.entries(form.texts || {}).map(([key, val]) => (
                <div key={key} className="space-y-1 sm:col-span-2">
                  <Label>{key}</Label>
                  <Input
                    value={val}
                    onChange={(e) =>
                      setForm((prev) => ({
                        ...prev,
                        texts: { ...prev.texts, [key]: e.target.value },
                      }))
                    }
                    className="text-right"
                  />
                </div>
              ))}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="text-right text-base">الحقول</CardTitle>
              <Button size="sm" onClick={addField} className="gap-1"><Plus className="w-4 h-4" /> حقل جديد</Button>
            </CardHeader>
            <CardContent className="space-y-2">
              {fieldsSorted.map((f) => (
                <div
                  key={f.id}
                  className={`border rounded-lg p-2 flex items-center justify-between gap-2 cursor-pointer ${selectedId === f.id ? 'border-[#C89B3C] bg-amber-50' : ''}`}
                  onClick={() => setSelectedId(f.id)}
                >
                  <div className="text-right">
                    <div className="font-medium text-sm">{f.label}</div>
                    <div className="text-xs text-gray-500">{f.type} · order {f.order} {f.visible ? '' : '· مخفي'}</div>
                  </div>
                  <div className="flex gap-1">
                    <Button size="sm" variant="outline" onClick={(e) => { e.stopPropagation(); moveField(f.id, -1); }}>↑</Button>
                    <Button size="sm" variant="outline" onClick={(e) => { e.stopPropagation(); moveField(f.id, 1); }}>↓</Button>
                    <Button size="sm" variant="ghost" className="text-red-600" onClick={(e) => { e.stopPropagation(); removeField(f.id); }}>
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>

          {selected && (
            <Card>
              <CardHeader><CardTitle className="text-right text-base">تحرير الحقل</CardTitle></CardHeader>
              <CardContent className="grid sm:grid-cols-2 gap-3 text-right">
                <div className="space-y-1"><Label>الاسم</Label>
                  <Input value={selected.label} onChange={(e) => updateField(selected.id, { label: e.target.value })} className="text-right" />
                </div>
                <div className="space-y-1"><Label>Placeholder</Label>
                  <Input value={selected.placeholder || ''} onChange={(e) => updateField(selected.id, { placeholder: e.target.value })} className="text-right" />
                </div>
                <div className="space-y-1"><Label>النوع</Label>
                  <Select value={selected.type} onValueChange={(v) => updateField(selected.id, { type: v })}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {FIELD_TYPES.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1"><Label>الترتيب</Label>
                  <Input type="number" value={selected.order} onChange={(e) => updateField(selected.id, { order: Number(e.target.value) || 0 })} />
                </div>
                <label className="flex items-center gap-2 text-sm">
                  <Checkbox checked={selected.visible} onCheckedChange={(v) => updateField(selected.id, { visible: !!v })} /> ظاهر
                </label>
                <label className="flex items-center gap-2 text-sm">
                  <Checkbox checked={selected.required} onCheckedChange={(v) => updateField(selected.id, { required: !!v })} /> إجباري
                </label>
                {(selected.type === 'dropdown' || selected.type === 'radio' || selected.type === 'multi_select') && (
                  <div className="sm:col-span-2 space-y-1">
                    <Label>الخيارات (سطر لكل خيار)</Label>
                    <Textarea
                      className="text-right"
                      value={(selected.options || []).join('\n')}
                      onChange={(e) => updateField(selected.id, { options: e.target.value.split('\n').map((x) => x.trim()).filter(Boolean) })}
                    />
                  </div>
                )}
              </CardContent>
            </Card>
          )}
        </div>

        {preview && (
          <Card className="h-fit sticky top-20">
            <CardHeader><CardTitle className="text-right text-base">معاينة الاستمارة</CardTitle></CardHeader>
            <CardContent>
              <div
                className="mx-auto p-4 shadow border bg-white"
                style={{
                  maxWidth: Number(idn.form_width) || 640,
                  borderRadius: Number(idn.border_radius) || 12,
                }}
              >
                <div className={`mb-4 ${idn.logo_position === 'left' ? 'text-left' : idn.logo_position === 'right' ? 'text-right' : 'text-center'}`}>
                  {(idn.image_type || 'logo') === 'banner' ? (
                    <div
                      className="w-full overflow-hidden mb-3 bg-gray-100"
                      style={{
                        width: String(idn.banner_width || '100%').includes('%') ? idn.banner_width : Number(idn.banner_width) || '100%',
                        height: Number(idn.banner_height) || 180,
                        borderRadius: Number(idn.border_radius) || 12,
                      }}
                    >
                      <img
                        src={idn.logo || '/brand/mfec-logo.png'}
                        alt="banner"
                        className="w-full h-full"
                        style={{ objectFit: (idn.object_fit === 'contain' ? 'contain' : 'cover') as any }}
                      />
                    </div>
                  ) : (
                    <img src={idn.logo || '/brand/mfec-logo.png'} alt="logo" style={{ width: Number(idn.logo_size) || 72, height: Number(idn.logo_size) || 72 }} className="object-contain inline-block" />
                  )}
                  <h2 className="font-bold mt-2" style={{ color: idn.primary_color }}>{idn.title}</h2>
                  <p className="text-sm text-gray-600">{idn.subtitle}</p>
                </div>
                <div className="space-y-3">
                  {fieldsSorted.filter((f) => f.visible).map((f) => (
                    <div key={f.id} className="text-right space-y-1">
                      <Label>{f.label}{f.required ? ' *' : ''}</Label>
                      {f.type === 'textarea' ? (
                        <Textarea placeholder={f.placeholder} style={{ background: idn.field_color }} />
                      ) : f.type === 'dropdown' ? (
                        <Select>
                          <SelectTrigger style={{ background: idn.field_color }}><SelectValue placeholder={f.placeholder || 'اختر'} /></SelectTrigger>
                          <SelectContent>
                            {(f.options || []).map((o) => <SelectItem key={o} value={o}>{o}</SelectItem>)}
                          </SelectContent>
                        </Select>
                      ) : f.type === 'checkbox' ? (
                        <label className="flex items-center gap-2 text-sm"><Checkbox /> {f.label}</label>
                      ) : f.type === 'image_upload' || f.type === 'file_upload' ? (
                        <div className="border border-dashed rounded p-4 text-center text-sm text-gray-500">رفع ملف</div>
                      ) : (
                        <Input placeholder={f.placeholder} style={{ background: idn.field_color }} />
                      )}
                    </div>
                  ))}
                  <Button className="w-full text-white" style={{ background: idn.button_color || '#C89B3C' }}>
                    {form.texts?.submit_button || 'إرسال'}
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        )}
      </main>
    </div>
  );
}
