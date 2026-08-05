import { useState, useEffect, useCallback, useRef } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Card, CardContent } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Checkbox } from '@/components/ui/checkbox';
import { useToast } from '@/hooks/use-toast';
import { Toaster } from '@/components/ui/toaster';
import { client, downloadAuthorizedFile } from '@/lib/localApi';
import { useNavigate } from 'react-router-dom';
import { useBrand } from '@/lib/brand';
import { downloadMemberPdf, downloadMembersZip, buildWelcomeMessage } from '@/lib/memberPdf';
import {
  Search, CheckCircle, XCircle, Eye,
  ArrowRight, Users, Clock, ThumbsUp, ThumbsDown, FileSpreadsheet,
  Trash2, MessageCircle, Send, UserPlus, Calendar, Phone,
  LogOut, Download, Upload, Shield, ArrowUpDown, ArrowUp, ArrowDown, Printer, Palette, ClipboardList, Pencil, FileText, Save
} from 'lucide-react';

const PAGE_SIZE_KEY = 'admin_page_size';
const PAGE_SIZE_OPTIONS = [10, 25, 50, 100] as const;
interface Registration {
  id: number;
  business_name: string;
  merchant_name: string;
  phone: string;
  governorate: string;
  area: string;
  business_type: string | null;
  image_key: string;
  notes: string | null;
  status: string;
  membership_number: string | null;
  request_number: string | null;
  membership_status: string | null;
  approved_at: string | null;
  whatsapp_registration_sent: boolean;
  whatsapp_approval_sent: boolean;
  whatsapp_last_attempt: string | null;
  whatsapp_status: string | null;
  user_id: string;
  last_modified_by: string | null;
  extra_fields?: Record<string, { label?: string; value?: any }> | null;
  created_at: string | null;
  updated_at: string | null;
}

interface Stats {
  total: number;
  pending: number;
  approved: number;
  rejected: number;
  active_members: number;
  suspended_members: number;
}

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

const defaultPermissions = (): Permissions => ({
  view: false,
  add: false,
  edit: false,
  delete: false,
  export: false,
  manage_users: false,
  manage_brand_settings: false,
  manage_registration_form_settings: false,
});

const RECORD_LIMIT_OPTIONS = [
  { value: 'all', label: 'جميع الأعضاء (حسب الفلتر الحالي)' },
  { value: '10', label: 'أول 10' },
  { value: '25', label: 'أول 25' },
  { value: '50', label: 'أول 50' },
  { value: '100', label: 'أول 100' },
  { value: '250', label: 'أول 250' },
  { value: '500', label: 'أول 500' },
  { value: '1000', label: 'أول 1000' },
  { value: 'custom', label: 'عدد مخصص' },
] as const;


function formatPhoneForWhatsApp(phone: string): string {
  let cleaned = phone.trim().replace(/[\s\-+]/g, '');
  if (cleaned.startsWith('07')) {
    cleaned = '964' + cleaned.substring(1);
  } else if (cleaned.startsWith('009647')) {
    cleaned = cleaned.substring(2);
  } else if (cleaned.startsWith('+964')) {
    cleaned = cleaned.substring(1);
  } else if (!cleaned.startsWith('964')) {
    cleaned = '964' + cleaned;
  }
  return cleaned;
}

function isValidPhoneForWhatsApp(phone: string): boolean {
  const cleaned = phone.trim().replace(/[\s\-+]/g, '');
  return cleaned.length >= 10 && cleaned.length <= 15 && /^\d+$/.test(cleaned);
}

function openWhatsAppChat(phone: string) {
  const formattedPhone = formatPhoneForWhatsApp(phone);
  window.open(`https://wa.me/${formattedPhone}`, '_blank');
}

function openWhatsAppWithText(phone: string, message: string) {
  const formattedPhone = formatPhoneForWhatsApp(phone);
  window.open(`https://wa.me/${formattedPhone}?text=${encodeURIComponent(message)}`, '_blank');
}

function openWhatsAppRegistration(phone: string, merchantName: string, businessName: string) {
  const message = `مرحبًا ${merchantName}

تم استلام طلب انضمام نشاطك ${businessName} إلى تجمع تجار التجارة الإلكترونية في العراق بنجاح.

طلبك الآن قيد المراجعة، وسيتم إشعارك بعد اتخاذ القرار.`;
  openWhatsAppWithText(phone, message);
}

const governorates = [
  'بغداد', 'البصرة', 'نينوى', 'أربيل', 'النجف', 'كربلاء',
  'ذي قار', 'بابل', 'ديالى', 'الأنبار', 'كركوك', 'صلاح الدين',
  'واسط', 'ميسان', 'المثنى', 'القادسية', 'دهوك', 'السليمانية'
];

const businessTypes = [
  'تجارة إلكترونية عامة', 'ملابس وأزياء', 'إلكترونيات وأجهزة',
  'مواد غذائية', 'مستحضرات تجميل وعناية', 'أثاث ومفروشات',
  'خدمات رقمية', 'تسويق وإعلانات', 'تعليم وتدريب',
  'صحة وطب', 'سيارات وقطع غيار', 'عقارات', 'أخرى',
];

