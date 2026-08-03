import { useState, useEffect, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Checkbox } from '@/components/ui/checkbox';
import { Switch } from '@/components/ui/switch';
import { useToast } from '@/hooks/use-toast';
import { Toaster } from '@/components/ui/toaster';
import { client } from '@/lib/localApi';
import { useNavigate } from 'react-router-dom';
import {
  ArrowRight, Users, UserPlus, Pencil, Trash2, LogOut, Shield, Store,
} from 'lucide-react';

interface Permissions {
  view: boolean;
  add: boolean;
  edit: boolean;
  delete: boolean;
  export: boolean;
  manage_users: boolean;
  manage_brand_settings: boolean;
  manage_registration_form_settings: boolean;
}

interface PanelUser {
  id: number;
  username: string;
  permissions: Permissions;
  is_active: boolean;
  created_at: string | null;
  updated_at: string | null;
}

const emptyPermissions = (): Permissions => ({
  view: false,
  add: false,
  edit: false,
  delete: false,
  export: false,
  manage_users: false,
  manage_brand_settings: false,
  manage_registration_form_settings: false,
});

const permissionLabels: { key: keyof Permissions; label: string }[] = [
  { key: 'view', label: 'عرض' },
  { key: 'add', label: 'إضافة' },
  { key: 'edit', label: 'تعديل' },
  { key: 'delete', label: 'حذف' },
  { key: 'export', label: 'تصدير' },
  { key: 'manage_users', label: 'إدارة المستخدمين' },
  { key: 'manage_brand_settings', label: 'إعدادات الهوية' },
  { key: 'manage_registration_form_settings', label: 'إعدادات استمارة التسجيل' },
];

