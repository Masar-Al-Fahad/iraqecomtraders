import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent } from '@/components/ui/card';
import { useToast } from '@/hooks/use-toast';
import { Toaster } from '@/components/ui/toaster';
import { client, localAuth } from '@/lib/localApi';
import { useNavigate } from 'react-router-dom';
import { useBrand } from '@/lib/brand';
import { ROUTES } from '@/lib/routes';

type Mode = 'login' | 'forgot' | 'otp';

export default function AdminLogin() {
  const { toast } = useToast();
  const navigate = useNavigate();
  const { brand, resolveAssetUrl } = useBrand();
  const [mode, setMode] = useState<Mode>('login');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [channel, setChannel] = useState<'auto' | 'email' | 'phone'>('auto');
  const [otp, setOtp] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [masked, setMasked] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (localAuth.isLoggedIn()) {
      navigate(ROUTES.ADMIN, { replace: true });
    }
  }, [navigate]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password) {
      toast({
        title: 'خطأ',
        description: 'يرجى إدخال اسم المستخدم وكلمة المرور',
        variant: 'destructive',
      });
      return;
    }
    setLoading(true);
    try {
      await client.auth.login(username.trim(), password);
      toast({ title: 'تم الدخول', description: 'مرحباً بك في لوحة الإدارة' });
      navigate(ROUTES.ADMIN, { replace: true });
    } catch (error: any) {
      toast({
        title: 'فشل تسجيل الدخول',
        description: error?.message || 'اسم المستخدم أو كلمة المرور غير صحيحة',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  };

  const requestOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim()) {
      toast({ title: 'خطأ', description: 'أدخل اسم المستخدم', variant: 'destructive' });
      return;
    }
    setLoading(true);
    try {
      const res = await client.auth.requestPasswordReset(username.trim(), channel === 'auto' ? undefined : channel);
      setMasked(res.destination_masked || '');
      setMode('otp');
      toast({
        title: 'تم إرسال الطلب',
        description: res.message || 'إن وُجد حساب مرتبط سيتم إرسال رمز التحقق.',
      });
    } catch (error: any) {
      toast({ title: 'تعذر الطلب', description: error?.message || 'حاول لاحقًا', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  const confirmReset = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!otp.trim() || newPassword.length < 6 || newPassword !== confirmPassword) {
      toast({
        title: 'تحقق من الحقول',
        description: 'أدخل OTP وكلمة مرور متطابقة لا تقل عن 6 أحرف',
        variant: 'destructive',
      });
      return;
    }
    setLoading(true);
    try {
      const res = await client.auth.confirmPasswordReset(username.trim(), otp.trim(), newPassword);
      toast({ title: 'تم التحديث', description: res.message || 'يمكنك تسجيل الدخول الآن' });
      setMode('login');
      setPassword('');
      setOtp('');
      setNewPassword('');
      setConfirmPassword('');
    } catch (error: any) {
      toast({ title: 'فشل التأكيد', description: error?.message || 'رمز غير صالح', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="min-h-screen flex items-center justify-center p-4"
      dir="rtl"
      style={{
        background: `linear-gradient(145deg, ${brand.primary_color} 0%, #111827 55%, ${brand.secondary_color}33 100%)`,
      }}
    >
      <Toaster />
      <Card className="w-full max-w-sm shadow-2xl border-0 overflow-hidden">
        <div className="h-1.5" style={{ background: brand.secondary_color }} />
        <CardContent className="pt-10 pb-10 space-y-6">
          <div className="text-center space-y-3">
            <img
              src={resolveAssetUrl(brand.system_logo)}
              alt="MFEC"
              className="mx-auto w-20 h-20 object-contain"
            />
            <h1 className="text-xl font-bold" style={{ color: brand.primary_color }}>
              {mode === 'login' ? 'تسجيل دخول الإدارة' : 'استعادة كلمة المرور'}
            </h1>
            <p className="text-sm text-gray-500">{brand.system_name}</p>
            <p className="text-xs font-semibold" style={{ color: brand.secondary_color }}>
              {brand.org_abbr}
            </p>
          </div>

          {mode === 'login' && (
            <form onSubmit={handleSubmit} className="space-y-4 text-right">
              <div className="space-y-2">
                <Label htmlFor="username">اسم المستخدم</Label>
                <Input
                  id="username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="text-right"
                  autoComplete="username"
                  disabled={loading}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="password">كلمة المرور</Label>
                <Input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="text-right"
                  autoComplete="current-password"
                  disabled={loading}
                />
              </div>
              <Button
                type="submit"
                className="w-full text-white font-bold"
                disabled={loading}
                style={{ background: brand.button_color || brand.secondary_color }}
              >
                {loading ? 'جاري الدخول...' : 'دخول'}
              </Button>
              <button
                type="button"
                className="w-full text-sm text-slate-600 underline"
                onClick={() => setMode('forgot')}
              >
                نسيت كلمة المرور؟
              </button>
            </form>
          )}

          {mode === 'forgot' && (
            <form onSubmit={requestOtp} className="space-y-4 text-right">
              <p className="text-sm text-slate-600">
                أدخل اسم المستخدم واختر قناة الاسترداد المسجّلة (بريد أو هاتف). لن نكشف إن كان الحساب موجودًا.
              </p>
              <div className="space-y-2">
                <Label>اسم المستخدم</Label>
                <Input value={username} onChange={(e) => setUsername(e.target.value)} disabled={loading} />
              </div>
              <div className="space-y-2">
                <Label>قناة الاسترداد</Label>
                <select
                  className="h-10 w-full border rounded-md px-3"
                  value={channel}
                  onChange={(e) => setChannel(e.target.value as typeof channel)}
                >
                  <option value="auto">تلقائي</option>
                  <option value="email">البريد الإلكتروني</option>
                  <option value="phone">الهاتف</option>
                </select>
              </div>
              <Button type="submit" className="w-full" disabled={loading} style={{ background: brand.button_color || brand.secondary_color }}>
                {loading ? 'جاري الإرسال...' : 'إرسال رمز التحقق'}
              </Button>
              <button type="button" className="w-full text-sm underline" onClick={() => setMode('login')}>
                العودة لتسجيل الدخول
              </button>
            </form>
          )}

          {mode === 'otp' && (
            <form onSubmit={confirmReset} className="space-y-4 text-right">
              <p className="text-sm text-slate-600">
                أدخل الرمز المرسل{masked ? ` إلى ${masked}` : ''} ثم اختر كلمة مرور جديدة.
              </p>
              <div className="space-y-2">
                <Label>رمز OTP</Label>
                <Input dir="ltr" value={otp} onChange={(e) => setOtp(e.target.value)} disabled={loading} />
              </div>
              <div className="space-y-2">
                <Label>كلمة المرور الجديدة</Label>
                <Input type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} disabled={loading} />
              </div>
              <div className="space-y-2">
                <Label>تأكيد كلمة المرور</Label>
                <Input type="password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} disabled={loading} />
              </div>
              <Button type="submit" className="w-full" disabled={loading} style={{ background: brand.button_color || brand.secondary_color }}>
                {loading ? 'جاري الحفظ...' : 'تحديث كلمة المرور'}
              </Button>
              <button type="button" className="w-full text-sm underline" onClick={() => setMode('forgot')}>
                إعادة إرسال الرمز
              </button>
            </form>
          )}
          <p className="text-center text-xs text-gray-400">{brand.footer_text_secondary}</p>
        </CardContent>
      </Card>
    </div>
  );
}