export default function AdminDashboard() {
  const { toast } = useToast();
  const navigate = useNavigate();
  const { brand, resolveAssetUrl } = useBrand();
  const [authState, setAuthState] = useState<'loading' | 'unauthorized' | 'authorized'>('loading');
  const [loading, setLoading] = useState(true);
  const [registrations, setRegistrations] = useState<Registration[]>([]);
  const [total, setTotal] = useState(0);
  const [stats, setStats] = useState<Stats>({ total: 0, pending: 0, approved: 0, rejected: 0, active_members: 0, suspended_members: 0 });
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [membershipStatusFilter, setMembershipStatusFilter] = useState('all');
  const [governorateFilter, setGovernorateFilter] = useState('all');
  const [yearFilter, setYearFilter] = useState('all');
  const [monthFilter, setMonthFilter] = useState('all');
  const [dayFilter, setDayFilter] = useState('all');
  const [selectedImage, setSelectedImage] = useState<string | null>(null);
  const [imageDialogOpen, setImageDialogOpen] = useState(false);
  const [detailDialogOpen, setDetailDialogOpen] = useState(false);
  const [addMemberDialogOpen, setAddMemberDialogOpen] = useState(false);
  const [selectedRegistration, setSelectedRegistration] = useState<Registration | null>(null);
  const [currentPage, setCurrentPage] = useState(0);
  const [addMemberLoading, setAddMemberLoading] = useState(false);
  const [memberImageFile, setMemberImageFile] = useState<File | null>(null);
  const [memberImagePreview, setMemberImagePreview] = useState<string | null>(null);
  const memberFileInputRef = useRef<HTMLInputElement>(null);
  const [pageSize, setPageSize] = useState<number>(() => {
    const saved = localStorage.getItem(PAGE_SIZE_KEY);
    const n = saved ? Number(saved) : 25;
    return PAGE_SIZE_OPTIONS.includes(n as any) ? n : 25;
  });
  const [printDialogOpen, setPrintDialogOpen] = useState(false);
  const [exportDialogOpen, setExportDialogOpen] = useState(false);
  const [exportMode, setExportMode] = useState<'print' | 'excel'>('print');
  const [recordLimitChoice, setRecordLimitChoice] = useState('all');
  const [customRecordLimit, setCustomRecordLimit] = useState('50');
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [editLoading, setEditLoading] = useState(false);
  const [savingPdf, setSavingPdf] = useState(false);
  const [selectedMap, setSelectedMap] = useState<Record<number, Registration>>({});
  const selectedIds = Object.keys(selectedMap).map(Number);
  const [joinMsgOpen, setJoinMsgOpen] = useState(false);
  const [joinMsgTarget, setJoinMsgTarget] = useState<Registration | null>(null);
  const [nextMembership, setNextMembership] = useState('');
  const [nextMembershipPreview, setNextMembershipPreview] = useState('');
  const [savingNextMn, setSavingNextMn] = useState(false);
  const [nextApplication, setNextApplication] = useState('');
  const [nextApplicationPreview, setNextApplicationPreview] = useState('');
  const [savingNextApp, setSavingNextApp] = useState(false);
  const [editForm, setEditForm] = useState({
    membership_number: '',
    business_name: '',
    merchant_name: '',
    phone: '',
    governorate: '',
    area: '',
    business_type: '',
    notes: '',
    membership_status: 'active',
    status: 'approved',
  });
  const [sortField, setSortField] = useState<string>('created_at');
  const [sortDir, setSortDir] = useState<'asc' | 'desc' | null>('desc');
  const [permissions, setPermissions] = useState<Permissions>(defaultPermissions());
  const [currentUserName, setCurrentUserName] = useState('');
  const [newMember, setNewMember] = useState({
    business_name: '', merchant_name: '', phone: '', governorate: '', area: '', business_type: '', notes: '', membership_status: 'active'
  });

  const sortParam = !sortDir ? '-created_at' : (sortDir === 'desc' ? `-${sortField}` : sortField);
  const sortBy = !sortDir ? 'created_at' : sortField;
  const sortOrder = !sortDir ? 'desc' : sortDir;

  const buildListQuery = (includePaging: boolean) => {
    const queryParams = new URLSearchParams();
    if (includePaging) {
      queryParams.set('skip', (currentPage * pageSize).toString());
      queryParams.set('limit', pageSize.toString());
    }
    // Primary sort param used by backend
    queryParams.set('sort', sortParam);
    // Explicit aliases for clarity / debugging
    queryParams.set('sort_by', sortBy);
    queryParams.set('sort_order', sortOrder);
    if (searchTerm) queryParams.set('query', searchTerm);
    if (statusFilter !== 'all') queryParams.set('status', statusFilter);
    if (membershipStatusFilter !== 'all') queryParams.set('membership_status', membershipStatusFilter);
    if (governorateFilter !== 'all') queryParams.set('governorate', governorateFilter);
    if (yearFilter !== 'all') queryParams.set('year', yearFilter);
    if (monthFilter !== 'all') queryParams.set('month', monthFilter);
    if (dayFilter !== 'all') queryParams.set('day', dayFilter);
    return queryParams;
  };

  const cycleSort = (field: string) => {
    if (sortField !== field) {
      setSortField(field);
      setSortDir('asc');
      setCurrentPage(0);
      return;
    }
    if (sortDir === 'asc') setSortDir('desc');
    else if (sortDir === 'desc') {
      setSortDir(null);
      setSortField('created_at');
    } else setSortDir('asc');
    setCurrentPage(0);
  };

  const SortIcon = ({ field }: { field: string }) => {
    if (sortField !== field || !sortDir) return <ArrowUpDown className="w-3 h-3 opacity-40 inline mr-1" />;
    if (sortDir === 'asc') return <ArrowUp className="w-3 h-3 inline mr-1 text-primary" />;
    return <ArrowDown className="w-3 h-3 inline mr-1 text-primary" />;
  };

  const SortableHead = ({ field, label }: { field: string; label: string }) => (
    <TableHead className="text-right font-semibold p-0 whitespace-normal min-w-0 text-white">
      <button
        type="button"
        className="w-full min-h-9 px-1.5 py-1 inline-flex items-center justify-end gap-0.5 cursor-pointer select-none hover:bg-white/10 text-[11px] leading-tight text-white"
        onClick={() => cycleSort(field)}
        title="اضغط للترتيب: تصاعدي ← تنازلي ← بدون"
      >
        <span className="text-right">{label}</span>
        <SortIcon field={field} />
      </button>
    </TableHead>
  );

  // Auth check - local JWT (me + check-admin in parallel)
  useEffect(() => {
    const checkAuth = async () => {
      try {
        const [meSettled, checkSettled] = await Promise.allSettled([
          client.auth.me(),
          client.apiCall.invoke({
            url: '/api/v1/admin/registrations/check-admin',
            method: 'GET',
            data: {},
          }),
        ]);
        if (meSettled.status !== 'fulfilled' || !meSettled.value?.data) {
          setAuthState('unauthorized');
          return;
        }
        if (checkSettled.status !== 'fulfilled') {
          setAuthState('unauthorized');
          return;
        }
        const res = meSettled.value;
        const check = checkSettled.value;
        const perms = { ...defaultPermissions(), ...(check.data?.permissions || res.data?.permissions || {}) };
        if (check.data?.is_super_admin || res.data?.is_super_admin) {
          Object.keys(perms).forEach((k) => { (perms as any)[k] = true; });
        }
        setPermissions(perms);
        setCurrentUserName(res.data?.name || check.data?.name || '');
        setAuthState('authorized');
      } catch {
        setAuthState('unauthorized');
      }
    };
    checkAuth();
  }, []);

  const fetchStats = useCallback(async () => {
    try {
      const response = await client.apiCall.invoke({
        url: '/api/v1/admin/registrations/stats',
        method: 'GET',
        data: {},
      });
      setStats(response.data);
    } catch {
      // silent
    }
  }, []);

  const fetchRegistrations = useCallback(async () => {
    setLoading(true);
    try {
      const queryParams = buildListQuery(true);

      const response = await client.apiCall.invoke({
        url: `/api/v1/admin/registrations?${queryParams.toString()}`,
        method: 'GET',
        data: {},
      });

      setRegistrations(response.data.items || []);
      setTotal(response.data.total || 0);
    } catch (error: any) {
      if (error?.status === 401 || error?.response?.status === 401) {
        setAuthState('unauthorized');
        return;
      }
      if (error?.status === 403 || error?.response?.status === 403) {
        toast({
          title: 'غير مسموح',
          description: error?.message || 'ليس لديك صلاحية لتنفيذ هذا الإجراء.',
          variant: 'destructive',
        });
        return;
      }
      toast({ title: 'خطأ', description: 'فشل في تحميل البيانات', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  }, [currentPage, pageSize, searchTerm, statusFilter, membershipStatusFilter, governorateFilter, yearFilter, monthFilter, dayFilter, sortParam, sortBy, sortOrder, toast]);

  useEffect(() => {
    if (authState !== 'authorized') return;
    const loadDashboard = async () => {
      const tasks: Promise<unknown>[] = [fetchRegistrations(), fetchStats()];
      if (permissions.edit) {
        tasks.push(
          client.apiCall
            .invoke({ url: '/api/v1/admin/registrations/next-membership-number', method: 'GET', data: {} })
            .then((res) => {
              setNextMembership(String(res.data?.next_number ?? ''));
              setNextMembershipPreview(res.data?.preview || '');
            })
            .catch(() => {}),
          client.apiCall
            .invoke({ url: '/api/v1/admin/registrations/next-application-number', method: 'GET', data: {} })
            .then((res) => {
              setNextApplication(String(res.data?.next_number ?? ''));
              setNextApplicationPreview(res.data?.preview || '');
            })
            .catch(() => {}),
        );
      }
      await Promise.all(tasks);
    };
    loadDashboard();
  }, [authState, fetchRegistrations, fetchStats, permissions.edit]);

  const saveCounter = async (
    kind: 'membership' | 'application',
    raw: string,
    setSaving: (v: boolean) => void,
    setValue: (v: string) => void,
    setPreview: (v: string) => void,
  ) => {
    const n = Number(raw);
    if (!Number.isFinite(n) || n < 1) {
      toast({ title: 'خطأ', description: 'أدخل رقمًا صحيحًا', variant: 'destructive' });
      return;
    }
    const path =
      kind === 'membership'
        ? '/api/v1/admin/registrations/next-membership-number'
        : '/api/v1/admin/registrations/next-application-number';
    const prefix = kind === 'membership' ? 'MF' : 'REQ';
    setSaving(true);
    try {
      let res: any = null;
      let lastErr: any = null;
      for (const method of ['POST', 'PUT', 'PATCH'] as const) {
        try {
          res = await client.apiCall.invoke({
            url: path,
            method,
            data: { next_number: n },
          });
          lastErr = null;
          break;
        } catch (e: any) {
          lastErr = e;
          if (e?.status !== 405 && e?.response?.status !== 405) break;
        }
      }
      if (!res) throw lastErr || new Error('فشل الحفظ');
      const saved = String(res.data?.next_number ?? n);
      const preview = res.data?.preview || `${prefix}-${String(n).padStart(4, '0')}`;
      setValue(saved);
      setPreview(preview);
      try {
        const refreshed = await client.apiCall.invoke({ url: path, method: 'GET', data: {} });
        setValue(String(refreshed.data?.next_number ?? saved));
        setPreview(refreshed.data?.preview || preview);
      } catch {
        // keep local values from save response
      }
      toast({
        title: 'تم الحفظ',
        description:
          res.data?.message ||
          (kind === 'membership' ? 'تم تحديث رقم العضوية التالي' : 'تم تحديث رقم الطلب التالي'),
      });
    } catch (e: any) {
      toast({
        title: 'تعذر الحفظ',
        description:
          e?.message ||
          (kind === 'membership'
            ? 'رقم العضوية مستخدم بالفعل، يرجى اختيار رقم آخر.'
            : 'رقم الطلب مستخدم بالفعل، يرجى اختيار رقم آخر.'),
        variant: 'destructive',
      });
    } finally {
      setSaving(false);
    }
  };

  const saveNextMembership = () =>
    saveCounter('membership', nextMembership, setSavingNextMn, setNextMembership, setNextMembershipPreview);

  const saveNextApplication = () =>
    saveCounter('application', nextApplication, setSavingNextApp, setNextApplication, setNextApplicationPreview);

  const openJoinMessageDialog = (reg: Registration) => {
    setJoinMsgTarget(reg);
    setJoinMsgOpen(true);
  };

  const welcomeTextFor = (reg: Registration) =>
    buildWelcomeMessage(brand.whatsapp_welcome_message, reg.membership_number || '', brand);

  const joinWhatsAppOnly = () => {
    if (!joinMsgTarget) return;
    openWhatsAppWithText(joinMsgTarget.phone, welcomeTextFor(joinMsgTarget));
    setJoinMsgOpen(false);
  };

  const joinDownloadThenWhatsApp = async () => {
    if (!joinMsgTarget) return;
    setSavingPdf(true);
    try {
      const imageUrl = await resolveMemberImageUrl(joinMsgTarget);
      await downloadMemberPdf(joinMsgTarget, brand, {
        logoUrl: resolveAssetUrl(brand.report_logo || brand.system_logo),
        imageUrl,
        generatedBy: currentUserName || 'admin',
      });
      toast({
        title: 'تم تنزيل ملف العضو',
        description: 'تم تنزيل ملف العضو، يمكنك إرفاقه يدويًا داخل واتساب.',
      });
      openWhatsAppWithText(joinMsgTarget.phone, welcomeTextFor(joinMsgTarget));
      setJoinMsgOpen(false);
    } catch (e: any) {
      toast({ title: 'خطأ', description: e?.message || 'فشل تنزيل الملف', variant: 'destructive' });
    } finally {
      setSavingPdf(false);
    }
  };

  const changePageSize = (value: string) => {
    const n = Number(value);
    if (!PAGE_SIZE_OPTIONS.includes(n as any)) return;
    setPageSize(n);
    localStorage.setItem(PAGE_SIZE_KEY, String(n));
    setCurrentPage(0);
  };

  const resolveMaxRecords = () => {
    if (recordLimitChoice === 'all') return 0;
    if (recordLimitChoice === 'custom') {
      const n = Number(customRecordLimit);
      if (!Number.isFinite(n) || n < 1) return null;
      return Math.min(Math.floor(n), 5000);
    }
    return Number(recordLimitChoice) || 0;
  };

  const openExportDialog = (mode: 'print' | 'excel') => {
    if (!permissions.export) {
      toast({ title: 'غير مسموح', description: 'ليس لديك صلاحية لتنفيذ هذا الإجراء.', variant: 'destructive' });
      return;
    }
    setExportMode(mode);
    setRecordLimitChoice('all');
    setCustomRecordLimit('50');
    setExportDialogOpen(true);
  };

  const confirmExportOrPrint = async () => {
    if (!permissions.export) {
      toast({ title: 'غير مسموح', description: 'ليس لديك صلاحية لتنفيذ هذا الإجراء.', variant: 'destructive' });
      return;
    }
    const maxRecords = resolveMaxRecords();
    if (maxRecords === null) {
      toast({ title: 'خطأ', description: 'أدخل عدداً مخصصاً صالحاً', variant: 'destructive' });
      return;
    }
    const q = buildListQuery(false);
    q.set('scope', 'filtered');
    q.set('sort', sortParam);
    if (maxRecords > 0) q.set('max_records', String(maxRecords));
    setExportDialogOpen(false);
    setPrintDialogOpen(false);
    if (exportMode === 'print') {
      window.open(`/admin/print?${q.toString()}`, '_blank', 'noopener,noreferrer');
      return;
    }
    toast({ title: 'جاري التصدير...', description: 'يتم إعداد ملف Excel' });
    try {
      const now = new Date();
      await downloadAuthorizedFile(
        `/api/v1/admin/registrations/export-xlsx?${q.toString()}`,
        `members_${now.toISOString().split('T')[0]}.xlsx`
      );
      toast({ title: 'تم التصدير', description: 'تم تنزيل ملف Excel بنجاح' });
    } catch (error: any) {
      toast({ title: 'خطأ', description: error?.message || 'فشل في التصدير', variant: 'destructive' });
    }
  };

  const openEdit = (reg: Registration) => {
    if (!permissions.edit) {
      toast({ title: 'غير مسموح', description: 'ليس لديك صلاحية لتنفيذ هذا الإجراء.', variant: 'destructive' });
      return;
    }
    setSelectedRegistration(reg);
    setEditForm({
      membership_number: reg.membership_number || '',
      business_name: reg.business_name || '',
      merchant_name: reg.merchant_name || '',
      phone: reg.phone || '',
      governorate: reg.governorate || '',
      area: reg.area || '',
      business_type: reg.business_type || '',
      notes: reg.notes || '',
      membership_status: reg.membership_status || 'active',
      status: reg.status || 'pending',
    });
    setEditDialogOpen(true);
  };

  const saveEdit = async () => {
    if (!selectedRegistration) return;
    if (!editForm.business_name || !editForm.merchant_name || !editForm.phone || !editForm.governorate || !editForm.area) {
      toast({ title: 'خطأ', description: 'املأ الحقول الأساسية', variant: 'destructive' });
      return;
    }
    setEditLoading(true);
    try {
      await client.apiCall.invoke({
        url: `/api/v1/entities/registrations/${selectedRegistration.id}`,
        method: 'PUT',
        data: {
          business_name: editForm.business_name,
          merchant_name: editForm.merchant_name,
          phone: editForm.phone,
          governorate: editForm.governorate,
          area: editForm.area,
          business_type: editForm.business_type || '',
          notes: editForm.notes || '',
          status: editForm.status,
          membership_number: editForm.membership_number || null,
          membership_status: editForm.membership_status || null,
        },
      });
      toast({ title: 'تم التحديث', description: 'تم حفظ بيانات العضو' });
      setEditDialogOpen(false);
      fetchRegistrations();
      fetchStats();
    } catch (error: any) {
      toast({ title: 'خطأ', description: error?.message || 'فشل تحديث العضو', variant: 'destructive' });
    } finally {
      setEditLoading(false);
    }
  };

  const resolveMemberImageUrl = async (reg: Registration): Promise<string | null> => {
    if (!reg.image_key || reg.image_key === 'manual_entry') return null;
    try {
      const res = await client.storage.getDownloadUrl({ bucket_name: 'business-images', object_key: reg.image_key });
      return res.data?.download_url || null;
    } catch {
      return null;
    }
  };

  const saveMemberPdf = async (reg: Registration) => {
    setSavingPdf(true);
    try {
      const imageUrl = await resolveMemberImageUrl(reg);
      await downloadMemberPdf(reg, brand, {
        logoUrl: resolveAssetUrl(brand.report_logo || brand.system_logo),
        imageUrl,
        generatedBy: currentUserName || 'admin',
      });
      toast({ title: 'تم الحفظ', description: 'تم تنزيل ملف PDF للعضو' });
    } catch (e: any) {
      toast({ title: 'خطأ', description: e?.message || 'فشل إنشاء PDF', variant: 'destructive' });
    } finally {
      setSavingPdf(false);
    }
  };

  const toggleSelect = (reg: Registration, checked: boolean) => {
    setSelectedMap((prev) => {
      const next = { ...prev };
      if (checked) next[reg.id] = reg;
      else delete next[reg.id];
      return next;
    });
  };

  const toggleSelectAllPage = (checked: boolean) => {
    setSelectedMap((prev) => {
      const next = { ...prev };
      if (checked) {
        registrations.forEach((r) => { next[r.id] = r; });
      } else {
        registrations.forEach((r) => { delete next[r.id]; });
      }
      return next;
    });
  };

  const saveSelectedPdfs = async () => {
    const targets = Object.values(selectedMap);
    if (!targets.length) {
      toast({ title: 'تنبيه', description: 'حدد عضواً واحداً على الأقل', variant: 'destructive' });
      return;
    }
    setSavingPdf(true);
    try {
      if (targets.length === 1) {
        const imageUrl = await resolveMemberImageUrl(targets[0]);
        await downloadMemberPdf(targets[0], brand, {
          logoUrl: resolveAssetUrl(brand.report_logo || brand.system_logo),
          imageUrl,
          generatedBy: currentUserName || 'admin',
        });
        toast({ title: 'تم الحفظ', description: 'تم تنزيل ملف PDF للعضو' });
        return;
      }
      toast({ title: 'جاري الحفظ الجماعي...', description: `إنشاء ${targets.length} ملف PDF داخل ZIP` });
      await downloadMembersZip(
        targets,
        brand,
        resolveMemberImageUrl,
        resolveAssetUrl(brand.report_logo || brand.system_logo),
        currentUserName || 'admin'
      );
      toast({ title: 'تم الحفظ', description: 'تم تنزيل ملف ZIP بملفات الأعضاء' });
    } catch (e: any) {
      toast({ title: 'خطأ', description: e?.message || 'فشل الحفظ الجماعي', variant: 'destructive' });
    } finally {
      setSavingPdf(false);
    }
  };

  const openPrint = (_scope: 'filtered' | 'all') => {
    openExportDialog('print');
  };
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

  const updateStatus = async (id: number, status: string) => {
    try {
      await client.apiCall.invoke({
        url: `/api/v1/admin/registrations/${id}/status`,
        method: 'PUT',
        data: { status },
      });
      toast({ title: 'تم التحديث', description: status === 'approved' ? 'تم قبول الطلب بنجاح' : status === 'rejected' ? 'تم رفض الطلب' : 'تم تحديث الحالة' });
      fetchRegistrations();
      fetchStats();
    } catch (error: any) {
      toast({ title: 'خطأ', description: error?.message || 'فشل في تحديث الحالة', variant: 'destructive' });
    }
  };

  const updateMembershipStatus = async (id: number, membershipStatus: string) => {
    try {
      await client.apiCall.invoke({
        url: `/api/v1/admin/registrations/${id}/membership-status`,
        method: 'PUT',
        data: { membership_status: membershipStatus },
      });
      toast({ title: 'تم التحديث', description: 'تم تحديث حالة العضوية' });
      fetchRegistrations();
      fetchStats();
    } catch (error: any) {
      toast({ title: 'خطأ', description: error?.message || 'فشل في تحديث حالة العضوية', variant: 'destructive' });
    }
  };

  const deleteRegistration = async (id: number) => {
    if (!permissions.delete) {
      toast({ title: 'غير مسموح', description: 'ليس لديك صلاحية لتنفيذ هذا الإجراء.', variant: 'destructive' });
      return;
    }
    if (!confirm('هل أنت متأكد من حذف هذا الطلب؟')) return;
    try {
      await client.apiCall.invoke({ url: `/api/v1/admin/registrations/${id}`, method: 'DELETE', data: {} });
      toast({ title: 'تم الحذف', description: 'تم حذف الطلب بنجاح' });
      fetchRegistrations();
      fetchStats();
    } catch (error: any) {
      toast({ title: 'خطأ', description: error?.message || 'فشل في حذف الطلب', variant: 'destructive' });
    }
  };

  const handleMemberImageChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      if (file.size > 5 * 1024 * 1024) {
        toast({ title: 'خطأ', description: 'الحد الأقصى 5MB', variant: 'destructive' });
        return;
      }
      setMemberImageFile(file);
      const reader = new FileReader();
      reader.onloadend = () => setMemberImagePreview(reader.result as string);
      reader.readAsDataURL(file);
    }
  };

  const addMember = async () => {
    if (!newMember.business_name || !newMember.merchant_name || !newMember.phone || !newMember.governorate || !newMember.area || !newMember.business_type) {
      toast({ title: 'خطأ', description: 'يرجى ملء جميع الحقول المطلوبة', variant: 'destructive' });
      return;
    }
    setAddMemberLoading(true);
    try {
      let imageKey = 'manual_entry';

      // Upload image if provided
      if (memberImageFile) {
        const timestamp = Date.now();
        const objectKey = `registrations/${timestamp}_${memberImageFile.name}`;
        const uploadRes = await client.storage.getUploadUrl({
          bucket_name: 'business-images',
          object_key: objectKey,
        });
        await fetch(uploadRes.data.upload_url, {
          method: 'PUT',
          body: memberImageFile,
          headers: { 'Content-Type': memberImageFile.type },
        });
        imageKey = objectKey;
      }

      await client.apiCall.invoke({
        url: '/api/v1/admin/registrations/add-member',
        method: 'POST',
        data: { ...newMember, image_key: imageKey },
      });
      toast({ title: 'تمت الإضافة', description: 'تم إضافة العضو بنجاح' });
      setAddMemberDialogOpen(false);
      setNewMember({ business_name: '', merchant_name: '', phone: '', governorate: '', area: '', business_type: '', notes: '', membership_status: 'active' });
      setMemberImageFile(null);
      setMemberImagePreview(null);
      fetchRegistrations();
      fetchStats();
    } catch {
      toast({ title: 'خطأ', description: 'فشل في إضافة العضو', variant: 'destructive' });
    } finally {
      setAddMemberLoading(false);
    }
  };

  const viewImage = async (imageKey: string) => {
    if (imageKey === 'manual_entry') {
      toast({ title: 'ملاحظة', description: 'هذا العضو مضاف يدوياً بدون صورة' });
      return;
    }
    try {
      const res = await client.storage.getDownloadUrl({ bucket_name: 'business-images', object_key: imageKey });
      setSelectedImage(res.data.download_url);
      setImageDialogOpen(true);
    } catch {
      toast({ title: 'خطأ', description: 'فشل في تحميل الصورة', variant: 'destructive' });
    }
  };

  // Real XLSX export via backend openpyxl (respects current filters/search/sort)
  const exportXLSX = async () => {
    openExportDialog('excel');
  };

  // JSON backup download
  const downloadBackupJSON = async () => {
    if (!permissions.export) {
      toast({ title: 'غير مسموح', description: 'ليس لديك صلاحية لتنفيذ هذا الإجراء.', variant: 'destructive' });
      return;
    }
    try {
      const queryParams = new URLSearchParams();
      queryParams.set('sort', sortParam);
      if (searchTerm) queryParams.set('query', searchTerm);
      if (statusFilter !== 'all') queryParams.set('status', statusFilter);
      if (membershipStatusFilter !== 'all') queryParams.set('membership_status', membershipStatusFilter);
      if (governorateFilter !== 'all') queryParams.set('governorate', governorateFilter);
      if (yearFilter !== 'all') queryParams.set('year', yearFilter);
      if (monthFilter !== 'all') queryParams.set('month', monthFilter);
      if (dayFilter !== 'all') queryParams.set('day', dayFilter);
      const response = await client.apiCall.invoke({
        url: `/api/v1/admin/registrations/export-all?${queryParams.toString()}`,
        method: 'GET',
        data: {},
      });
      const blob = new Blob([JSON.stringify(response.data, null, 2)], { type: 'application/json;charset=utf-8' });
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = `backup_${new Date().toISOString().split('T')[0]}.json`;
      link.click();
      URL.revokeObjectURL(link.href);
      toast({ title: 'تم التنزيل', description: 'تم تنزيل النسخة الاحتياطية JSON' });
    } catch (error: any) {
      toast({ title: 'خطأ', description: error?.message || 'فشل في تنزيل النسخة الاحتياطية', variant: 'destructive' });
    }
  };

  // CSV backup download
  const downloadBackupCSV = async () => {
    if (!permissions.export) {
      toast({ title: 'غير مسموح', description: 'ليس لديك صلاحية لتنفيذ هذا الإجراء.', variant: 'destructive' });
      return;
    }
    try {
      const queryParams = new URLSearchParams();
      queryParams.set('sort', sortParam);
      if (searchTerm) queryParams.set('query', searchTerm);
      if (statusFilter !== 'all') queryParams.set('status', statusFilter);
      if (membershipStatusFilter !== 'all') queryParams.set('membership_status', membershipStatusFilter);
      if (governorateFilter !== 'all') queryParams.set('governorate', governorateFilter);
      if (yearFilter !== 'all') queryParams.set('year', yearFilter);
      if (monthFilter !== 'all') queryParams.set('month', monthFilter);
      if (dayFilter !== 'all') queryParams.set('day', dayFilter);
      const response = await client.apiCall.invoke({
        url: `/api/v1/admin/registrations/export-all?${queryParams.toString()}`,
        method: 'GET',
        data: {},
      });
      const allData = response.data.items || [];
      const headers = ['id', 'membership_number', 'business_name', 'merchant_name', 'phone', 'governorate', 'area', 'business_type', 'status', 'membership_status', 'approved_at', 'created_at', 'updated_at', 'notes'];
      const rows = allData.map((reg: any) => headers.map(h => `"${(reg[h] || '').toString().replace(/"/g, '""')}"`).join(','));
      const csvContent = [headers.join(','), ...rows].join('\n');
      const blob = new Blob(['\uFEFF' + csvContent], { type: 'text/csv;charset=utf-8' });
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = `backup_${new Date().toISOString().split('T')[0]}.csv`;
      link.click();
      URL.revokeObjectURL(link.href);
      toast({ title: 'تم التنزيل', description: 'تم تنزيل النسخة الاحتياطية CSV' });
    } catch (error: any) {
      toast({ title: 'خطأ', description: error?.message || 'فشل في تنزيل النسخة الاحتياطية', variant: 'destructive' });
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'pending': return <Badge className="bg-amber-100 text-amber-800 hover:bg-amber-100"><Clock className="w-3 h-3 ml-1" /> قيد المراجعة</Badge>;
      case 'approved': return <Badge className="bg-green-100 text-green-800 hover:bg-green-100"><ThumbsUp className="w-3 h-3 ml-1" /> مقبول</Badge>;
      case 'rejected': return <Badge className="bg-red-100 text-red-800 hover:bg-red-100"><ThumbsDown className="w-3 h-3 ml-1" /> مرفوض</Badge>;
      default: return <Badge variant="secondary">{status}</Badge>;
    }
  };

  const getMembershipBadge = (ms: string | null) => {
    switch (ms) {
      case 'active': return <Badge className="bg-emerald-100 text-emerald-800 hover:bg-emerald-100">فعال</Badge>;
      case 'suspended': return <Badge className="bg-orange-100 text-orange-800 hover:bg-orange-100">معلق</Badge>;
      case 'expired': return <Badge className="bg-gray-200 text-gray-700 hover:bg-gray-200">منتهي</Badge>;
      default: return <span className="text-gray-400 text-xs">-</span>;
    }
  };

  const years = Array.from({ length: 5 }, (_, i) => (new Date().getFullYear() - i).toString());
  const months = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12'];
  const days = Array.from({ length: 31 }, (_, i) => (i + 1).toString());

  // --- UNAUTHORIZED STATE ---
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

  // --- AUTHORIZED ADMIN VIEW ---
  return (
    <div className="min-h-screen bg-[#F9FAFB]" dir="rtl">
      <Toaster />
      <header className="sticky top-0 z-10 text-white shadow-md" style={{ background: brand.header_color || brand.primary_color }}>
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-3">
            <img
              src={resolveAssetUrl(brand.system_logo)}
              alt="MFEC"
              className="w-11 h-11 object-contain bg-white/10 rounded-lg p-0.5"
            />
            <div>
              <h1 className="text-lg font-bold leading-tight">{brand.header_text || brand.system_name}</h1>
              <p className="text-xs opacity-80">
                <span style={{ color: brand.secondary_color }}>{brand.org_abbr}</span>
                {' · '}إدارة الأعضاء والطلبات
                {currentUserName ? ` · ${currentUserName}` : ''}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            {permissions.add && (
              <Button size="sm" onClick={() => setAddMemberDialogOpen(true)} className="flex items-center gap-1 text-white hover:opacity-90" style={{ background: brand.button_color || brand.secondary_color }}>
                <UserPlus className="w-4 h-4" /> إضافة عضو
              </Button>
            )}
            {(permissions.manage_brand_settings) && (
              <Button variant="outline" size="sm" onClick={() => navigate('/admin/brand-settings')} className="flex items-center gap-1 bg-white/10 text-white border-white/30 hover:bg-white/20">
                <Palette className="w-4 h-4" /> إعدادات الهوية
              </Button>
            )}
            {(permissions.manage_registration_form_settings) && (
              <Button variant="outline" size="sm" onClick={() => navigate('/admin/form-settings')} className="flex items-center gap-1 bg-white/10 text-white border-white/30 hover:bg-white/20">
                <ClipboardList className="w-4 h-4" /> إعدادات الاستمارة
              </Button>
            )}
            {permissions.export && (
              <Button variant="outline" size="sm" onClick={() => navigate('/admin/membership-report')} className="flex items-center gap-1 bg-white/10 text-white border-white/30 hover:bg-white/20">
                <FileText className="w-4 h-4" /> كشف العضوية
              </Button>
            )}
            {permissions.manage_users && (
              <Button variant="outline" size="sm" onClick={() => navigate('/admin/users')} className="flex items-center gap-1 bg-white/10 text-white border-white/30 hover:bg-white/20">
                <Users className="w-4 h-4" /> إدارة المستخدمين
              </Button>
            )}
            <Button variant="outline" size="sm" onClick={() => navigate('/')} className="flex items-center gap-2 bg-white/10 text-white border-white/30 hover:bg-white/20">
              <ArrowRight className="w-4 h-4" /> الرئيسية
            </Button>
            <Button variant="ghost" size="sm" onClick={handleLogout} className="flex items-center gap-1 text-white/90 hover:bg-white/10" title="تسجيل الخروج">
              <LogOut className="w-4 h-4" />
            </Button>
          </div>
        </div>
        <div className="h-1" style={{ background: brand.secondary_color }} />
      </header>

      <main className="max-w-7xl mx-auto px-4 py-6 space-y-6">
        {permissions.edit && (
          <Card className="border-0 shadow-sm">
            <CardContent className="p-4 grid grid-cols-1 md:grid-cols-2 gap-4 text-right">
              <div className="flex flex-col sm:flex-row items-end gap-3">
                <div className="space-y-1 flex-1 w-full">
                  <Label>رقم العضوية التالي (Next Membership Number)</Label>
                  <Input
                    type="number"
                    min={1}
                    value={nextMembership}
                    onChange={(e) => setNextMembership(e.target.value)}
                    className="text-right font-mono"
                  />
                  <p className="text-xs text-gray-500">
                    المعاينة: {nextMembershipPreview || (nextMembership ? `MF-${String(nextMembership).padStart(4, '0')}` : '-')}
                  </p>
                  <p className="text-xs text-gray-500">
                    يُستخدم عند قبول طلب أو إضافة عضو، ثم يزيد تلقائيًا (+1). لا يؤثر على الأعضاء الحاليين.
                  </p>
                </div>
                <Button
                  disabled={savingNextMn}
                  onClick={saveNextMembership}
                  className="text-white shrink-0"
                  style={{ background: brand.button_color }}
                >
                  {savingNextMn ? 'جاري الحفظ...' : 'حفظ'}
                </Button>
              </div>
              <div className="flex flex-col sm:flex-row items-end gap-3">
                <div className="space-y-1 flex-1 w-full">
                  <Label>رقم الطلب التالي (Next Application Number)</Label>
                  <Input
                    type="number"
                    min={1}
                    value={nextApplication}
                    onChange={(e) => setNextApplication(e.target.value)}
                    className="text-right font-mono"
                  />
                  <p className="text-xs text-gray-500">
                    المعاينة: {nextApplicationPreview || (nextApplication ? `REQ-${String(nextApplication).padStart(4, '0')}` : '-')}
                  </p>
                  <p className="text-xs text-gray-500">
                    يُستخدم عند تقديم طلب انضمام جديد من الصفحة العامة، ثم يزيد تلقائيًا (+1). لا يؤثر على الطلبات السابقة.
                  </p>
                </div>
                <Button
                  disabled={savingNextApp}
                  onClick={saveNextApplication}
                  className="text-white shrink-0"
                  style={{ background: brand.button_color }}
                >
                  {savingNextApp ? 'جاري الحفظ...' : 'حفظ'}
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Stats */}
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
          <Card className="border-0 shadow-sm hover:shadow-md transition-shadow border-t-2" style={{ borderTopColor: brand.primary_color }}><CardContent className="p-3 flex items-center gap-2">
            <div className="w-9 h-9 rounded-lg flex items-center justify-center" style={{ background: `${brand.primary_color}15` }}><Users className="w-4 h-4" style={{ color: brand.primary_color }} /></div>
            <div><p className="text-xl font-bold text-gray-800">{stats.total}</p><p className="text-[10px] text-gray-500">إجمالي</p></div>
          </CardContent></Card>
          <Card className="border-0 shadow-sm hover:shadow-md transition-shadow border-t-2" style={{ borderTopColor: brand.secondary_color }}><CardContent className="p-3 flex items-center gap-2">
            <div className="w-9 h-9 rounded-lg flex items-center justify-center" style={{ background: `${brand.secondary_color}22` }}><Clock className="w-4 h-4" style={{ color: brand.secondary_color }} /></div>
            <div><p className="text-xl font-bold text-gray-800">{stats.pending}</p><p className="text-[10px] text-gray-500">قيد المراجعة</p></div>
          </CardContent></Card>
          <Card className="border-0 shadow-sm hover:shadow-md transition-shadow border-t-2 border-t-green-600"><CardContent className="p-3 flex items-center gap-2">
            <div className="w-9 h-9 bg-green-100 rounded-lg flex items-center justify-center"><CheckCircle className="w-4 h-4 text-green-600" /></div>
            <div><p className="text-xl font-bold text-gray-800">{stats.approved}</p><p className="text-[10px] text-gray-500">مقبول</p></div>
          </CardContent></Card>
          <Card className="border-0 shadow-sm hover:shadow-md transition-shadow border-t-2 border-t-red-500"><CardContent className="p-3 flex items-center gap-2">
            <div className="w-9 h-9 bg-red-100 rounded-lg flex items-center justify-center"><XCircle className="w-4 h-4 text-red-600" /></div>
            <div><p className="text-xl font-bold text-gray-800">{stats.rejected}</p><p className="text-[10px] text-gray-500">مرفوض</p></div>
          </CardContent></Card>
          <Card className="border-0 shadow-sm hover:shadow-md transition-shadow border-t-2 border-t-emerald-600"><CardContent className="p-3 flex items-center gap-2">
            <div className="w-9 h-9 bg-emerald-100 rounded-lg flex items-center justify-center"><ThumbsUp className="w-4 h-4 text-emerald-600" /></div>
            <div><p className="text-xl font-bold text-gray-800">{stats.active_members}</p><p className="text-[10px] text-gray-500">أعضاء فعالين</p></div>
          </CardContent></Card>
          <Card className="border-0 shadow-sm hover:shadow-md transition-shadow border-t-2 border-t-orange-500"><CardContent className="p-3 flex items-center gap-2">
            <div className="w-9 h-9 bg-orange-100 rounded-lg flex items-center justify-center"><Clock className="w-4 h-4 text-orange-600" /></div>
            <div><p className="text-xl font-bold text-gray-800">{stats.suspended_members}</p><p className="text-[10px] text-gray-500">معلقين</p></div>
          </CardContent></Card>
        </div>

        {/* Filters */}
        <Card className="border-0 shadow-sm">
          <CardContent className="p-4 space-y-3">
            <div className="flex flex-col md:flex-row gap-3">
              <div className="flex-1 relative">
                <Search className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                <Input placeholder="بحث بالاسم، الهاتف، النشاط، رقم العضوية..." value={searchTerm} onChange={(e) => { setSearchTerm(e.target.value); setCurrentPage(0); }} className="pr-10 text-right" />
              </div>
              <Select value={statusFilter} onValueChange={(val) => { setStatusFilter(val); setCurrentPage(0); }}>
                <SelectTrigger className="w-full md:w-[140px]"><SelectValue placeholder="حالة الطلب" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">جميع الحالات</SelectItem>
                  <SelectItem value="pending">قيد المراجعة</SelectItem>
                  <SelectItem value="approved">مقبول</SelectItem>
                  <SelectItem value="rejected">مرفوض</SelectItem>
                </SelectContent>
              </Select>
              <Select value={membershipStatusFilter} onValueChange={(val) => { setMembershipStatusFilter(val); setCurrentPage(0); }}>
                <SelectTrigger className="w-full md:w-[140px]"><SelectValue placeholder="حالة العضوية" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">جميع العضويات</SelectItem>
                  <SelectItem value="active">فعال</SelectItem>
                  <SelectItem value="suspended">معلق</SelectItem>
                  <SelectItem value="expired">منتهي</SelectItem>
                </SelectContent>
              </Select>
              <Select value={governorateFilter} onValueChange={(val) => { setGovernorateFilter(val); setCurrentPage(0); }}>
                <SelectTrigger className="w-full md:w-[140px]"><SelectValue placeholder="المحافظة" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">جميع المحافظات</SelectItem>
                  {governorates.map((gov) => (<SelectItem key={gov} value={gov}>{gov}</SelectItem>))}
                </SelectContent>
              </Select>
            </div>
            {/* Date Filters */}
            <div className="flex flex-col md:flex-row gap-3 items-center">
              <div className="flex items-center gap-1 text-sm text-gray-500"><Calendar className="w-4 h-4" /> فلترة بالتاريخ:</div>
              <Select value={yearFilter} onValueChange={(val) => { setYearFilter(val); setCurrentPage(0); }}>
                <SelectTrigger className="w-full md:w-[110px]"><SelectValue placeholder="السنة" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">كل السنوات</SelectItem>
                  {years.map(y => (<SelectItem key={y} value={y}>{y}</SelectItem>))}
                </SelectContent>
              </Select>
              <Select value={monthFilter} onValueChange={(val) => { setMonthFilter(val); setCurrentPage(0); }}>
                <SelectTrigger className="w-full md:w-[110px]"><SelectValue placeholder="الشهر" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">كل الأشهر</SelectItem>
                  {months.map(m => (<SelectItem key={m} value={m}>{m}</SelectItem>))}
                </SelectContent>
              </Select>
              <Select value={dayFilter} onValueChange={(val) => { setDayFilter(val); setCurrentPage(0); }}>
                <SelectTrigger className="w-full md:w-[100px]"><SelectValue placeholder="اليوم" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">كل الأيام</SelectItem>
                  {days.map(d => (<SelectItem key={d} value={d}>{d}</SelectItem>))}
                </SelectContent>
              </Select>
              <div className="flex gap-2 mr-auto flex-wrap items-center">
                <div className="flex items-center gap-2 text-sm text-gray-600">
                  <span className="whitespace-nowrap">عدد الأعضاء في الصفحة</span>
                  <Select value={String(pageSize)} onValueChange={changePageSize}>
                    <SelectTrigger className="w-[90px] h-8"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {PAGE_SIZE_OPTIONS.map((n) => (
                        <SelectItem key={n} value={String(n)}>{n}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                {permissions.export && (
                  <>
                    <Button
                      onClick={saveSelectedPdfs}
                      disabled={savingPdf || selectedIds.length === 0}
                      variant="outline"
                      size="sm"
                      className="flex items-center gap-1 hover:border-[#C89B3C]"
                    >
                      <Save className="w-4 h-4" /> حفظ {selectedIds.length > 0 ? `(${selectedIds.length})` : ''}
                    </Button>
                    <Button onClick={exportXLSX} variant="outline" size="sm" className="flex items-center gap-1 hover:border-[#C89B3C]">
                      <FileSpreadsheet className="w-4 h-4" /> تصدير Excel
                    </Button>
                    <Button onClick={() => openExportDialog('print')} variant="outline" size="sm" className="flex items-center gap-1 hover:border-[#C89B3C]">
                      <Printer className="w-4 h-4" /> طباعة
                    </Button>
                    <Button onClick={downloadBackupJSON} variant="outline" size="sm" className="flex items-center gap-1">
                      <Download className="w-4 h-4" /> JSON
                    </Button>
                    <Button onClick={downloadBackupCSV} variant="outline" size="sm" className="flex items-center gap-1">
                      <Download className="w-4 h-4" /> CSV
                    </Button>
                  </>
                )}
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Table */}
        <Card className="border-0 shadow-sm overflow-hidden">
          <CardContent className="p-0">
            {loading ? (
              <div className="flex items-center justify-center py-20">
                <div className="text-center space-y-3">
                  <svg className="animate-spin h-8 w-8 mx-auto text-primary" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg>
                  <p className="text-gray-500">جاري التحميل...</p>
                </div>
              </div>
            ) : registrations.length === 0 ? (
              <div className="flex items-center justify-center py-20">
                <div className="text-center space-y-3"><Users className="w-12 h-12 mx-auto text-gray-300" /><p className="text-gray-500 text-lg">لا توجد طلبات</p><p className="text-gray-400 text-sm">جرّب تغيير الفلاتر أو البحث</p></div>
              </div>
            ) : (
              <>
                {/* Desktop / laptop compact table — essential columns visible without horizontal scroll when possible */}
                <div className="hidden md:block">
                  <Table className="table-fixed w-full text-[12px]">
                    <TableHeader>
                      <TableRow style={{ background: brand.table_header_color || brand.primary_color }}>
                        <TableHead className="text-white w-8 px-1">
                          <Checkbox
                            checked={registrations.length > 0 && registrations.every((r) => selectedIds.includes(r.id))}
                            onCheckedChange={(v) => toggleSelectAllPage(!!v)}
                            aria-label="تحديد الكل"
                          />
                        </TableHead>
                        <TableHead className="text-right font-semibold w-8 px-1 text-white">#</TableHead>
                        <SortableHead field="membership_number" label="رقم العضوية" />
                        <SortableHead field="business_name" label="اسم النشاط" />
                        <SortableHead field="merchant_name" label="التاجر" />
                        <SortableHead field="phone" label="الهاتف" />
                        <SortableHead field="governorate" label="المحافظة" />
                        <SortableHead field="status" label="الطلب" />
                        <SortableHead field="membership_status" label="العضوية" />
                        <SortableHead field="created_at" label="تاريخ الطلب" />
                        <SortableHead field="last_modified_by" label="آخر تعديل" />
                        <TableHead className="text-right font-semibold px-1 w-[160px] text-white">إجراءات</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {registrations.map((reg, idx) => (
                        <TableRow key={reg.id} className="hover:bg-amber-50/40 transition-colors" style={{ background: idx % 2 === 1 ? (brand.table_alt_row_color || '#F3F4F6') : undefined }}>
                          <TableCell className="px-1 py-1.5 align-top">
                            <Checkbox
                              checked={selectedIds.includes(reg.id)}
                              onCheckedChange={(v) => toggleSelect(reg, !!v)}
                            />
                          </TableCell>
                          <TableCell className="px-1 py-1.5 align-top">{currentPage * pageSize + idx + 1}</TableCell>
                          <TableCell className="px-1 py-1.5 align-top break-words">
                            {reg.membership_number ? (<Badge className="bg-blue-50 text-blue-700 hover:bg-blue-50 font-mono text-[10px]">{reg.membership_number}</Badge>) : '-'}
                          </TableCell>
                          <TableCell className="px-1 py-1.5 align-top font-medium break-words whitespace-normal leading-snug">{reg.business_name}</TableCell>
                          <TableCell className="px-1 py-1.5 align-top break-words whitespace-normal leading-snug">{reg.merchant_name}</TableCell>
                          <TableCell className="px-1 py-1.5 align-top">
                            <div className="flex items-start gap-0.5">
                              <span dir="ltr" className="font-mono text-[11px] break-all">{reg.phone}</span>
                              <Button variant="ghost" size="sm" onClick={() => openWhatsAppChat(reg.phone)} title="واتساب" className="p-0 h-5 w-5 text-green-600 shrink-0" disabled={!isValidPhoneForWhatsApp(reg.phone)}>
                                <Phone className="w-3 h-3" />
                              </Button>
                            </div>
                          </TableCell>
                          <TableCell className="px-1 py-1.5 align-top break-words whitespace-normal">{reg.governorate}</TableCell>
                          <TableCell className="px-1 py-1.5 align-top">{getStatusBadge(reg.status)}</TableCell>
                          <TableCell className="px-1 py-1.5 align-top">{getMembershipBadge(reg.membership_status)}</TableCell>
                          <TableCell className="px-1 py-1.5 align-top text-[11px] text-gray-500 whitespace-normal">{reg.created_at ? new Date(reg.created_at).toLocaleDateString('ar-IQ') : '-'}</TableCell>
                          <TableCell className="px-1 py-1.5 align-top text-[11px] text-gray-700 break-words whitespace-normal">{reg.last_modified_by || '-'}</TableCell>
                          <TableCell className="px-1 py-1.5 align-top">
                            <div className="flex items-center gap-0.5 flex-wrap max-w-[160px]">
                              <Button variant="outline" size="sm" onClick={() => { setSelectedRegistration(reg); setDetailDialogOpen(true); }} title="عرض التفاصيل" className="h-7 px-1.5 text-[10px] gap-0.5 border-blue-200 text-blue-700">
                                <Eye className="w-3.5 h-3.5" /> تفاصيل
                              </Button>
                              {permissions.edit && (
                                <Button variant="outline" size="sm" onClick={() => openEdit(reg)} title="تعديل العضو" className="h-7 px-1.5 text-[10px] gap-0.5 border-amber-200 text-amber-700">
                                  <Pencil className="w-3.5 h-3.5" /> تعديل
                                </Button>
                              )}
                              {permissions.export && (
                                <Button variant="outline" size="sm" disabled={savingPdf} onClick={() => saveMemberPdf(reg)} title="حفظ PDF" className="h-7 px-1.5 text-[10px] gap-0.5 border-emerald-200 text-emerald-700">
                                  <Save className="w-3.5 h-3.5" /> حفظ
                                </Button>
                              )}
                              {permissions.edit && reg.status !== 'approved' && (<Button variant="ghost" size="sm" onClick={() => updateStatus(reg.id, 'approved')} title="قبول" className="h-7 w-7 p-0 text-green-600"><CheckCircle className="w-3.5 h-3.5" /></Button>)}
                              {permissions.edit && reg.status !== 'rejected' && (<Button variant="ghost" size="sm" onClick={() => updateStatus(reg.id, 'rejected')} title="رفض" className="h-7 w-7 p-0 text-red-600"><XCircle className="w-3.5 h-3.5" /></Button>)}
                              {permissions.delete && (<Button variant="ghost" size="sm" onClick={() => deleteRegistration(reg.id)} title="حذف" className="h-7 w-7 p-0 text-gray-500"><Trash2 className="w-3.5 h-3.5" /></Button>)}
                            </div>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                  <p className="text-[11px] text-gray-400 px-3 py-2 border-t">
                    للمزيد من الحقول (تاريخ الموافقة، …) استخدم «عرض التفاصيل». المستخدم: {currentUserName || '-'}
                  </p>
                </div>

                {/* Mobile / narrow: cards with essentials + details */}
                <div className="md:hidden space-y-3 p-3">
                  {registrations.map((reg) => (
                    <Card key={reg.id} className="border shadow-sm">
                      <CardContent className="p-3 space-y-2">
                        <div className="flex items-start justify-between gap-2">
                          <h3 className="font-bold text-gray-800 text-sm leading-snug">{reg.business_name}</h3>
                          {getStatusBadge(reg.status)}
                        </div>
                        <div className="flex items-center gap-2 flex-wrap">
                          {reg.membership_number && <Badge className="bg-blue-50 text-blue-700 hover:bg-blue-50 font-mono text-xs">{reg.membership_number}</Badge>}
                          {getMembershipBadge(reg.membership_status)}
                        </div>
                        <div className="grid grid-cols-2 gap-1.5 text-xs text-gray-600">
                          <div><span className="font-medium">التاجر:</span> {reg.merchant_name}</div>
                          <div className="flex items-center gap-1"><span className="font-medium">الهاتف:</span> <span dir="ltr">{reg.phone}</span></div>
                          <div><span className="font-medium">المحافظة:</span> {reg.governorate}</div>
                          <div><span className="font-medium">التاريخ:</span> {reg.created_at ? new Date(reg.created_at).toLocaleDateString('ar-IQ') : '-'}</div>
                          <div className="col-span-2"><span className="font-medium">آخر تعديل:</span> {reg.last_modified_by || '-'}</div>
                        </div>
                        <div className="flex items-center gap-2 pt-2 border-t flex-wrap">
                          <Checkbox
                            checked={selectedIds.includes(reg.id)}
                            onCheckedChange={(v) => toggleSelect(reg, !!v)}
                          />
                          <Button size="sm" variant="outline" onClick={() => { setSelectedRegistration(reg); setDetailDialogOpen(true); }} className="flex items-center gap-1"><Eye className="w-3 h-3" /> عرض التفاصيل</Button>
                          {permissions.edit && (
                            <Button size="sm" variant="outline" onClick={() => openEdit(reg)} className="flex items-center gap-1 text-amber-700 border-amber-200">
                              <Pencil className="w-3 h-3" /> تعديل
                            </Button>
                          )}
                          {permissions.export && (
                            <Button size="sm" variant="outline" disabled={savingPdf} onClick={() => saveMemberPdf(reg)} className="flex items-center gap-1 text-emerald-700 border-emerald-200">
                              <Save className="w-3 h-3" /> حفظ
                            </Button>
                          )}
                          {permissions.edit && reg.status !== 'approved' && (<Button size="sm" onClick={() => updateStatus(reg.id, 'approved')} className="flex items-center gap-1 bg-green-600 hover:bg-green-700 text-white"><CheckCircle className="w-3 h-3" /> قبول</Button>)}
                          {permissions.edit && reg.status !== 'rejected' && (<Button size="sm" variant="destructive" onClick={() => updateStatus(reg.id, 'rejected')} className="flex items-center gap-1"><XCircle className="w-3 h-3" /> رفض</Button>)}
                          {permissions.delete && (<Button size="sm" variant="outline" onClick={() => deleteRegistration(reg.id)} className="flex items-center gap-1 text-red-600 border-red-200"><Trash2 className="w-3 h-3" /> حذف</Button>)}
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                </div>

                <div className="flex flex-col sm:flex-row items-center justify-between gap-3 p-4 border-t">
                  <p className="text-sm text-gray-500">
                    {total === 0 ? 'لا توجد نتائج' : `عرض ${currentPage * pageSize + 1} - ${Math.min((currentPage + 1) * pageSize, total)} من ${total}`}
                  </p>
                  <div className="flex items-center gap-2">
                    <Button variant="outline" size="sm" disabled={currentPage === 0} onClick={() => setCurrentPage(prev => prev - 1)}>السابق</Button>
                    <span className="text-xs text-gray-500 px-1">
                      صفحة {currentPage + 1} / {Math.max(1, Math.ceil(total / pageSize))}
                    </span>
                    <Button variant="outline" size="sm" disabled={(currentPage + 1) * pageSize >= total} onClick={() => setCurrentPage(prev => prev + 1)}>التالي</Button>
                  </div>
                </div>
              </>
            )}
          </CardContent>
        </Card>
      </main>

      {/* Join message dialog */}
      <Dialog open={joinMsgOpen} onOpenChange={setJoinMsgOpen}>
        <DialogContent className="max-w-md" dir="rtl">
          <DialogHeader>
            <DialogTitle className="text-right">رسالة الانضمام</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 text-right">
            <p className="text-sm text-gray-600">
              اختر طريقة إرسال رسالة الترحيب للعضو {joinMsgTarget?.merchant_name || ''}.
            </p>
            <Button className="w-full text-white" style={{ background: brand.button_color }} onClick={joinWhatsAppOnly}>
              فتح واتساب فقط
            </Button>
            <Button
              className="w-full"
              variant="outline"
              disabled={savingPdf}
              onClick={joinDownloadThenWhatsApp}
            >
              {savingPdf ? 'جاري تنزيل الملف...' : 'تنزيل ملف العضو ثم فتح واتساب'}
            </Button>
            <p className="text-xs text-gray-500">
              واتساب ويب لا يدعم إرفاق الملف تلقائيًا — بعد التنزيل أرفق PDF يدويًا.
            </p>
          </div>
        </DialogContent>
      </Dialog>

      {/* Export / Print record-limit dialog */}
      <Dialog open={exportDialogOpen || printDialogOpen} onOpenChange={(open) => { setExportDialogOpen(open); setPrintDialogOpen(open); }}>
        <DialogContent className="max-w-md" dir="rtl">
          <DialogHeader>
            <DialogTitle className="text-right">
              {exportMode === 'excel' ? 'تصدير Excel' : 'طباعة التقرير'}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3 text-right">
            <p className="text-sm text-gray-600">
              يعتمد التقرير على نتائج البحث والفلاتر والترتيب الحالية. اختر عدد السجلات:
            </p>
            <Select value={recordLimitChoice} onValueChange={setRecordLimitChoice}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {RECORD_LIMIT_OPTIONS.map((o) => (
                  <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            {recordLimitChoice === 'custom' && (
              <div className="space-y-1">
                <Label>العدد المخصص</Label>
                <Input
                  type="number"
                  min={1}
                  max={5000}
                  value={customRecordLimit}
                  onChange={(e) => setCustomRecordLimit(e.target.value)}
                  className="text-right"
                />
              </div>
            )}
            <Button className="w-full text-white" style={{ background: brand.button_color || brand.secondary_color }} onClick={confirmExportOrPrint}>
              {exportMode === 'excel' ? 'تصدير الآن' : 'فتح معاينة الطباعة'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Image Dialog */}
      <Dialog open={imageDialogOpen} onOpenChange={setImageDialogOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader><DialogTitle className="text-right">صورة شاشة النشاط التجاري</DialogTitle></DialogHeader>
          {selectedImage && (<div className="flex items-center justify-center p-4"><img src={selectedImage} alt="صورة النشاط التجاري" className="max-w-full max-h-[60vh] rounded-lg object-contain" /></div>)}
        </DialogContent>
      </Dialog>

      {/* Detail Dialog */}
      <Dialog open={detailDialogOpen} onOpenChange={setDetailDialogOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader><DialogTitle className="text-right">تفاصيل الطلب</DialogTitle></DialogHeader>
          {selectedRegistration && (
            <div className="space-y-4 text-right">
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div className="space-y-1"><p className="text-gray-500 text-xs">اسم النشاط التجاري</p><p className="font-medium">{selectedRegistration.business_name}</p></div>
                <div className="space-y-1"><p className="text-gray-500 text-xs">اسم التاجر</p><p className="font-medium">{selectedRegistration.merchant_name}</p></div>
                <div className="space-y-1"><p className="text-gray-500 text-xs">رقم الهاتف</p><p className="font-medium font-mono" dir="ltr">{selectedRegistration.phone}</p></div>
                <div className="space-y-1"><p className="text-gray-500 text-xs">المحافظة</p><p className="font-medium">{selectedRegistration.governorate}</p></div>
                <div className="space-y-1"><p className="text-gray-500 text-xs">المنطقة</p><p className="font-medium">{selectedRegistration.area}</p></div>
                <div className="space-y-1"><p className="text-gray-500 text-xs">نوع النشاط</p><p className="font-medium">{selectedRegistration.business_type || '-'}</p></div>
                <div className="space-y-1"><p className="text-gray-500 text-xs">حالة الطلب</p>{getStatusBadge(selectedRegistration.status)}</div>
                <div className="space-y-1"><p className="text-gray-500 text-xs">رقم العضوية</p><p className="font-medium font-mono">{selectedRegistration.membership_number || '-'}</p></div>
                <div className="space-y-1"><p className="text-gray-500 text-xs">رقم الطلب</p><p className="font-medium font-mono">{selectedRegistration.request_number || '-'}</p></div>
                <div className="space-y-1"><p className="text-gray-500 text-xs">حالة العضوية</p>{getMembershipBadge(selectedRegistration.membership_status)}</div>
                <div className="space-y-1"><p className="text-gray-500 text-xs">تاريخ التقديم</p><p className="font-medium">{selectedRegistration.created_at ? new Date(selectedRegistration.created_at).toLocaleDateString('ar-IQ') : '-'}</p></div>
                <div className="space-y-1"><p className="text-gray-500 text-xs">تاريخ الموافقة</p><p className="font-medium">{selectedRegistration.approved_at && selectedRegistration.approved_at !== '' ? new Date(selectedRegistration.approved_at).toLocaleDateString('ar-IQ') : '-'}</p></div>
                <div className="space-y-1"><p className="text-gray-500 text-xs">آخر تعديل بواسطة</p><p className="font-medium">{selectedRegistration.last_modified_by || '-'}</p></div>
              </div>
              {selectedRegistration.extra_fields && Object.keys(selectedRegistration.extra_fields).length > 0 && (
                <div className="bg-amber-50/60 p-3 rounded-lg space-y-2">
                  <p className="text-gray-600 text-xs font-medium">حقول إضافية</p>
                  <div className="grid grid-cols-2 gap-2 text-sm">
                    {Object.entries(selectedRegistration.extra_fields).map(([key, entry]) => (
                      <div key={key} className="space-y-0.5">
                        <p className="text-gray-500 text-xs">{entry?.label || key}</p>
                        <p className="font-medium">{
                          Array.isArray(entry?.value) ? entry.value.join(', ') : (entry?.value ?? '-')
                        }</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {selectedRegistration.notes && (<div className="bg-gray-50 p-3 rounded-lg"><p className="text-gray-500 text-xs mb-1">ملاحظات</p><p className="text-sm">{selectedRegistration.notes}</p></div>)}
              {/* Membership Status Control */}
              {selectedRegistration.status === 'approved' && permissions.edit && (
                <div className="bg-blue-50 p-3 rounded-lg space-y-2">
                  <p className="text-sm font-medium text-blue-800">تغيير حالة العضوية:</p>
                  <div className="flex gap-2">
                    <Button size="sm" variant={selectedRegistration.membership_status === 'active' ? 'default' : 'outline'} onClick={() => { updateMembershipStatus(selectedRegistration.id, 'active'); setDetailDialogOpen(false); }} className="text-xs">فعال</Button>
                    <Button size="sm" variant={selectedRegistration.membership_status === 'suspended' ? 'default' : 'outline'} onClick={() => { updateMembershipStatus(selectedRegistration.id, 'suspended'); setDetailDialogOpen(false); }} className="text-xs">معلق</Button>
                    <Button size="sm" variant={selectedRegistration.membership_status === 'expired' ? 'default' : 'outline'} onClick={() => { updateMembershipStatus(selectedRegistration.id, 'expired'); setDetailDialogOpen(false); }} className="text-xs">منتهي</Button>
                  </div>
                </div>
              )}
              <div className="flex gap-2 pt-2 flex-wrap">
                {permissions.edit && (
                  <Button size="sm" variant="outline" onClick={() => { setDetailDialogOpen(false); openEdit(selectedRegistration); }} className="flex items-center gap-1 text-amber-700 border-amber-200">
                    <Pencil className="w-3 h-3" /> تعديل العضو
                  </Button>
                )}
                {permissions.export && (
                  <Button size="sm" variant="outline" disabled={savingPdf} onClick={() => saveMemberPdf(selectedRegistration)} className="flex items-center gap-1 text-emerald-700 border-emerald-200">
                    <Save className="w-3 h-3" /> حفظ PDF
                  </Button>
                )}
                {selectedRegistration.image_key !== 'manual_entry' && (<Button size="sm" variant="outline" onClick={() => { viewImage(selectedRegistration.image_key); setDetailDialogOpen(false); }} className="flex items-center gap-1"><Eye className="w-3 h-3" /> عرض الصورة</Button>)}
                <Button size="sm" variant="outline" onClick={() => openWhatsAppChat(selectedRegistration.phone)} className="flex items-center gap-1 text-green-600 border-green-200" disabled={!isValidPhoneForWhatsApp(selectedRegistration.phone)}><Phone className="w-3 h-3" /> مراسلة واتساب</Button>
                {selectedRegistration.status === 'approved' && (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => openJoinMessageDialog(selectedRegistration)}
                    className="flex items-center gap-1 text-green-600 border-green-200"
                    disabled={!isValidPhoneForWhatsApp(selectedRegistration.phone)}
                  >
                    <Send className="w-3 h-3" /> رسالة الانضمام
                  </Button>
                )}
                {selectedRegistration.status === 'pending' && (<Button size="sm" variant="outline" onClick={() => openWhatsAppRegistration(selectedRegistration.phone, selectedRegistration.merchant_name, selectedRegistration.business_name)} className="flex items-center gap-1 text-green-600 border-green-200" disabled={!isValidPhoneForWhatsApp(selectedRegistration.phone)}><MessageCircle className="w-3 h-3" /> رسالة استلام</Button>)}
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Edit Member Dialog */}
      <Dialog open={editDialogOpen} onOpenChange={setEditDialogOpen}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto" dir="rtl">
          <DialogHeader><DialogTitle className="text-right">تعديل بيانات العضو</DialogTitle></DialogHeader>
          <div className="space-y-3 text-right">
            <div className="space-y-1">
              <Label>رقم العضوية</Label>
              <Input value={editForm.membership_number} onChange={(e) => setEditForm((p) => ({ ...p, membership_number: e.target.value }))} className="text-right font-mono" />
            </div>
            <div className="space-y-1">
              <Label>اسم النشاط</Label>
              <Input value={editForm.business_name} onChange={(e) => setEditForm((p) => ({ ...p, business_name: e.target.value }))} className="text-right" />
            </div>
            <div className="space-y-1">
              <Label>اسم التاجر</Label>
              <Input value={editForm.merchant_name} onChange={(e) => setEditForm((p) => ({ ...p, merchant_name: e.target.value }))} className="text-right" />
            </div>
            <div className="space-y-1">
              <Label>الهاتف</Label>
              <Input value={editForm.phone} onChange={(e) => setEditForm((p) => ({ ...p, phone: e.target.value }))} className="text-right" dir="ltr" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label>المحافظة</Label>
                <Select value={editForm.governorate} onValueChange={(v) => setEditForm((p) => ({ ...p, governorate: v }))}>
                  <SelectTrigger><SelectValue placeholder="المحافظة" /></SelectTrigger>
                  <SelectContent>
                    {governorates.map((g) => <SelectItem key={g} value={g}>{g}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label>المنطقة</Label>
                <Input value={editForm.area} onChange={(e) => setEditForm((p) => ({ ...p, area: e.target.value }))} className="text-right" />
              </div>
            </div>
            <div className="space-y-1">
              <Label>نوع النشاط</Label>
              <Select value={editForm.business_type || undefined} onValueChange={(v) => setEditForm((p) => ({ ...p, business_type: v }))}>
                <SelectTrigger><SelectValue placeholder="نوع النشاط" /></SelectTrigger>
                <SelectContent>
                  {businessTypes.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label>حالة الطلب</Label>
                <Select value={editForm.status} onValueChange={(v) => setEditForm((p) => ({ ...p, status: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="pending">قيد المراجعة</SelectItem>
                    <SelectItem value="approved">مقبول</SelectItem>
                    <SelectItem value="rejected">مرفوض</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label>حالة العضوية</Label>
                <Select value={editForm.membership_status} onValueChange={(v) => setEditForm((p) => ({ ...p, membership_status: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="active">فعال</SelectItem>
                    <SelectItem value="suspended">معلق</SelectItem>
                    <SelectItem value="expired">منتهي</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-1">
              <Label>الملاحظات</Label>
              <Textarea value={editForm.notes} onChange={(e) => setEditForm((p) => ({ ...p, notes: e.target.value }))} className="text-right" />
            </div>
            <Button className="w-full text-white" style={{ background: brand.button_color }} disabled={editLoading} onClick={saveEdit}>
              {editLoading ? 'جاري الحفظ...' : 'حفظ التعديلات'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Add Member Dialog */}
      <Dialog open={addMemberDialogOpen} onOpenChange={setAddMemberDialogOpen}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle className="text-right">إضافة عضو يدوياً</DialogTitle></DialogHeader>
          <div className="space-y-4 text-right">
            <div className="space-y-2">
              <Label className="text-sm font-medium">اسم النشاط التجاري *</Label>
              <Input value={newMember.business_name} onChange={(e) => setNewMember(prev => ({ ...prev, business_name: e.target.value }))} className="text-right" placeholder="أدخل اسم النشاط" />
            </div>
            <div className="space-y-2">
              <Label className="text-sm font-medium">اسم التاجر *</Label>
              <Input value={newMember.merchant_name} onChange={(e) => setNewMember(prev => ({ ...prev, merchant_name: e.target.value }))} className="text-right" placeholder="أدخل اسم التاجر" />
            </div>
            <div className="space-y-2">
              <Label className="text-sm font-medium">رقم الهاتف *</Label>
              <Input value={newMember.phone} onChange={(e) => setNewMember(prev => ({ ...prev, phone: e.target.value }))} dir="ltr" className="text-right" placeholder="07XXXXXXXXX" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2">
                <Label className="text-sm font-medium">المحافظة *</Label>
                <Select value={newMember.governorate} onValueChange={(val) => setNewMember(prev => ({ ...prev, governorate: val }))}>
                  <SelectTrigger><SelectValue placeholder="اختر" /></SelectTrigger>
                  <SelectContent>{governorates.map(g => (<SelectItem key={g} value={g}>{g}</SelectItem>))}</SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label className="text-sm font-medium">المنطقة *</Label>
                <Input value={newMember.area} onChange={(e) => setNewMember(prev => ({ ...prev, area: e.target.value }))} className="text-right" placeholder="المنطقة" />
              </div>
            </div>
            <div className="space-y-2">
              <Label className="text-sm font-medium">نوع النشاط التجاري *</Label>
              <Select value={newMember.business_type} onValueChange={(val) => setNewMember(prev => ({ ...prev, business_type: val }))}>
                <SelectTrigger><SelectValue placeholder="اختر النوع" /></SelectTrigger>
                <SelectContent>{businessTypes.map(t => (<SelectItem key={t} value={t}>{t}</SelectItem>))}</SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label className="text-sm font-medium">حالة العضوية</Label>
              <Select value={newMember.membership_status} onValueChange={(val) => setNewMember(prev => ({ ...prev, membership_status: val }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="active">فعال</SelectItem>
                  <SelectItem value="suspended">معلق</SelectItem>
                  <SelectItem value="expired">منتهي</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {/* Image upload for manual member */}
            <div className="space-y-2">
              <Label className="text-sm font-medium">صورة (اختياري)</Label>
              <div
                onClick={() => memberFileInputRef.current?.click()}
                className="border-2 border-dashed border-gray-300 rounded-lg p-4 text-center cursor-pointer hover:border-primary hover:bg-primary/5 transition-colors"
              >
                {memberImagePreview ? (
                  <div className="space-y-2">
                    <img src={memberImagePreview} alt="معاينة" className="max-h-24 mx-auto rounded-lg object-cover" />
                    <p className="text-xs text-gray-500">اضغط لتغيير الصورة</p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <Upload className="w-6 h-6 mx-auto text-gray-400" />
                    <p className="text-sm text-gray-500">اضغط لرفع صورة (اختياري)</p>
                  </div>
                )}
              </div>
              <input
                ref={memberFileInputRef}
                type="file"
                accept=".jpg,.jpeg,.png"
                onChange={handleMemberImageChange}
                className="hidden"
              />
            </div>
            <div className="space-y-2">
              <Label className="text-sm font-medium">ملاحظات</Label>
              <Textarea value={newMember.notes} onChange={(e) => setNewMember(prev => ({ ...prev, notes: e.target.value }))} className="text-right" placeholder="ملاحظات اختيارية..." />
            </div>
            <Button onClick={addMember} disabled={addMemberLoading} className="w-full bg-primary text-white">
              {addMemberLoading ? 'جاري الإضافة...' : 'إضافة العضو'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}