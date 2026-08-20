import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import html2canvas from 'html2canvas';
import jsPDF from 'jspdf';
import {
  Award, BarChart3, Building2, FileSpreadsheet, Link2, LogOut,
  Plus, Printer, Receipt, Save, Shield, Users,
} from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Textarea } from '@/components/ui/textarea';
import { useToast } from '@/hooks/use-toast';
import { useBrand } from '@/lib/brand';
import { client, downloadAuthorizedFile, getApiBase, localAuth } from '@/lib/localApi';
import { ROUTES } from '@/lib/routes';

type PermissionMap = Record<string, boolean>;
type Company = {
  id: number; name: string; service_type_id: number; service_type_name: string;
  status: string; contact_info?: string; notes?: string;
  current_contract?: { commission_method: string; commission_value: number; version: number } | null;
};
type ServiceType = { id: number; name: string; code: string };
type Account = {
  id: number; member_id: number; member_name: string; membership_number?: string;
  governorate: string; company_id: number; company_name: string; service_type_name: string;
  registered_name?: string; registered_phone?: string; customer_code?: string;
  statement_url?: string; notes?: string; is_active: boolean;
};
type MonthlyRow = Account & {
  operation_count: number; gross_business_value: number;
  commission_method?: string; commission_value?: number; revenue_amount?: number;
};

const current = new Date();
const api = (url: string, method = 'GET', data?: unknown) =>
  client.apiCall.invoke({ url, method, data });
const money = (value: number | string | undefined) =>
  `${Number(value || 0).toLocaleString('en-US', { maximumFractionDigits: 3 })} د.ع`;

