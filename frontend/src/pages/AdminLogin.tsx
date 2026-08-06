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

export default function AdminLogin() {
  const { toast } = useToast();
  const navigate = useNavigate();
  const { brand, resolveAssetUrl } = useBrand();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
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
              تسجيل دخول الإدارة
            </h1>
            <p className="text-sm text-gray-500">{brand.system_name}</p>
            <p className="text-xs font-semibold" style={{ color: brand.secondary_color }}>
              {brand.org_abbr}
            </p>
          </div>

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
          </form>
          <p className="text-center text-xs text-gray-400">{brand.footer_text_secondary}</p>
        </CardContent>
      </Card>
    </div>
  );
}