export default function UsersManagement() {
  const { toast } = useToast();
  const navigate = useNavigate();
  const [authState, setAuthState] = useState<'loading' | 'unauthorized' | 'authorized'>('loading');
  const [loading, setLoading] = useState(true);
  const [users, setUsers] = useState<PanelUser[]>([]);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<PanelUser | null>(null);
  const [saving, setSaving] = useState(false);
  const [formUsername, setFormUsername] = useState('');
  const [formPassword, setFormPassword] = useState('');
  const [formPermissions, setFormPermissions] = useState<Permissions>(emptyPermissions());
  const [formActive, setFormActive] = useState(true);

  useEffect(() => {
    const checkAuth = async () => {
      try {
        const res = await client.auth.me();
        if (!res?.data) {
          setAuthState('unauthorized');
          return;
        }
        try {
          const check = await client.apiCall.invoke({
            url: '/api/v1/admin/registrations/check-admin',
            method: 'GET',
            data: {},
          });
          const perms = check.data?.permissions || {};
          const isSuper = check.data?.is_super_admin || res.data?.is_super_admin;
          if (!isSuper && !perms.manage_users) {
            setAuthState('unauthorized');
            return;
          }
          setAuthState('authorized');
        } catch {
          setAuthState('unauthorized');
        }
      } catch {
        setAuthState('unauthorized');
      }
    };
    checkAuth();
  }, []);

  const fetchUsers = useCallback(async () => {
    setLoading(true);
    try {
      const response = await client.apiCall.invoke({
        url: '/api/v1/admin/users',
        method: 'GET',
        data: {},
      });
      setUsers(response.data.items || []);
    } catch (error: any) {
      if (error?.status === 401 || error?.response?.status === 401 || error?.status === 403 || error?.response?.status === 403) {
        setAuthState('unauthorized');
        return;
      }
      toast({ title: 'خطأ', description: 'فشل في تحميل المستخدمين', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    if (authState === 'authorized') {
      fetchUsers();
    }
  }, [authState, fetchUsers]);

  const handleLogin = () => {
    client.auth.toLogin();
  };

  const handleLogout = async () => {
    try {
      await client.auth.logout();
    } catch {
      // silent
    }
    setAuthState('unauthorized');
    navigate('/admin/login');
  };

  const openCreateDialog = () => {
    setEditingUser(null);
    setFormUsername('');
    setFormPassword('');
    setFormPermissions(emptyPermissions());
    setFormActive(true);
    setDialogOpen(true);
  };

  const openEditDialog = (user: PanelUser) => {
    setEditingUser(user);
    setFormUsername(user.username);
    setFormPassword('');
    setFormPermissions({ ...emptyPermissions(), ...user.permissions });
    setFormActive(user.is_active);
    setDialogOpen(true);
  };

  const togglePermission = (key: keyof Permissions) => {
    setFormPermissions((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const saveUser = async () => {
    if (!formUsername.trim()) {
      toast({ title: 'خطأ', description: 'يرجى إدخال اسم المستخدم', variant: 'destructive' });
      return;
    }
    if (!editingUser && !formPassword.trim()) {
      toast({ title: 'خطأ', description: 'يرجى إدخال كلمة المرور', variant: 'destructive' });
      return;
    }

    setSaving(true);
    try {
      if (editingUser) {
        const payload: Record<string, unknown> = {
          username: formUsername.trim(),
          permissions: formPermissions,
          is_active: formActive,
        };
        if (formPassword.trim()) {
          payload.password = formPassword;
        }
        await client.apiCall.invoke({
          url: `/api/v1/admin/users/${editingUser.id}`,
          method: 'PUT',
          data: payload,
        });
        toast({ title: 'تم التحديث', description: 'تم تحديث المستخدم بنجاح' });
      } else {
        await client.apiCall.invoke({
          url: '/api/v1/admin/users',
          method: 'POST',
          data: {
            username: formUsername.trim(),
            password: formPassword,
            permissions: formPermissions,
            is_active: formActive,
          },
        });
        toast({ title: 'تمت الإضافة', description: 'تم إنشاء المستخدم بنجاح' });
      }
      setDialogOpen(false);
      fetchUsers();
    } catch (error: any) {
      const detail = error?.response?.data?.detail || error?.data?.detail || 'فشل في حفظ المستخدم';
      toast({ title: 'خطأ', description: String(detail), variant: 'destructive' });
    } finally {
      setSaving(false);
    }
  };

  const deleteUser = async (user: PanelUser) => {
    if (!confirm(`هل أنت متأكد من حذف المستخدم "${user.username}"؟`)) return;
    try {
      await client.apiCall.invoke({
        url: `/api/v1/admin/users/${user.id}`,
        method: 'DELETE',
        data: {},
      });
      toast({ title: 'تم الحذف', description: 'تم حذف المستخدم بنجاح' });
      fetchUsers();
    } catch {
      toast({ title: 'خطأ', description: 'فشل في حذف المستخدم', variant: 'destructive' });
    }
  };

  const toggleActive = async (user: PanelUser) => {
    try {
      await client.apiCall.invoke({
        url: `/api/v1/admin/users/${user.id}/toggle-active`,
        method: 'PATCH',
        data: {},
      });
      toast({
        title: 'تم التحديث',
        description: user.is_active ? 'تم تعطيل المستخدم' : 'تم تفعيل المستخدم',
      });
      fetchUsers();
    } catch {
      toast({ title: 'خطأ', description: 'فشل في تغيير حالة المستخدم', variant: 'destructive' });
    }
  };

  const activePermissionsLabel = (perms: Permissions) => {
    const labels = permissionLabels.filter((p) => perms[p.key]).map((p) => p.label);
    return labels.length ? labels.join('، ') : 'لا توجد';
  };

  if (authState === 'loading') {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center space-y-4">
          <svg className="animate-spin h-10 w-10 mx-auto text-primary" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg>
          <p className="text-gray-500">جاري التحقق من الصلاحيات...</p>
        </div>
      </div>
    );
  }

  if (authState === 'unauthorized') {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
        <Toaster />
        <Card className="w-full max-w-sm text-center shadow-xl border-0">
          <CardContent className="pt-10 pb-10 space-y-6">
            <div className="mx-auto w-16 h-16 bg-red-100 rounded-full flex items-center justify-center">
              <Shield className="w-8 h-8 text-red-600" />
            </div>
            <h2 className="text-xl font-bold text-gray-800">لوحة الإدارة محمية</h2>
            <p className="text-gray-600 text-sm">
              هذه اللوحة مخصصة للمدير المعتمد فقط. يرجى تسجيل الدخول بالحساب المصرح له.
            </p>
            <Button onClick={handleLogin} className="w-full bg-primary text-white">
              تسجيل الدخول
            </Button>
            <Button variant="outline" onClick={() => navigate('/')} className="w-full">
              العودة للرئيسية
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <Toaster />
      <header className="bg-white shadow-sm border-b sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-primary rounded-lg flex items-center justify-center">
              <Store className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-gray-800">إدارة المستخدمين</h1>
              <p className="text-xs text-gray-500">إنشاء وتعديل صلاحيات المستخدمين</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button size="sm" onClick={openCreateDialog} className="flex items-center gap-1 bg-primary text-white">
              <UserPlus className="w-4 h-4" /> مستخدم جديد
            </Button>
            <Button variant="outline" size="sm" onClick={() => navigate('/admin')} className="flex items-center gap-2">
              <ArrowRight className="w-4 h-4" /> لوحة الإدارة
            </Button>
            <Button variant="ghost" size="sm" onClick={handleLogout} className="flex items-center gap-1 text-red-600 hover:bg-red-50" title="تسجيل الخروج">
              <LogOut className="w-4 h-4" />
            </Button>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 py-6 space-y-6">
        <Card className="border-0 shadow-sm">
          <CardContent className="p-4">
            <div className="flex items-center gap-2 mb-4">
              <Users className="w-5 h-5 text-primary" />
              <h2 className="font-bold text-gray-800">قائمة المستخدمين ({users.length})</h2>
            </div>

            {loading ? (
              <div className="py-12 text-center text-gray-500">جاري التحميل...</div>
            ) : users.length === 0 ? (
              <div className="py-12 text-center text-gray-500">لا يوجد مستخدمون بعد. أنشئ مستخدماً جديداً للبدء.</div>
            ) : (
              <>
                <div className="hidden md:block overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="text-right font-bold">#</TableHead>
                        <TableHead className="text-right font-bold">اسم المستخدم</TableHead>
                        <TableHead className="text-right font-bold">الصلاحيات</TableHead>
                        <TableHead className="text-right font-bold">الحالة</TableHead>
                        <TableHead className="text-right font-bold">إجراءات</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {users.map((user) => (
                        <TableRow key={user.id}>
                          <TableCell>{user.id}</TableCell>
                          <TableCell className="font-medium">{user.username}</TableCell>
                          <TableCell className="text-sm text-gray-600 max-w-xs">{activePermissionsLabel(user.permissions)}</TableCell>
                          <TableCell>
                            {user.is_active ? (
                              <Badge className="bg-emerald-100 text-emerald-800 hover:bg-emerald-100">مفعّل</Badge>
                            ) : (
                              <Badge className="bg-gray-200 text-gray-700 hover:bg-gray-200">معطّل</Badge>
                            )}
                          </TableCell>
                          <TableCell>
                            <div className="flex items-center gap-1">
                              <Button variant="ghost" size="sm" onClick={() => openEditDialog(user)} title="تعديل">
                                <Pencil className="w-4 h-4" />
                              </Button>
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => toggleActive(user)}
                                title={user.is_active ? 'تعطيل' : 'تفعيل'}
                                className={user.is_active ? 'text-orange-600' : 'text-emerald-600'}
                              >
                                <Switch checked={user.is_active} className="pointer-events-none scale-75" />
                              </Button>
                              <Button variant="ghost" size="sm" onClick={() => deleteUser(user)} title="حذف" className="text-red-600 hover:bg-red-50">
                                <Trash2 className="w-4 h-4" />
                              </Button>
                            </div>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>

                <div className="md:hidden space-y-3">
                  {users.map((user) => (
                    <div key={user.id} className="border rounded-lg p-3 space-y-2 text-right">
                      <div className="flex items-center justify-between">
                        <span className="font-bold">{user.username}</span>
                        {user.is_active ? (
                          <Badge className="bg-emerald-100 text-emerald-800 hover:bg-emerald-100">مفعّل</Badge>
                        ) : (
                          <Badge className="bg-gray-200 text-gray-700 hover:bg-gray-200">معطّل</Badge>
                        )}
                      </div>
                      <p className="text-xs text-gray-500">{activePermissionsLabel(user.permissions)}</p>
                      <div className="flex gap-2 pt-1">
                        <Button size="sm" variant="outline" onClick={() => openEditDialog(user)} className="flex items-center gap-1">
                          <Pencil className="w-3 h-3" /> تعديل
                        </Button>
                        <Button size="sm" variant="outline" onClick={() => toggleActive(user)}>
                          {user.is_active ? 'تعطيل' : 'تفعيل'}
                        </Button>
                        <Button size="sm" variant="destructive" onClick={() => deleteUser(user)} className="flex items-center gap-1">
                          <Trash2 className="w-3 h-3" /> حذف
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}
          </CardContent>
        </Card>
      </main>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="text-right">
              {editingUser ? 'تعديل المستخدم' : 'إنشاء مستخدم جديد'}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4 text-right">
            <div className="space-y-2">
              <Label className="text-sm font-medium">اسم المستخدم *</Label>
              <Input
                value={formUsername}
                onChange={(e) => setFormUsername(e.target.value)}
                className="text-right"
                placeholder="أدخل اسم المستخدم"
              />
            </div>
            <div className="space-y-2">
              <Label className="text-sm font-medium">
                كلمة المرور {editingUser ? '(اتركها فارغة للإبقاء عليها)' : '*'}
              </Label>
              <Input
                type="password"
                value={formPassword}
                onChange={(e) => setFormPassword(e.target.value)}
                className="text-right"
                placeholder={editingUser ? 'كلمة مرور جديدة (اختياري)' : 'أدخل كلمة المرور'}
              />
            </div>
            <div className="space-y-2">
              <Label className="text-sm font-medium">الصلاحيات</Label>
              <div className="grid grid-cols-2 gap-3 bg-gray-50 p-3 rounded-lg">
                {permissionLabels.map(({ key, label }) => (
                  <label key={key} className="flex items-center gap-2 cursor-pointer">
                    <Checkbox
                      checked={formPermissions[key]}
                      onCheckedChange={() => togglePermission(key)}
                    />
                    <span className="text-sm">{label}</span>
                  </label>
                ))}
              </div>
            </div>
            <div className="flex items-center justify-between bg-gray-50 p-3 rounded-lg">
              <Label className="text-sm font-medium">تفعيل المستخدم</Label>
              <Switch checked={formActive} onCheckedChange={setFormActive} />
            </div>
            <Button onClick={saveUser} disabled={saving} className="w-full bg-primary text-white">
              {saving ? 'جاري الحفظ...' : editingUser ? 'حفظ التعديلات' : 'إنشاء المستخدم'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