export default function FinancialActivities() {
  const { toast } = useToast();
  const navigate = useNavigate();
  const { brand, resolveAssetUrl } = useBrand();
  const certificateRef = useRef<HTMLDivElement>(null);
  const [ready, setReady] = useState(false);
  const [denied, setDenied] = useState(false);
  const [permissions, setPermissions] = useState<PermissionMap>({});
  const [superAdmin, setSuperAdmin] = useState(false);
  const can = (key: string) => superAdmin || !!permissions[key];
  const [services, setServices] = useState<ServiceType[]>([]);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [year, setYear] = useState(current.getFullYear());
  const [month, setMonth] = useState(current.getMonth() + 1);
  const [companyId, setCompanyId] = useState('');
  const [monthlyRows, setMonthlyRows] = useState<MonthlyRow[]>([]);
  const [periodStatus, setPeriodStatus] = useState('not_started');
  const [dashboard, setDashboard] = useState<any>(null);
  const [expenses, setExpenses] = useState<any[]>([]);
  const [reports, setReports] = useState<any[]>([]);
  const [ranking, setRanking] = useState<any[]>([]);
  const [winner, setWinner] = useState<any>(null);
  const [certificate, setCertificate] = useState<any>(null);
  const [certificateOpen, setCertificateOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [companyForm, setCompanyForm] = useState({
    name: '', service_type_id: '', contact_info: '', status: 'active',
    contract_start: '', contract_end: '', notes: '',
  });
  const [contractForm, setContractForm] = useState({
    company_id: '', commission_method: 'fixed_per_operation',
    commission_value: '', effective_from: new Date().toISOString().slice(0, 10),
    effective_to: '', notes: '', attachment_key: '',
  });
  const [accountForm, setAccountForm] = useState({
    member_id: '', company_id: '', registered_name: '', registered_phone: '',
    customer_code: '', statement_url: '', notes: '',
  });
  const [memberOptions, setMemberOptions] = useState<any[]>([]);
  const [expenseForm, setExpenseForm] = useState({
    expense_date: new Date().toISOString().slice(0, 10), category: '',
    description: '', amount: '', notes: '', receipt_key: '',
  });

  const visibleTabs = useMemo(() => ({
    overview: can('view_revenue') || can('view_profits'),
    companies: can('view_companies') || can('manage_companies_contracts'),
    accounts: can('manage_member_company_accounts') || can('view_companies'),
    monthly: can('monthly_entry'),
    expenses: can('view_expenses') || can('enter_expenses'),
    reports: can('view_financial_reports'),
    ranking: can('view_financial_reports') || can('issue_distinguished_certificate'),
  }), [permissions, superAdmin]);

  const loadCommon = async () => {
    const [access, svc, cmp] = await Promise.all([
      api('/api/v1/admin/financial/access'),
      api('/api/v1/admin/financial/service-types'),
      api('/api/v1/admin/financial/companies'),
    ]);
    setPermissions(access.data.permissions || {});
    setSuperAdmin(!!access.data.is_super_admin);
    setServices(svc.data.items || []);
    setCompanies(cmp.data.items || []);
    if (!companyId && cmp.data.items?.length) setCompanyId(String(cmp.data.items[0].id));
  };

  useEffect(() => {
    (async () => {
      try {
        const me = await client.auth.me();
        if (!me.data) throw new Error('unauthorized');
        await loadCommon();
        setReady(true);
      } catch {
        setDenied(true);
      }
    })();
  }, []);

  useEffect(() => {
    if (!ready) return;
    const tasks: Promise<any>[] = [];
    if (visibleTabs.overview) tasks.push(api(`/api/v1/admin/financial/dashboard?accounting_year=${year}&accounting_month=${month}`).then(r => setDashboard(r.data)));
    if (visibleTabs.expenses) tasks.push(api(`/api/v1/admin/financial/expenses?accounting_year=${year}&accounting_month=${month}`).then(r => setExpenses(r.data.items || [])));
    if (visibleTabs.accounts) tasks.push(api('/api/v1/admin/financial/member-accounts').then(r => setAccounts(r.data.items || [])));
    if (can('manage_member_company_accounts')) tasks.push(api('/api/v1/admin/financial/members').then(r => setMemberOptions(r.data.items || [])));
    Promise.allSettled(tasks);
  }, [ready, year, month, permissions, superAdmin]);

  const notifyError = (error: any) =>
    toast({ title: 'تعذر إكمال العملية', description: error?.message || 'حدث خطأ غير متوقع', variant: 'destructive' });

  const saveCompany = async () => {
    setBusy(true);
    try {
      await api('/api/v1/admin/financial/companies', 'POST', {
        ...companyForm, service_type_id: Number(companyForm.service_type_id),
        contract_start: companyForm.contract_start || null,
        contract_end: companyForm.contract_end || null,
      });
      setCompanyForm({ name: '', service_type_id: '', contact_info: '', status: 'active', contract_start: '', contract_end: '', notes: '' });
      await loadCommon();
      toast({ title: 'تمت إضافة الشركة' });
    } catch (e) { notifyError(e); } finally { setBusy(false); }
  };

  const saveContract = async () => {
    setBusy(true);
    try {
      await api(`/api/v1/admin/financial/companies/${contractForm.company_id}/contracts`, 'POST', {
        commission_method: contractForm.commission_method,
        commission_value: Number(contractForm.commission_value),
        effective_from: contractForm.effective_from,
        effective_to: contractForm.effective_to || null,
        attachment_key: contractForm.attachment_key || null,
        notes: contractForm.notes || null,
      });
      await loadCommon();
      toast({ title: 'تم حفظ نسخة العقد والعمولة' });
    } catch (e) { notifyError(e); } finally { setBusy(false); }
  };

  const saveAccount = async () => {
    setBusy(true);
    try {
      await api('/api/v1/admin/financial/member-accounts', 'POST', {
        ...accountForm, member_id: Number(accountForm.member_id), company_id: Number(accountForm.company_id),
        statement_url: accountForm.statement_url || null, is_active: true,
      });
      const res = await api('/api/v1/admin/financial/member-accounts');
      setAccounts(res.data.items || []);
      toast({ title: 'تم حفظ ارتباط العضو بالشركة' });
    } catch (e) { notifyError(e); } finally { setBusy(false); }
  };

  const loadMonthly = async () => {
    if (!companyId) return;
    setBusy(true);
    try {
      const res = await api(`/api/v1/admin/financial/monthly-entry?company_id=${companyId}&accounting_year=${year}&accounting_month=${month}`);
      setMonthlyRows(res.data.items || []);
      setPeriodStatus(res.data.status);
    } catch (e) { notifyError(e); } finally { setBusy(false); }
  };

  const updateMonthly = (memberId: number, field: 'operation_count' | 'gross_business_value', value: string) =>
    setMonthlyRows(rows => rows.map(row => row.member_id === memberId ? { ...row, [field]: Number(value || 0) } : row));

  const saveMonthly = async (markComplete = false) => {
    setBusy(true);
    try {
      const res = await api('/api/v1/admin/financial/monthly-entry/bulk', 'PUT', {
        company_id: Number(companyId), accounting_year: year, accounting_month: month,
        mark_complete: markComplete,
        rows: monthlyRows.map(row => ({
          member_id: row.member_id, operation_count: row.operation_count || 0,
          gross_business_value: row.gross_business_value || 0,
        })),
      });
      setPeriodStatus(res.data.status);
      toast({ title: 'تم الحفظ الجماعي', description: `${res.data.saved} سجل` });
    } catch (e) { notifyError(e); } finally { setBusy(false); }
  };

  const saveExpense = async () => {
    setBusy(true);
    try {
      await api('/api/v1/admin/financial/expenses', 'POST', {
        ...expenseForm, amount: Number(expenseForm.amount),
        accounting_year: year, accounting_month: month,
        receipt_key: expenseForm.receipt_key || null,
      });
      const res = await api(`/api/v1/admin/financial/expenses?accounting_year=${year}&accounting_month=${month}`);
      setExpenses(res.data.items || []);
      toast({ title: 'تم تسجيل المصروف' });
    } catch (e) { notifyError(e); } finally { setBusy(false); }
  };

  const loadReports = async () => {
    try {
      const res = await api(`/api/v1/admin/financial/reports/members?accounting_year=${year}&accounting_month=${month}`);
      setReports(res.data.items || []);
    } catch (e) { notifyError(e); }
  };

  const exportReports = () =>
    downloadAuthorizedFile(
      `/api/v1/admin/financial/reports/members.xlsx?accounting_year=${year}&accounting_month=${month}`,
      `financial-${year}-${month}.xlsx`,
    ).catch(notifyError);

  const loadRanking = async (basis = 'operations') => {
    try {
      const res = await api(`/api/v1/admin/financial/ranking?accounting_year=${year}&accounting_month=${month}&basis=${basis}`);
      setRanking(res.data.items || []);
      setWinner(res.data.winner);
    } catch (e) { notifyError(e); }
  };

  const confirmWinner = async (row: any, basis = 'operations') => {
    if (!confirm(`تأكيد ${row.member_name} عضوًا مميزًا للشهر؟`)) return;
    try {
      const res = await api('/api/v1/admin/financial/distinguished-members', 'POST', {
        accounting_year: year, accounting_month: month, member_id: row.member_id, ranking_basis: basis,
      });
      setWinner({ id: res.data.id, member_id: row.member_id, ranking_basis: basis });
      toast({ title: 'تم تأكيد العضو المميز' });
    } catch (e) { notifyError(e); }
  };

  const issueCertificate = async () => {
    if (!winner) return;
    try {
      const res = await api('/api/v1/admin/financial/certificates', 'POST', { winner_id: winner.id });
      setCertificate(res.data);
      setCertificateOpen(true);
    } catch (e) { notifyError(e); }
  };

  const downloadCertificatePdf = async () => {
    if (!certificateRef.current || !certificate) return;
    const canvas = await html2canvas(certificateRef.current, { scale: 2, backgroundColor: '#ffffff' });
    const pdf = new jsPDF({ orientation: 'landscape', unit: 'mm', format: 'a4' });
    pdf.addImage(canvas.toDataURL('image/png'), 'PNG', 10, 10, 277, 190);
    pdf.save(`${certificate.certificate_number}.pdf`);
  };

  const uploadPrivate = async (kind: 'contracts' | 'receipts', file: File) => {
    if (file.size > 10 * 1024 * 1024) throw new Error('الحد الأقصى 10MB');
    if (!['application/pdf', 'image/jpeg', 'image/png', 'image/webp'].includes(file.type)) throw new Error('صيغة الملف غير مدعومة');
    const form = new FormData();
    form.append('file', file);
    const res = await fetch(`${getApiBase()}/api/v1/admin/financial/documents/${kind}`, {
      method: 'POST', headers: { Authorization: `Bearer ${localAuth.getToken() || ''}` }, body: form,
    });
    if (!res.ok) throw new Error('فشل رفع المستند');
    return (await res.json()).object_key as string;
  };

  if (denied) return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 p-4" dir="rtl">
      <Card className="max-w-sm w-full"><CardContent className="p-8 text-center space-y-4">
        <Shield className="w-12 h-12 mx-auto text-amber-600" />
        <h2 className="font-bold text-xl">لا توجد صلاحية للإدارة المالية</h2>
        <Button onClick={() => navigate(ROUTES.ADMIN)}>العودة إلى إدارة العضويات</Button>
      </CardContent></Card>
    </div>
  );
  if (!ready) return <div className="min-h-screen flex items-center justify-center" dir="rtl">جاري تحميل الإدارة المالية...</div>;

  return (
    <div className="min-h-screen bg-[#F9FAFB]" dir="rtl">
      <header className="text-white shadow-md" style={{ background: brand.header_color || brand.primary_color }}>
        <div className="max-w-7xl mx-auto px-4 py-3 flex justify-between items-center gap-3 flex-wrap">
          <div className="flex items-center gap-3">
            <img src={resolveAssetUrl(brand.system_logo)} className="w-12 h-12 object-contain" alt={brand.org_abbr} />
            <div><h1 className="font-bold text-xl">الإدارة المالية والنشاطات</h1><p className="text-xs opacity-80">{brand.system_name}</p></div>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" className="bg-white/10 text-white border-white/30" onClick={() => navigate(ROUTES.ADMIN)}>
              إدارة العضويات
            </Button>
            {can('manage_users_permissions') && <Button variant="outline" className="bg-white/10 text-white border-white/30" onClick={() => navigate(ROUTES.ADMIN_USERS)}><Users className="w-4 h-4 ml-1" /> المستخدمون</Button>}
            <Button variant="ghost" className="text-white" onClick={async () => { await client.auth.logout(); navigate(ROUTES.ADMIN_LOGIN); }}><LogOut className="w-4 h-4" /></Button>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto p-4 md:p-6 space-y-4">
        <Card><CardContent className="p-3 flex gap-3 items-end flex-wrap">
          <div><Label>السنة</Label><Input type="number" value={year} onChange={e => setYear(Number(e.target.value))} className="w-28" /></div>
          <div><Label>الشهر</Label><Input type="number" min={1} max={12} value={month} onChange={e => setMonth(Number(e.target.value))} className="w-24" /></div>
          <Badge variant="outline">الفترة الحالية: {month}/{year}</Badge>
        </CardContent></Card>

        <Tabs defaultValue={visibleTabs.overview ? 'overview' : visibleTabs.monthly ? 'monthly' : 'companies'}>
          <TabsList className="h-auto flex flex-wrap justify-start">
            {visibleTabs.overview && <TabsTrigger value="overview"><BarChart3 className="w-4 h-4 ml-1" /> المؤشرات</TabsTrigger>}
            {visibleTabs.companies && <TabsTrigger value="companies"><Building2 className="w-4 h-4 ml-1" /> الشركات والعقود</TabsTrigger>}
            {visibleTabs.accounts && <TabsTrigger value="accounts"><Link2 className="w-4 h-4 ml-1" /> ارتباطات الأعضاء</TabsTrigger>}
            {visibleTabs.monthly && <TabsTrigger value="monthly"><FileSpreadsheet className="w-4 h-4 ml-1" /> الإدخال الشهري</TabsTrigger>}
            {visibleTabs.expenses && <TabsTrigger value="expenses"><Receipt className="w-4 h-4 ml-1" /> المصاريف</TabsTrigger>}
            {visibleTabs.reports && <TabsTrigger value="reports">التقارير</TabsTrigger>}
            {visibleTabs.ranking && <TabsTrigger value="ranking"><Award className="w-4 h-4 ml-1" /> العضو المميز</TabsTrigger>}
          </TabsList>

          <TabsContent value="overview" className="space-y-4">
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
              {[
                ['إيرادات الشهر', money(dashboard?.total_revenue)],
                ['المصاريف', money(dashboard?.total_expenses)],
                ['صافي الربح', money(dashboard?.net_profit)],
                ['إجمالي العمليات', Number(dashboard?.total_operations || 0).toLocaleString('en-US')],
              ].map(([label, value]) => <Card key={label}><CardContent className="p-4"><p className="text-xs text-gray-500">{label}</p><p className="text-xl font-bold mt-1">{value}</p></CardContent></Card>)}
            </div>
            <div className="grid md:grid-cols-2 gap-4">
              <Card><CardContent className="p-4"><h3 className="font-bold mb-3">الإيرادات حسب نوع الخدمة</h3>{dashboard?.by_service?.map((x: any) => <div key={x.name} className="flex justify-between py-2 border-b"><span>{x.name} ({x.operations})</span><b>{money(x.revenue)}</b></div>)}</CardContent></Card>
              <Card><CardContent className="p-4"><h3 className="font-bold mb-3">أعلى الشركات نشاطًا</h3>{dashboard?.top_companies?.map((x: any) => <div key={x.name} className="flex justify-between py-2 border-b"><span>{x.name} ({x.operations})</span><b>{money(x.revenue)}</b></div>)}</CardContent></Card>
            </div>
          </TabsContent>

          <TabsContent value="companies" className="space-y-4">
            {can('manage_companies_contracts') && <div className="grid lg:grid-cols-2 gap-4">
              <Card><CardContent className="p-4 space-y-3"><h3 className="font-bold">إضافة شركة/مقدم خدمة</h3>
                <Input placeholder="اسم الشركة" value={companyForm.name} onChange={e => setCompanyForm({ ...companyForm, name: e.target.value })} />
                <select className="w-full border rounded-md h-10 px-3 bg-white" value={companyForm.service_type_id} onChange={e => setCompanyForm({ ...companyForm, service_type_id: e.target.value })}><option value="">نوع الخدمة</option>{services.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select>
                <Textarea placeholder="بيانات الاتصال والملاحظات" value={companyForm.contact_info} onChange={e => setCompanyForm({ ...companyForm, contact_info: e.target.value })} />
                <div className="grid grid-cols-2 gap-2"><Input type="date" value={companyForm.contract_start} onChange={e => setCompanyForm({ ...companyForm, contract_start: e.target.value })} /><Input type="date" value={companyForm.contract_end} onChange={e => setCompanyForm({ ...companyForm, contract_end: e.target.value })} /></div>
                <Button disabled={busy || !companyForm.name || !companyForm.service_type_id} onClick={saveCompany}><Plus className="w-4 h-4 ml-1" /> إضافة</Button>
              </CardContent></Card>
              <Card><CardContent className="p-4 space-y-3"><h3 className="font-bold">إضافة نسخة عقد/عمولة</h3>
                <select className="w-full border rounded-md h-10 px-3 bg-white" value={contractForm.company_id} onChange={e => setContractForm({ ...contractForm, company_id: e.target.value })}><option value="">الشركة</option>{companies.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select>
                <select className="w-full border rounded-md h-10 px-3 bg-white" value={contractForm.commission_method} onChange={e => setContractForm({ ...contractForm, commission_method: e.target.value })}>
                  <option value="fixed_per_operation">مبلغ ثابت لكل عملية</option><option value="percentage">نسبة من قيمة الأعمال</option><option value="monthly_fixed">مبلغ شهري ثابت</option><option value="custom">قيمة مخصصة</option>
                </select>
                <Input type="number" placeholder="قيمة العمولة" value={contractForm.commission_value} onChange={e => setContractForm({ ...contractForm, commission_value: e.target.value })} />
                <Input type="date" value={contractForm.effective_from} onChange={e => setContractForm({ ...contractForm, effective_from: e.target.value })} />
                <Label className="block border border-dashed rounded p-3 cursor-pointer">إرفاق عقد PDF/صورة
                  <input type="file" className="hidden" accept=".pdf,.jpg,.jpeg,.png,.webp" onChange={async e => { const f = e.target.files?.[0]; if (f) try { setContractForm({ ...contractForm, attachment_key: await uploadPrivate('contracts', f) }); } catch (x) { notifyError(x); } }} />
                </Label>
                {contractForm.attachment_key && <Badge>تم رفع العقد</Badge>}
                <Button disabled={busy || !contractForm.company_id || !contractForm.commission_value} onClick={saveContract}><Save className="w-4 h-4 ml-1" /> حفظ النسخة</Button>
              </CardContent></Card>
            </div>}
            <Card><CardContent className="p-0 overflow-x-auto"><table className="w-full text-sm"><thead className="text-white" style={{ background: brand.table_header_color }}><tr><th className="p-3 text-right">الشركة</th><th>الخدمة</th><th>الحالة</th><th>العمولة الحالية</th></tr></thead><tbody>{companies.map(c => <tr key={c.id} className="border-b"><td className="p-3 font-medium">{c.name}</td><td>{c.service_type_name}</td><td>{c.status === 'active' ? 'فعالة' : 'متوقفة'}</td><td>{c.current_contract ? `${c.current_contract.commission_method} · ${money(c.current_contract.commission_value)}` : 'لا يوجد عقد'}</td></tr>)}</tbody></table></CardContent></Card>
          </TabsContent>

          <TabsContent value="accounts" className="space-y-4">
            {can('manage_member_company_accounts') && <Card><CardContent className="p-4 grid md:grid-cols-3 gap-3">
              <select className="border rounded-md h-10 px-3" value={accountForm.member_id} onChange={e => setAccountForm({ ...accountForm, member_id: e.target.value })}><option value="">العضو</option>{memberOptions.map(m => <option key={m.id} value={m.id}>{m.membership_number} · {m.member_name}</option>)}</select>
              <select className="border rounded-md h-10 px-3" value={accountForm.company_id} onChange={e => setAccountForm({ ...accountForm, company_id: e.target.value })}><option value="">الشركة</option>{companies.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select>
              <Input placeholder="الاسم المسجل لدى الشركة" value={accountForm.registered_name} onChange={e => setAccountForm({ ...accountForm, registered_name: e.target.value })} />
              <Input placeholder="الهاتف المسجل" value={accountForm.registered_phone} onChange={e => setAccountForm({ ...accountForm, registered_phone: e.target.value })} />
              <Input placeholder="كود العميل" value={accountForm.customer_code} onChange={e => setAccountForm({ ...accountForm, customer_code: e.target.value })} />
              <Input placeholder="رابط كشف الشركة" value={accountForm.statement_url} onChange={e => setAccountForm({ ...accountForm, statement_url: e.target.value })} />
              <Textarea placeholder="ملاحظات" value={accountForm.notes} onChange={e => setAccountForm({ ...accountForm, notes: e.target.value })} />
              <Button disabled={busy || !accountForm.member_id || !accountForm.company_id} onClick={saveAccount}>حفظ الارتباط</Button>
            </CardContent></Card>}
            <Card><CardContent className="p-0 overflow-x-auto"><table className="w-full text-sm"><thead><tr className="bg-gray-100"><th className="p-3 text-right">العضو</th><th>الشركة/الخدمة</th><th>الاسم المسجل</th><th>الهاتف/الكود</th><th>الكشف</th></tr></thead><tbody>{accounts.map(a => <tr key={a.id} className="border-b"><td className="p-3">{a.membership_number} · {a.member_name}<small className="block text-gray-500">{a.governorate}</small></td><td>{a.company_name}<small className="block">{a.service_type_name}</small></td><td>{a.registered_name || '-'}</td><td>{a.registered_phone || '-'}<small className="block">{a.customer_code || '-'}</small></td><td>{a.statement_url ? <Button size="sm" variant="outline" onClick={() => window.open(a.statement_url, '_blank', 'noopener,noreferrer')}>فتح كشف الشركة</Button> : '-'}</td></tr>)}</tbody></table></CardContent></Card>
          </TabsContent>

          <TabsContent value="monthly" className="space-y-4">
            <Card><CardContent className="p-4 flex items-end gap-3 flex-wrap">
              <div><Label>الشركة</Label><select className="border rounded-md h-10 px-3 min-w-56" value={companyId} onChange={e => setCompanyId(e.target.value)}>{companies.map(c => <option key={c.id} value={c.id}>{c.service_type_name} · {c.name}</option>)}</select></div>
              <Button onClick={loadMonthly}>تحميل جدول الإدخال</Button><Badge>{periodStatus}</Badge>
            </CardContent></Card>
            <Card><CardContent className="p-0 overflow-x-auto"><table className="w-full text-sm"><thead className="bg-gray-100"><tr><th className="p-3 text-right">العضو</th><th>بيانات الشركة</th><th>الكشف</th><th>عدد العمليات</th>{monthlyRows.some(x => 'revenue_amount' in x) && <th>الإيراد</th>}</tr></thead><tbody>{monthlyRows.map((row, index) => <tr key={row.member_id} className="border-b"><td className="p-3">{row.membership_number} · {row.member_name}<small className="block">{row.governorate}</small></td><td>{row.registered_name || '-'}<small className="block">{row.registered_phone} · {row.customer_code}</small></td><td>{row.statement_url ? <Button size="sm" variant="outline" onClick={() => window.open(row.statement_url, '_blank')}>فتح</Button> : '-'}</td><td><Input className="w-28 text-center" type="number" min={0} value={row.operation_count} onChange={e => updateMonthly(row.member_id, 'operation_count', e.target.value)} onKeyDown={e => { if (e.key === 'Enter') (document.querySelector(`[data-monthly="${index + 1}"]`) as HTMLInputElement)?.focus(); }} data-monthly={index} /></td>{'revenue_amount' in row && <td>{money(row.revenue_amount)}</td>}</tr>)}</tbody></table></CardContent></Card>
            {!!monthlyRows.length && <div className="flex gap-2"><Button disabled={busy || periodStatus === 'closed'} onClick={() => saveMonthly(false)}>حفظ</Button><Button disabled={busy || periodStatus === 'closed'} variant="outline" onClick={() => saveMonthly(true)}>حفظ وإكمال الشركة</Button></div>}
          </TabsContent>

          <TabsContent value="expenses" className="space-y-4">
            {can('enter_expenses') && <Card><CardContent className="p-4 grid md:grid-cols-3 gap-3">
              <Input type="date" value={expenseForm.expense_date} onChange={e => setExpenseForm({ ...expenseForm, expense_date: e.target.value })} />
              <Input placeholder="التصنيف" value={expenseForm.category} onChange={e => setExpenseForm({ ...expenseForm, category: e.target.value })} />
              <Input placeholder="وصف المصروف" value={expenseForm.description} onChange={e => setExpenseForm({ ...expenseForm, description: e.target.value })} />
              <Input type="number" placeholder="المبلغ د.ع" value={expenseForm.amount} onChange={e => setExpenseForm({ ...expenseForm, amount: e.target.value })} />
              <Textarea placeholder="ملاحظات" value={expenseForm.notes} onChange={e => setExpenseForm({ ...expenseForm, notes: e.target.value })} />
              <Label className="border border-dashed rounded p-3 cursor-pointer">إرفاق فاتورة/وصل<input type="file" className="hidden" accept=".pdf,.jpg,.jpeg,.png,.webp" onChange={async e => { const f = e.target.files?.[0]; if (f) try { setExpenseForm({ ...expenseForm, receipt_key: await uploadPrivate('receipts', f) }); } catch (x) { notifyError(x); } }} /></Label>
              <Button disabled={busy || !expenseForm.category || !expenseForm.description || !expenseForm.amount} onClick={saveExpense}>تسجيل المصروف</Button>
            </CardContent></Card>}
            {can('view_expenses') && <Card><CardContent className="p-0 overflow-x-auto"><table className="w-full text-sm"><thead><tr className="bg-gray-100"><th className="p-3">التاريخ</th><th>التصنيف</th><th>الوصف</th><th>المبلغ</th><th>المستخدم</th></tr></thead><tbody>{expenses.map(x => <tr key={x.id} className="border-b text-center"><td className="p-3">{x.expense_date}</td><td>{x.category}</td><td>{x.description}</td><td>{money(x.amount)}</td><td>{x.created_by}</td></tr>)}</tbody></table></CardContent></Card>}
          </TabsContent>

          <TabsContent value="reports" className="space-y-4">
            <div className="flex gap-2"><Button onClick={loadReports}>عرض التقرير</Button>{can('export_excel') && <Button variant="outline" onClick={exportReports}><FileSpreadsheet className="w-4 h-4 ml-1" /> Excel</Button>}{can('print_pdf') && <Button variant="outline" onClick={() => window.print()}><Printer className="w-4 h-4 ml-1" /> طباعة/PDF</Button>}</div>
            <Card><CardContent className="p-0 overflow-x-auto"><table className="w-full text-xs"><thead className="bg-gray-100"><tr><th className="p-3">العضو</th><th>الشحن</th><th>إيراد الشحن</th><th>التوصيل</th><th>إيراد التوصيل</th><th>أخرى</th><th>الإجمالي</th><th>إجمالي الإيراد</th></tr></thead><tbody>{reports.map(x => <tr key={x.member_id} className="border-b text-center"><td className="p-3 text-right">{x.membership_number} · {x.member_name}<small className="block">{x.governorate}</small></td><td>{x.shipping_operations}</td><td>{money(x.shipping_revenue)}</td><td>{x.delivery_operations}</td><td>{money(x.delivery_revenue)}</td><td>{x.other_operations}</td><td>{x.total_operations}</td><td>{money(x.total_revenue)}</td></tr>)}</tbody></table></CardContent></Card>
          </TabsContent>

          <TabsContent value="ranking" className="space-y-4">
            <div className="flex gap-2"><Button onClick={() => loadRanking('operations')}>حسب العمليات</Button><Button variant="outline" onClick={() => loadRanking('revenue')}>حسب الإيراد</Button>{winner && can('issue_distinguished_certificate') && <Button className="bg-amber-600" onClick={issueCertificate}><Award className="w-4 h-4 ml-1" /> إصدار الشهادة</Button>}</div>
            <div className="grid md:grid-cols-3 gap-3">{ranking.slice(0, 12).map((x, i) => <Card key={x.member_id}><CardContent className="p-4"><Badge>#{i + 1}</Badge><h3 className="font-bold mt-2">{x.member_name}</h3><p className="text-sm">{x.membership_number}</p><p>{x.operations} عملية · {money(x.revenue)}</p>{can('issue_distinguished_certificate') && <Button size="sm" variant="outline" className="mt-3" onClick={() => confirmWinner(x)}>اختيار عضو مميز</Button>}</CardContent></Card>)}</div>
          </TabsContent>
        </Tabs>
      </main>

      <Dialog open={certificateOpen} onOpenChange={setCertificateOpen}><DialogContent className="max-w-5xl"><DialogHeader><DialogTitle>شهادة العضو المميز</DialogTitle></DialogHeader>
        {certificate && <div ref={certificateRef} className="aspect-[1.414/1] border-[12px] border-double p-10 text-center flex flex-col justify-center items-center bg-white" style={{ borderColor: brand.secondary_color, color: brand.primary_color }}>
          <img src={resolveAssetUrl(brand.report_logo || brand.system_logo)} className="w-24 h-24 object-contain" alt="" />
          <h2 className="text-2xl font-bold mt-3">{brand.system_name}</h2><h1 className="text-4xl font-bold my-8" style={{ color: brand.secondary_color }}>شهادة العضو المميز للشهر</h1>
          <p className="text-xl">تُمنح إلى</p><h3 className="text-4xl font-bold my-4">{certificate.member_name}</h3><p className="text-lg">رقم العضوية: {certificate.membership_number}</p>
          <p className="max-w-2xl my-6 text-lg">تقديرًا لتميزه ونشاطه وإسهامه الفاعل في مجتمع التجارة الإلكترونية العراقي خلال شهر {certificate.accounting_month}/{certificate.accounting_year}.</p>
          <p className="text-sm">رقم الشهادة: {certificate.certificate_number} · تاريخ الإصدار: {new Date().toLocaleDateString('ar-IQ')}</p>
        </div>}
        <div className="flex gap-2"><Button onClick={() => window.print()}><Printer className="w-4 h-4 ml-1" /> طباعة</Button><Button variant="outline" onClick={downloadCertificatePdf}>تنزيل PDF</Button></div>
      </DialogContent></Dialog>
    </div>
  );
}
