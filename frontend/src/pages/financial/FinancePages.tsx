import { useEffect, useMemo, useState } from 'react';
import { Edit3, Eye, FileDown, FileSpreadsheet, Plus, Printer, ReceiptText, RotateCcw, Save, Wallet } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Progress } from '@/components/ui/progress';
import { Textarea } from '@/components/ui/textarea';
import { financialErpApi } from '@/lib/financialErpApi';
import { useBrand } from '@/lib/brand';
import type { Company, Expense, Revenue, ServiceType } from '@/types/financialErp';
import { CompactTable, Empty, FileButton, FormDialog, PageTitle, SafeDateInput, StatusBadge, ActionButton, formatLatn, money } from './FinancialUi';
import { downloadVoucherPdf, downloadVoucherPdfZip, openVoucherWindow, paymentVoucherHtml, receiptVoucherHtml } from './voucherDocs';

type Props = {
  companies: Company[];
  services: ServiceType[];
  can: (key: string) => boolean;
  notify: (e: unknown) => void;
  success: (message: string) => void;
};
const now = new Date();
const today = () => new Date().toISOString().slice(0, 10);
type SortDir = 'asc' | 'desc';

function Field({ label, children, className = '' }: { label: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={className}>
      <Label className="block mb-1">{label}</Label>
      {children}
    </div>
  );
}
function Metric({ label, value, moneyValue = true }: { label: string; value: number; moneyValue?: boolean }) {
  return (
    <Card>
      <CardContent className="p-4">
        <small className="text-slate-500">{label}</small>
        <b className="block text-xl">{moneyValue ? money(value) : formatLatn(value, { maximumFractionDigits: 0 })}</b>
      </CardContent>
    </Card>
  );
}
function ColSort({
  label,
  active,
  dir,
  onClick,
}: {
  label: string;
  active: boolean;
  dir: SortDir;
  onClick: () => void;
}) {
  return (
    <button type="button" className="inline-flex items-center gap-1 font-semibold hover:text-blue-800" onClick={onClick}>
      {label}
      <span className={`text-xs ${active ? 'text-blue-700' : 'text-slate-300'}`}>{active ? (dir === 'asc' ? '↑' : '↓') : '↕'}</span>
    </button>
  );
}

export function DashboardPage({ companies, notify }: Props) {
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [data, setData] = useState<any>();
  const load = () => financialErpApi.dashboard(year, month).then(setData).catch(notify);
  useEffect(() => {
    void load();
  }, [year, month]);
  const max = Math.max(...(data?.by_company || []).map((x: any) => x.due), 1);
  return (
    <div className="space-y-4">
      <PageTitle title="لوحة المؤشرات" description="الاستحقاق المحاسبي منفصل عن المقبوض الفعلي والمصروفات للفترة المختارة." />
      <Card>
        <CardContent className="p-3 flex gap-2 items-end">
          <Field label="السنة">
            <Input className="w-28" type="number" value={year} onChange={(e) => setYear(Number(e.target.value))} />
          </Field>
          <Field label="الشهر">
            <Input className="w-24" type="number" min={1} max={12} value={month} onChange={(e) => setMonth(Number(e.target.value))} />
          </Field>
          <Button variant="outline" onClick={load}>
            تحديث
          </Button>
        </CardContent>
      </Card>
      <div className="grid grid-cols-2 xl:grid-cols-5 gap-3">
        {[
          ['المستحق المتراكم', data?.accrued_revenue, 'text-blue-700'],
          ['المقبوض الفعلي', data?.actual_revenue, 'text-emerald-700'],
          ['المصاريف', data?.expenses, 'text-red-700'],
          ['الربح التقديري', data?.estimated_profit, 'text-violet-700'],
          ['الرصيد القائم', data?.outstanding_receivable, 'text-amber-700'],
        ].map(([label, value, color]) => (
          <Card key={label as string}>
            <CardContent className="p-4">
              <p className="text-xs text-slate-500">{label}</p>
              <b className={`block text-xl mt-1 ${color}`}>{money(value as number)}</b>
            </CardContent>
          </Card>
        ))}
      </div>
      <div className="grid lg:grid-cols-2 gap-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">الشركات حسب استحقاق MFEC</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {data?.by_company?.slice(0, 10).map((x: any) => (
              <div key={x.name}>
                <div className="flex justify-between text-sm mb-1">
                  <span>{x.name}</span>
                  <b>{money(x.due)}</b>
                </div>
                <Progress value={(x.due / max) * 100} />
              </div>
            ))}
            {!data?.by_company?.length && <Empty />}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">ملخص أنواع الخدمات</CardTitle>
          </CardHeader>
          <CardContent>
            {data?.by_service?.map((x: any) => (
              <div key={x.name} className="grid grid-cols-3 py-3 border-t">
                <b>{x.name}</b>
                <span>{money(x.gross)}</span>
                <span className="font-bold">{money(x.due)}</span>
              </div>
            ))}
            {!data?.by_service?.length && <Empty />}
          </CardContent>
        </Card>
      </div>
      <Card>
        <CardContent className="p-4 grid md:grid-cols-3 gap-4">
          <Metric label="حجم أعمال الأعضاء" value={data?.gross_business_amount} />
          <Metric label="صافي النتيجة الفعلية" value={data?.actual_net_result} />
          <Metric label="عدد الشركات المعرفة" value={companies.length} moneyValue={false} />
        </CardContent>
      </Card>
    </div>
  );
}

const blankRevenue = {
  company_id: '',
  received_at: today(),
  amount: '',
  receipt_method: 'تحويل مصرفي',
  category: 'اشتراك/خدمة',
  description: '',
  period_start: '',
  period_end: '',
  notes: '',
  attachment_key: '',
};

export function RevenuesPage({ companies, can, notify, success }: Props) {
  const { brand, resolveAssetUrl } = useBrand();
  const [rows, setRows] = useState<Revenue[]>([]);
  const [company, setCompany] = useState('');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [deleted, setDeleted] = useState(false);
  const [q, setQ] = useState('');
  const [method, setMethod] = useState('');
  const [category, setCategory] = useState('');
  const [descriptionF, setDescriptionF] = useState('');
  const [yearF, setYearF] = useState('');
  const [monthF, setMonthF] = useState('');
  const [minAmt, setMinAmt] = useState('');
  const [maxAmt, setMaxAmt] = useState('');
  const [statusF, setStatusF] = useState<'all' | 'active' | 'cancelled'>('all');
  const [sortKey, setSortKey] = useState<
    'seq' | 'received_at' | 'amount' | 'receipt_number' | 'company' | 'category' | 'description' | 'method' | 'status'
  >('received_at');
  const [sortDir, setSortDir] = useState<SortDir>('desc');
  const [selected, setSelected] = useState<number[]>([]);
  const [zipBusy, setZipBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const [edit, setEdit] = useState<Revenue>();
  const [form, setForm] = useState<any>(blankRevenue);
  const [previewForm, setPreviewForm] = useState(false);
  const [viewRow, setViewRow] = useState<Revenue>();
  const [allocationOpen, setAllocationOpen] = useState(false);
  const [receipt, setReceipt] = useState<Revenue>();
  const [targets, setTargets] = useState<any>({ statements: [], settlements: [] });
  const [allocation, setAllocation] = useState({ target_type: 'statement', target_id: '', amount: '' });
  const [voucher, setVoucher] = useState<{ next_rec: number; preview_rec: string } | null>(null);
  const [nextRecInput, setNextRecInput] = useState('');

  const loadVoucher = () =>
    financialErpApi
      .voucherNumbers()
      .then((x) => {
        setVoucher({ next_rec: x.next_rec, preview_rec: x.preview_rec });
        setNextRecInput(String(x.next_rec));
      })
      .catch(notify);
  const load = () =>
    financialErpApi
      .revenues({ company_id: company, date_from: from, date_to: to, include_deleted: deleted })
      .then((x) => setRows(x.items))
      .catch(notify);
  useEffect(() => {
    void load();
    void loadVoucher();
  }, [deleted]);

  const companyName = (id: number) => companies.find((c) => c.id === id)?.name || '-';

  const filtered = useMemo(() => {
    const term = q.trim().toLowerCase();
    let list = rows.filter((r) => {
      const cancelled = r.deleted || r.status === 'cancelled';
      if (statusF === 'active' && cancelled) return false;
      if (statusF === 'cancelled' && !cancelled) return false;
      if (method && !(r.receipt_method || '').includes(method)) return false;
      if (category && !(r.category || '').includes(category)) return false;
      if (descriptionF && !(r.description || '').includes(descriptionF)) return false;
      if (yearF) {
        const y = Number(String(r.received_at).slice(0, 4));
        if (y !== Number(yearF)) return false;
      }
      if (monthF) {
        const m = Number(String(r.received_at).slice(5, 7));
        if (m !== Number(monthF)) return false;
      }
      if (minAmt && !(r.amount >= Number(minAmt))) return false;
      if (maxAmt && !(r.amount <= Number(maxAmt))) return false;
      if (!term) return true;
      const blob = [
        r.receipt_number,
        companyName(r.company_id),
        r.received_at,
        r.receipt_method,
        r.category,
        r.description,
        r.notes,
        r.created_by,
        String(r.amount),
      ]
        .join(' ')
        .toLowerCase();
      return blob.includes(term);
    });
    const dir = sortDir === 'asc' ? 1 : -1;
    list = [...list].sort((a, b) => {
      if (sortKey === 'amount') return (a.amount - b.amount) * dir;
      if (sortKey === 'receipt_number') return String(a.receipt_number).localeCompare(String(b.receipt_number), 'en') * dir;
      if (sortKey === 'company') return companyName(a.company_id).localeCompare(companyName(b.company_id), 'ar') * dir;
      if (sortKey === 'category') return String(a.category || '').localeCompare(String(b.category || ''), 'ar') * dir;
      if (sortKey === 'description') return String(a.description || '').localeCompare(String(b.description || ''), 'ar') * dir;
      if (sortKey === 'method') return String(a.receipt_method || '').localeCompare(String(b.receipt_method || ''), 'ar') * dir;
      if (sortKey === 'status') {
        const as = a.deleted || a.status === 'cancelled' ? 1 : 0;
        const bs = b.deleted || b.status === 'cancelled' ? 1 : 0;
        return (as - bs) * dir;
      }
      return String(a.received_at).localeCompare(String(b.received_at)) * dir;
    });
    return list;
  }, [rows, q, method, category, descriptionF, yearF, monthF, minAmt, maxAmt, statusF, sortKey, sortDir, companies]);

  const toggleSort = (key: typeof sortKey) => {
    if (sortKey === key) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    else {
      setSortKey(key);
      setSortDir('asc');
    }
  };

  const resetFilters = () => {
    setQ('');
    setCompany('');
    setFrom('');
    setTo('');
    setMethod('');
    setCategory('');
    setDescriptionF('');
    setYearF('');
    setMonthF('');
    setMinAmt('');
    setMaxAmt('');
    setStatusF('all');
    setDeleted(false);
    setSelected([]);
  };

  const allFilteredSelected = filtered.length > 0 && filtered.every((x) => selected.includes(x.id));
  const toggleSelectAll = (on: boolean) => {
    if (on) setSelected(filtered.map((x) => x.id));
    else setSelected([]);
  };

  const logo = () => resolveAssetUrl(brand.report_logo || brand.system_logo);
  const receiptHtml = (row: Revenue, mode: 'view' | 'print' | 'pdf') =>
    receiptVoucherHtml({
      brand,
      logoUrl: logo(),
      mode,
      row: {
        receipt_number: row.receipt_number,
        company_name: companyName(row.company_id),
        received_at: row.received_at,
        amount: row.amount,
        receipt_method: row.receipt_method,
        category: row.category,
        description: row.description,
        period_start: row.period_start,
        period_end: row.period_end,
        notes: row.notes,
        created_by: row.created_by,
      },
    });

  const viewVoucher = (row: Revenue) => setViewRow(row);
  const printVoucher = (row: Revenue) => {
    try {
      openVoucherWindow(receiptHtml(row, 'print'));
    } catch (e) {
      notify(e);
    }
  };
  const pdfVoucher = async (row: Revenue) => {
    try {
      await downloadVoucherPdf(receiptHtml(row, 'pdf'), `${row.receipt_number}.pdf`);
      success(`تم تنزيل PDF للوصل ${row.receipt_number}`);
    } catch (e) {
      notify(e);
    }
  };

  const exportZip = async () => {
    if (!selected.length) {
      notify(new Error('حدّد وصولًا واحدًا على الأقل قبل تصدير ZIP'));
      return;
    }
    const picks = filtered.filter((x) => selected.includes(x.id));
    if (!picks.length) {
      notify(new Error('الوصولات المحددة غير ظاهرة ضمن النتائج الحالية'));
      return;
    }
    setZipBusy(true);
    try {
      await downloadVoucherPdfZip(
        picks.map((row) => ({
          html: receiptHtml(row, 'pdf'),
          filename: `${row.receipt_number || `REC-${row.id}`}.pdf`,
        })),
        `REC-vouchers-${today()}.zip`,
      );
      success(`تم تنزيل ZIP يحتوي ${picks.length} ملف PDF`);
    } catch (e) {
      notify(e);
    } finally {
      setZipBusy(false);
    }
  };

  const save = async () => {
    if (!form.company_id) {
      notify(new Error('اختر الشركة التي تم استلام المبلغ منها'));
      return;
    }
    if (!form.received_at) {
      notify(new Error('تاريخ القبض مطلوب'));
      return;
    }
    if (!(Number(form.amount) > 0)) {
      notify(new Error('أدخل مبلغ قبض أكبر من صفر'));
      return;
    }
    if (!form.description?.trim()) {
      notify(new Error('بيان الإيراد مطلوب'));
      return;
    }
    try {
      const payload = {
        company_id: Number(form.company_id),
        received_at: form.received_at,
        amount: Number(form.amount),
        receipt_method: form.receipt_method,
        category: form.category || null,
        description: form.description,
        period_start: form.period_start || null,
        period_end: form.period_end || null,
        notes: form.notes || null,
        attachment_key: form.attachment_key || null,
      };
      let saved: Revenue | undefined;
      if (edit) {
        const x = await financialErpApi.updateRevenue(edit.id, payload);
        saved = {
          ...edit,
          ...payload,
          receipt_number: x.receipt_number,
          amount: Number(form.amount),
          allocated: edit.allocated,
          remaining: edit.remaining,
          deleted: false,
          status: 'active',
        };
        success(`تم تعديل وصل القبض ${x.receipt_number}`);
      } else {
        const x = await financialErpApi.createRevenue(payload);
        saved = {
          id: x.id,
          receipt_number: x.receipt_number,
          company_id: Number(form.company_id),
          received_at: form.received_at,
          amount: Number(form.amount),
          allocated: 0,
          remaining: Number(form.amount),
          receipt_method: form.receipt_method,
          category: form.category,
          description: form.description,
          period_start: form.period_start || undefined,
          period_end: form.period_end || undefined,
          notes: form.notes || undefined,
          attachment_key: form.attachment_key || undefined,
          deleted: false,
          status: 'active',
        };
        success(`تم حفظ وصل القبض ${x.receipt_number}`);
      }
      setOpen(false);
      setPreviewForm(false);
      await load();
      await loadVoucher();
      if (saved) setViewRow(saved);
    } catch (e) {
      notify(e);
    }
  };

  const openEdit = (x?: Revenue) => {
    setEdit(x);
    setForm(
      x
        ? {
            ...blankRevenue,
            ...x,
            company_id: String(x.company_id),
            amount: String(x.amount),
            period_start: x.period_start || '',
            period_end: x.period_end || '',
            notes: x.notes || '',
            attachment_key: x.attachment_key || '',
          }
        : blankRevenue,
    );
    setPreviewForm(false);
    setOpen(true);
    void loadVoucher();
  };

  const openAllocation = async (x: Revenue) => {
    try {
      setReceipt(x);
      setTargets(await financialErpApi.allocationTargets(x.id));
      setAllocation({ target_type: 'statement', target_id: '', amount: String(x.remaining) });
      setAllocationOpen(true);
    } catch (e) {
      notify(e);
    }
  };
  const allocate = async () => {
    if (!receipt) return;
    try {
      await financialErpApi.allocateRevenue(receipt.id, {
        statement_id: allocation.target_type === 'statement' ? Number(allocation.target_id) : null,
        settlement_batch_id: allocation.target_type === 'settlement' ? Number(allocation.target_id) : null,
        amount: Number(allocation.amount),
      });
      setAllocationOpen(false);
      await load();
    } catch (e) {
      notify(e);
    }
  };
  const draftPreview = (): Revenue => ({
    id: edit?.id || 0,
    receipt_number: edit?.receipt_number || voucher?.preview_rec || 'REC-…',
    company_id: Number(form.company_id) || 0,
    received_at: form.received_at,
    amount: Number(form.amount) || 0,
    allocated: edit?.allocated || 0,
    remaining: Number(form.amount) || 0,
    receipt_method: form.receipt_method,
    category: form.category,
    description: form.description,
    period_start: form.period_start || undefined,
    period_end: form.period_end || undefined,
    notes: form.notes || undefined,
    attachment_key: form.attachment_key || undefined,
    deleted: false,
    status: 'active',
  });
  const saveNextRec = async () => {
    const n = Number(nextRecInput);
    if (!(n > 0)) {
      notify(new Error('أدخل رقمًا صحيحًا لتالي وصل القبض'));
      return;
    }
    try {
      const x = await financialErpApi.setVoucherNumbers({ next_rec: n });
      setVoucher({ next_rec: x.next_rec, preview_rec: x.preview_rec });
      setNextRecInput(String(x.next_rec));
      success(`تم تعيين الرقم التالي لوصل القبض: ${x.preview_rec}`);
    } catch (e) {
      notify(e);
    }
  };

  const exportIds = selected.length ? selected : filtered.map((x) => x.id);

  return (
    <div className="space-y-4">
      <PageTitle
        title="وصولات القبض"
        description="ترقيم تلقائي REC-xxxx يُحجز فقط عند الحفظ الناجح. الإلغاء يبقي الرقم للتدقيق ولا يعيده للمخزون."
        actions={
          <>
            {can('financial.revenues.create') && (
              <Button onClick={() => openEdit()}>
                <Plus className="w-4 h-4 ml-2" />
                وصل قبض
              </Button>
            )}
            <Button type="button" variant="outline" disabled={zipBusy} onClick={() => void exportZip()}>
              <FileDown className="w-4 h-4 ml-1" />
              {zipBusy ? 'جاري ZIP…' : 'تصدير الوصولات PDF'}
            </Button>
            {can('financial.reports.xlsx') && (
              <Button
                variant="outline"
                onClick={() =>
                  financialErpApi
                    .exportRevenues({
                      company_id: company,
                      date_from: from,
                      date_to: to,
                      selected_ids: exportIds.length ? exportIds : undefined,
                    })
                    .catch(notify)
                }
              >
                <FileSpreadsheet className="w-4 h-4 ml-1" />
                Excel
              </Button>
            )}
          </>
        }
      />
      <Card>
        <CardContent className="p-3 flex flex-wrap gap-3 items-end">
          <Field label="رقم وصل القبض التالي">
            <div className="flex gap-2">
              <Input className="w-36 font-mono" value={nextRecInput} onChange={(e) => setNextRecInput(e.target.value)} placeholder="5" />
              <Button type="button" variant="outline" onClick={() => void saveNextRec()}>
                حفظ
              </Button>
            </div>
          </Field>
          <div className="text-sm text-slate-600 pb-2">
            المعاينة: <b className="font-mono">{voucher?.preview_rec || '—'}</b>
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="p-3 grid sm:grid-cols-2 lg:grid-cols-4 gap-2">
          <Input placeholder="بحث (REC، وصف، شركة، منشئ...)" value={q} onChange={(e) => setQ(e.target.value)} />
          <select className="h-10 border rounded-md px-3" value={company} onChange={(e) => setCompany(e.target.value)}>
            <option value="">كل الشركات</option>
            {companies.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
          <Input placeholder="طريقة القبض" value={method} onChange={(e) => setMethod(e.target.value)} />
          <Input placeholder="التصنيف" value={category} onChange={(e) => setCategory(e.target.value)} />
          <Input placeholder="البيان / الوصف" value={descriptionF} onChange={(e) => setDescriptionF(e.target.value)} />
          <Input type="number" placeholder="السنة" value={yearF} onChange={(e) => setYearF(e.target.value)} />
          <Input type="number" min={1} max={12} placeholder="الشهر" value={monthF} onChange={(e) => setMonthF(e.target.value)} />
          <SafeDateInput className="w-full" value={from} onChange={(e) => setFrom(e.target.value)} />
          <SafeDateInput className="w-full" value={to} onChange={(e) => setTo(e.target.value)} />
          <Input type="number" placeholder="من مبلغ" value={minAmt} onChange={(e) => setMinAmt(e.target.value)} />
          <Input type="number" placeholder="إلى مبلغ" value={maxAmt} onChange={(e) => setMaxAmt(e.target.value)} />
          <select className="h-10 border rounded-md px-3" value={statusF} onChange={(e) => setStatusF(e.target.value as typeof statusF)}>
            <option value="all">كل الحالات</option>
            <option value="active">فعال</option>
            <option value="cancelled">ملغى</option>
          </select>
          <Button type="button" variant="outline" onClick={load}>
            تطبيق من الخادم
          </Button>
          <Button type="button" variant="ghost" onClick={resetFilters}>
            مسح الفلاتر
          </Button>
          {can('financial.revenues.restore') && (
            <label className="flex gap-2 items-center text-sm">
              <input type="checkbox" checked={deleted} onChange={(e) => setDeleted(e.target.checked)} />
              تحميل الملغى من الخادم
            </label>
          )}
        </CardContent>
      </Card>
      <div className="grid sm:grid-cols-3 gap-2">
        <Metric label="إجمالي المقبوض (النتائج)" value={filtered.filter((x) => !x.deleted).reduce((a, x) => a + x.amount, 0)} />
        <Metric label="المخصص" value={filtered.reduce((a, x) => a + x.allocated, 0)} />
        <Metric label="غير المخصص" value={filtered.filter((x) => !x.deleted).reduce((a, x) => a + x.remaining, 0)} />
      </div>
      <p className="text-sm text-slate-500">النتائج: {formatLatn(filtered.length, { maximumFractionDigits: 0 })} · محدد: {formatLatn(selected.length, { maximumFractionDigits: 0 })}</p>
      <CompactTable
        headers={[
          <ColSort key="seq" label="تسلسل" active={sortKey === 'seq'} dir={sortDir} onClick={() => toggleSort('received_at')} />,
          <span key="all" className="inline-flex items-center gap-2">
            <Checkbox checked={allFilteredSelected} onCheckedChange={(v) => toggleSelectAll(!!v)} aria-label="تحديد الكل" />
            تحديد الكل
          </span>,
          <ColSort key="num" label="رقم الوصل" active={sortKey === 'receipt_number'} dir={sortDir} onClick={() => toggleSort('receipt_number')} />,
          <ColSort key="co" label="الشركة" active={sortKey === 'company'} dir={sortDir} onClick={() => toggleSort('company')} />,
          <ColSort key="dt" label="التاريخ" active={sortKey === 'received_at'} dir={sortDir} onClick={() => toggleSort('received_at')} />,
          <ColSort key="amt" label="المبلغ" active={sortKey === 'amount'} dir={sortDir} onClick={() => toggleSort('amount')} />,
          <ColSort key="meth" label="طريقة القبض" active={sortKey === 'method'} dir={sortDir} onClick={() => toggleSort('method')} />,
          <ColSort key="cat" label="التصنيف" active={sortKey === 'category'} dir={sortDir} onClick={() => toggleSort('category')} />,
          <ColSort key="desc" label="البيان" active={sortKey === 'description'} dir={sortDir} onClick={() => toggleSort('description')} />,
          <ColSort key="st" label="الحالة" active={sortKey === 'status'} dir={sortDir} onClick={() => toggleSort('status')} />,
          'الإجراءات',
        ]}
      >
        {filtered.map((x, idx) => (
          <tr key={x.id} className={`border-t ${x.deleted ? 'opacity-60' : ''}`}>
            <td className="p-3 font-mono">{idx + 1}</td>
            <td className="p-3 print:hidden">
              <Checkbox
                checked={selected.includes(x.id)}
                onCheckedChange={(v) => setSelected((ids) => (v ? [...ids, x.id] : ids.filter((id) => id !== x.id)))}
              />
            </td>
            <td className="p-3 font-mono font-bold">{x.receipt_number}</td>
            <td>{companyName(x.company_id)}</td>
            <td className="font-mono">{x.received_at}</td>
            <td>{money(x.amount)}</td>
            <td>{x.receipt_method}</td>
            <td>{x.category || '—'}</td>
            <td className="max-w-48 whitespace-normal text-sm">{x.description || '—'}</td>
            <td>
              <StatusBadge value={x.deleted || x.status === 'cancelled' ? 'cancelled' : 'active'} />
            </td>
            <td className="print:hidden">
              <div className="flex flex-wrap gap-1">
                <ActionButton label="عرض الوصل" icon={Eye} onClick={() => viewVoucher(x)} />
                <ActionButton label="PDF" icon={FileDown} onClick={() => void pdfVoucher(x)} />
                <ActionButton label="طباعة" icon={Printer} onClick={() => printVoucher(x)} />
                {x.attachment_key && (
                  <Button size="icon" variant="ghost" onClick={() => financialErpApi.openDocument(x.attachment_key!)}>
                    <Eye className="w-4 h-4" />
                  </Button>
                )}
                {!x.deleted && x.remaining > 0 && can('financial.revenues.edit') && (
                  <ActionButton label="تخصيص" icon={Wallet} onClick={() => openAllocation(x)} />
                )}
                {!x.deleted && can('financial.revenues.edit') && (
                  <Button size="icon" variant="ghost" onClick={() => openEdit(x)}>
                    <Edit3 className="w-4 h-4" />
                  </Button>
                )}
                {!x.deleted && can('financial.revenues.delete') && (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={async () => {
                      if (!confirm(`إلغاء الوصل ${x.receipt_number}؟ سيبقى رقمه محجوزًا للتدقيق.`)) return;
                      await financialErpApi.deleteRevenue(x.id);
                      await load();
                      success(`تم إلغاء ${x.receipt_number}`);
                    }}
                  >
                    إلغاء
                  </Button>
                )}
                {x.deleted && can('financial.revenues.restore') && (
                  <ActionButton
                    label="إعادة تفعيل"
                    icon={RotateCcw}
                    onClick={async () => {
                      await financialErpApi.restoreRevenue(x.id);
                      await load();
                    }}
                  />
                )}
              </div>
            </td>
          </tr>
        ))}
        {!filtered.length && (
          <tr>
            <td colSpan={11}>
              <Empty title="لا نتائج" description="عدّل البحث أو الفلاتر." />
            </td>
          </tr>
        )}
      </CompactTable>

      <FormDialog open={open} onOpenChange={setOpen} title={edit ? `تعديل وصل ${edit.receipt_number}` : 'وصل قبض جديد'} className="max-w-3xl">
        <div className="grid md:grid-cols-2 gap-3">
          <Field label="رقم الوصل">
            <Input className="font-mono font-bold" value={edit?.receipt_number || voucher?.preview_rec || 'REC-…'} disabled />
          </Field>
          <Field label="الشركة">
            <select className="h-10 border rounded-md px-3 w-full" value={form.company_id} onChange={(e) => setForm({ ...form, company_id: e.target.value })}>
              <option value="">اختر</option>
              {companies.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="التاريخ">
            <SafeDateInput value={form.received_at} onChange={(e) => setForm({ ...form, received_at: e.target.value })} />
          </Field>
          <Field label="المبلغ">
            <Input type="number" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} />
          </Field>
          <Field label="طريقة القبض">
            <Input value={form.receipt_method} onChange={(e) => setForm({ ...form, receipt_method: e.target.value })} />
          </Field>
          <Field label="التصنيف">
            <Input value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} />
          </Field>
          <Field label="البيان / الوصف" className="md:col-span-2">
            <Input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          </Field>
          <Field label="من فترة">
            <SafeDateInput value={form.period_start} onChange={(e) => setForm({ ...form, period_start: e.target.value })} />
          </Field>
          <Field label="إلى فترة">
            <SafeDateInput value={form.period_end} onChange={(e) => setForm({ ...form, period_end: e.target.value })} />
          </Field>
          <Field label="المرفق">
            <FileButton
              label={form.attachment_key ? 'تم رفع المرفق' : 'رفع مرفق'}
              onFile={async (file) => {
                const u = await financialErpApi.upload('receipts', file);
                setForm({ ...form, attachment_key: u.object_key });
              }}
            />
          </Field>
          <Field label="ملاحظات">
            <Textarea value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
          </Field>
        </div>
        <div className="flex flex-wrap gap-2 mt-2">
          <Button type="button" variant="outline" onClick={() => setPreviewForm(true)}>
            <ReceiptText className="w-4 h-4 ml-2" />
            معاينة الوصل
          </Button>
          <Button type="button" onClick={() => void save()}>
            <Save className="w-4 h-4 ml-2" />
            حفظ
          </Button>
        </div>
      </FormDialog>

      <FormDialog open={previewForm} onOpenChange={setPreviewForm} title="معاينة قبل الحفظ (لا تستهلك رقمًا)" className="max-w-3xl">
        {(() => {
          const d = draftPreview();
          return (
            <div className="space-y-3">
              <iframe title="معاينة وصل قبض" className="w-full h-[65vh] border rounded-xl bg-white" srcDoc={receiptHtml(d, 'view')} />
              <p className="text-sm text-amber-700">المعاينة لا تحجز الرقم. الحفظ فقط يستهلك {voucher?.preview_rec}.</p>
              <Button type="button" onClick={() => void save()}>
                تأكيد الحفظ
              </Button>
            </div>
          );
        })()}
      </FormDialog>

      <FormDialog open={allocationOpen} onOpenChange={setAllocationOpen} title={`تخصيص الوصل ${receipt?.receipt_number || ''}`}>
        <p>
          الرصيد المتاح: <b>{money(receipt?.remaining)}</b>
        </p>
        <div className="grid md:grid-cols-2 gap-3">
          <Field label="نوع الهدف">
            <select
              className="h-10 border rounded-md px-3 w-full"
              value={allocation.target_type}
              onChange={(e) => setAllocation({ ...allocation, target_type: e.target.value, target_id: '' })}
            >
              <option value="statement">كشف شهري معتمد</option>
              <option value="settlement">دفعة تسوية</option>
            </select>
          </Field>
          <Field label="الهدف">
            <select className="h-10 border rounded-md px-3 w-full" value={allocation.target_id} onChange={(e) => setAllocation({ ...allocation, target_id: e.target.value })}>
              <option value="">اختر</option>
              {(allocation.target_type === 'statement' ? targets.statements : targets.settlements).map((x: any) => (
                <option key={x.id} value={x.id}>
                  {x.label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="مبلغ التخصيص">
            <Input type="number" max={receipt?.remaining} value={allocation.amount} onChange={(e) => setAllocation({ ...allocation, amount: e.target.value })} />
          </Field>
        </div>
        <Button type="button" onClick={allocate} disabled={!allocation.target_id}>
          حفظ التخصيص الجزئي
        </Button>
      </FormDialog>

      <FormDialog open={!!viewRow} onOpenChange={(v) => !v && setViewRow(undefined)} title={`عرض وصل ${viewRow?.receipt_number || ''}`} className="max-w-5xl">
        {viewRow && (
          <div className="space-y-3">
            <iframe title="وصل قبض" className="w-full h-[75vh] border rounded-xl bg-white" srcDoc={receiptHtml(viewRow, 'view')} />
            <div className="flex flex-wrap gap-2">
              <Button type="button" variant="outline" onClick={() => printVoucher(viewRow)}>
                <Printer className="w-4 h-4 ml-2" />
                طباعة
              </Button>
              <Button type="button" variant="outline" onClick={() => void pdfVoucher(viewRow)}>
                <FileDown className="w-4 h-4 ml-2" />
                PDF
              </Button>
            </div>
          </div>
        )}
      </FormDialog>
    </div>
  );
}

const blankExpense = {
  expense_date: today(),
  payee: '',
  person_name: '',
  company_name: '',
  payment_method: 'نقدًا',
  category: 'تشغيل',
  description: '',
  amount: '',
  notes: '',
  receipt_key: '',
};

export function ExpensesPage({ can, notify, success }: Props) {
  const { brand, resolveAssetUrl } = useBrand();
  const [year, setYear] = useState<number | ''>(now.getFullYear());
  const [month, setMonth] = useState<number | ''>(now.getMonth() + 1);
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [rows, setRows] = useState<Expense[]>([]);
  const [deleted, setDeleted] = useState(false);
  const [q, setQ] = useState('');
  const [category, setCategory] = useState('');
  const [descriptionF, setDescriptionF] = useState('');
  const [payee, setPayee] = useState('');
  const [person, setPerson] = useState('');
  const [companyNameF, setCompanyNameF] = useState('');
  const [payMethod, setPayMethod] = useState('');
  const [minAmt, setMinAmt] = useState('');
  const [maxAmt, setMaxAmt] = useState('');
  const [statusF, setStatusF] = useState<'all' | 'active' | 'cancelled'>('all');
  const [sortKey, setSortKey] = useState<
    'expense_date' | 'amount' | 'payment_number' | 'payee' | 'person' | 'company' | 'category' | 'description' | 'status'
  >('expense_date');
  const [sortDir, setSortDir] = useState<SortDir>('desc');
  const [open, setOpen] = useState(false);
  const [edit, setEdit] = useState<Expense>();
  const [form, setForm] = useState<any>(blankExpense);
  const [selected, setSelected] = useState<number[]>([]);
  const [zipBusy, setZipBusy] = useState(false);
  const [previewForm, setPreviewForm] = useState(false);
  const [viewRow, setViewRow] = useState<Expense>();
  const [voucher, setVoucher] = useState<{ next_pay: number; preview_pay: string } | null>(null);
  const [nextPayInput, setNextPayInput] = useState('');

  const loadVoucher = () =>
    financialErpApi
      .voucherNumbers()
      .then((x) => {
        setVoucher({ next_pay: x.next_pay, preview_pay: x.preview_pay });
        setNextPayInput(String(x.next_pay));
      })
      .catch(notify);
  const load = () =>
    financialErpApi
      .expenses({ accounting_year: year, accounting_month: month, date_from: from, date_to: to, include_deleted: deleted })
      .then((x) => setRows(x.items))
      .catch(notify);
  useEffect(() => {
    void load();
    void loadVoucher();
  }, [year, month, from, to, deleted]);

  const filtered = useMemo(() => {
    const term = q.trim().toLowerCase();
    let list = rows.filter((r) => {
      const cancelled = r.deleted || r.status === 'cancelled';
      if (statusF === 'active' && cancelled) return false;
      if (statusF === 'cancelled' && !cancelled) return false;
      if (category && !(r.category || '').includes(category)) return false;
      if (descriptionF && !(r.description || '').includes(descriptionF)) return false;
      if (payee && !(r.payee || '').includes(payee)) return false;
      if (person && !(r.person_name || '').includes(person)) return false;
      if (companyNameF && !(r.company_name || '').includes(companyNameF)) return false;
      if (payMethod && !(r.payment_method || '').includes(payMethod)) return false;
      if (minAmt && !(r.amount >= Number(minAmt))) return false;
      if (maxAmt && !(r.amount <= Number(maxAmt))) return false;
      if (!term) return true;
      const blob = [
        r.payment_number,
        r.expense_date,
        r.payee,
        r.person_name,
        r.company_name,
        r.payment_method,
        r.category,
        r.description,
        r.notes,
        r.created_by,
        String(r.amount),
        String(r.accounting_year),
        String(r.accounting_month),
      ]
        .join(' ')
        .toLowerCase();
      return blob.includes(term);
    });
    const dir = sortDir === 'asc' ? 1 : -1;
    list = [...list].sort((a, b) => {
      if (sortKey === 'amount') return (a.amount - b.amount) * dir;
      if (sortKey === 'payment_number') return String(a.payment_number || '').localeCompare(String(b.payment_number || ''), 'en') * dir;
      if (sortKey === 'payee') return String(a.payee || '').localeCompare(String(b.payee || ''), 'ar') * dir;
      if (sortKey === 'person') return String(a.person_name || '').localeCompare(String(b.person_name || ''), 'ar') * dir;
      if (sortKey === 'company') return String(a.company_name || '').localeCompare(String(b.company_name || ''), 'ar') * dir;
      if (sortKey === 'category') return String(a.category || '').localeCompare(String(b.category || ''), 'ar') * dir;
      if (sortKey === 'description') return String(a.description || '').localeCompare(String(b.description || ''), 'ar') * dir;
      if (sortKey === 'status') {
        const as = a.deleted || a.status === 'cancelled' ? 1 : 0;
        const bs = b.deleted || b.status === 'cancelled' ? 1 : 0;
        return (as - bs) * dir;
      }
      return String(a.expense_date).localeCompare(String(b.expense_date)) * dir;
    });
    return list;
  }, [rows, q, category, descriptionF, payee, person, companyNameF, payMethod, minAmt, maxAmt, statusF, sortKey, sortDir]);

  const toggleSort = (key: typeof sortKey) => {
    if (sortKey === key) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    else {
      setSortKey(key);
      setSortDir('asc');
    }
  };

  const resetFilters = () => {
    setQ('');
    setCategory('');
    setDescriptionF('');
    setPayee('');
    setPerson('');
    setCompanyNameF('');
    setPayMethod('');
    setMinAmt('');
    setMaxAmt('');
    setFrom('');
    setTo('');
    setYear(now.getFullYear());
    setMonth(now.getMonth() + 1);
    setStatusF('all');
    setDeleted(false);
    setSelected([]);
  };

  const allFilteredSelected = filtered.length > 0 && filtered.every((x) => selected.includes(x.id));
  const toggleSelectAll = (on: boolean) => {
    if (on) setSelected(filtered.map((x) => x.id));
    else setSelected([]);
  };

  const logo = () => resolveAssetUrl(brand.report_logo || brand.system_logo);
  const paymentHtml = (row: Expense, mode: 'view' | 'print' | 'pdf') =>
    paymentVoucherHtml({ brand, logoUrl: logo(), mode, row });

  const viewVoucher = (row: Expense) => setViewRow(row);
  const printVoucher = (row: Expense) => {
    try {
      openVoucherWindow(paymentHtml(row, 'print'));
    } catch (e) {
      notify(e);
    }
  };
  const pdfVoucher = async (row: Expense) => {
    try {
      await downloadVoucherPdf(paymentHtml(row, 'pdf'), `${row.payment_number || 'PAY'}.pdf`);
      success(`تم تنزيل PDF للوصل ${row.payment_number}`);
    } catch (e) {
      notify(e);
    }
  };

  const exportZip = async () => {
    if (!selected.length) {
      notify(new Error('حدّد وصولًا واحدًا على الأقل قبل تصدير ZIP'));
      return;
    }
    const picks = filtered.filter((x) => selected.includes(x.id));
    if (!picks.length) {
      notify(new Error('الوصولات المحددة غير ظاهرة ضمن النتائج الحالية'));
      return;
    }
    setZipBusy(true);
    try {
      await downloadVoucherPdfZip(
        picks.map((row) => ({
          html: paymentHtml(row, 'pdf'),
          filename: `${row.payment_number || `PAY-${row.id}`}.pdf`,
        })),
        `PAY-vouchers-${today()}.zip`,
      );
      success(`تم تنزيل ZIP يحتوي ${picks.length} ملف PDF`);
    } catch (e) {
      notify(e);
    } finally {
      setZipBusy(false);
    }
  };

  const save = async () => {
    if (!form.expense_date) {
      notify(new Error('تاريخ الصرف مطلوب'));
      return;
    }
    if (!form.payee?.trim()) {
      notify(new Error('حقل «دُفع إلى» مطلوب'));
      return;
    }
    if (form.category.trim().length < 2) {
      notify(new Error('تصنيف الصرف مطلوب'));
      return;
    }
    if (form.description.trim().length < 2) {
      notify(new Error('البيان/الغرض من الصرف مطلوب'));
      return;
    }
    if (!(Number(form.amount) > 0)) {
      notify(new Error('أدخل مبلغًا أكبر من صفر'));
      return;
    }
    try {
      const d = new Date(`${form.expense_date}T00:00:00`);
      const payload = {
        ...form,
        amount: Number(form.amount),
        accounting_year: year || d.getFullYear(),
        accounting_month: month || d.getMonth() + 1,
        payee: form.payee,
        person_name: form.person_name || null,
        company_name: form.company_name || null,
        payment_method: form.payment_method || null,
      };
      const savedRes = await financialErpApi.saveExpense(payload, edit?.id);
      const number = savedRes.payment_number || edit?.payment_number || voucher?.preview_pay || '';
      setOpen(false);
      setPreviewForm(false);
      await load();
      await loadVoucher();
      success(edit ? `تم تعديل وصل الصرف ${number}` : `تم حفظ وصل الصرف ${number}`);
      const row: Expense = {
        id: savedRes.id,
        payment_number: number,
        expense_date: form.expense_date,
        accounting_year: payload.accounting_year,
        accounting_month: payload.accounting_month,
        payee: form.payee,
        person_name: form.person_name,
        company_name: form.company_name,
        payment_method: form.payment_method,
        category: form.category,
        description: form.description,
        amount: Number(form.amount),
        notes: form.notes,
        receipt_key: form.receipt_key,
        created_by: '',
        deleted: false,
        status: 'active',
      };
      setViewRow(row);
    } catch (e) {
      notify(e);
    }
  };

  const openEdit = (x?: Expense) => {
    setEdit(x);
    setForm(
      x
        ? {
            ...blankExpense,
            ...x,
            amount: String(x.amount),
            payee: x.payee || '',
            person_name: x.person_name || '',
            company_name: x.company_name || '',
            payment_method: x.payment_method || 'نقدًا',
            notes: x.notes || '',
            receipt_key: x.receipt_key || '',
          }
        : blankExpense,
    );
    setPreviewForm(false);
    setOpen(true);
    void loadVoucher();
  };
  const draftPreview = (): Expense => ({
    id: edit?.id || 0,
    payment_number: edit?.payment_number || voucher?.preview_pay || 'PAY-…',
    expense_date: form.expense_date,
    accounting_year: now.getFullYear(),
    accounting_month: now.getMonth() + 1,
    payee: form.payee,
    person_name: form.person_name,
    company_name: form.company_name,
    payment_method: form.payment_method,
    category: form.category,
    description: form.description,
    amount: Number(form.amount) || 0,
    notes: form.notes,
    receipt_key: form.receipt_key,
    created_by: '',
    deleted: false,
    status: 'active',
  });
  const saveNextPay = async () => {
    const n = Number(nextPayInput);
    if (!(n > 0)) {
      notify(new Error('أدخل رقمًا صحيحًا لتالي وصل الصرف'));
      return;
    }
    try {
      const x = await financialErpApi.setVoucherNumbers({ next_pay: n });
      setVoucher({ next_pay: x.next_pay, preview_pay: x.preview_pay });
      setNextPayInput(String(x.next_pay));
      success(`تم تعيين الرقم التالي لوصل الصرف: ${x.preview_pay}`);
    } catch (e) {
      notify(e);
    }
  };

  const exportIds = selected.length ? selected : filtered.map((x) => x.id);

  return (
    <div className="space-y-4">
      <PageTitle
        title="وصولات الصرف"
        description="ترقيم تلقائي مستقل PAY-xxxx يُحجز فقط عند الحفظ. الإلغاء لا يعيد الرقم للمخزون."
        actions={
          <>
            {can('financial.expenses.create') && (
              <Button onClick={() => openEdit()}>
                <Plus className="w-4 h-4 ml-1" />
                وصل صرف
              </Button>
            )}
            <Button type="button" variant="outline" disabled={zipBusy} onClick={() => void exportZip()}>
              <FileDown className="w-4 h-4 ml-1" />
              {zipBusy ? 'جاري ZIP…' : 'تصدير الوصولات PDF'}
            </Button>
            {can('financial.reports.xlsx') && (
              <Button
                variant="outline"
                onClick={() =>
                  financialErpApi
                    .exportExpenses({
                      accounting_year: year,
                      accounting_month: month,
                      date_from: from,
                      date_to: to,
                      selected_ids: exportIds.length ? exportIds : undefined,
                    })
                    .catch(notify)
                }
              >
                <FileSpreadsheet className="w-4 h-4 ml-1" />
                Excel
              </Button>
            )}
          </>
        }
      />
      <Card>
        <CardContent className="p-3 flex flex-wrap gap-3 items-end">
          <Field label="رقم المصروف التالي">
            <div className="flex gap-2">
              <Input className="w-36 font-mono" value={nextPayInput} onChange={(e) => setNextPayInput(e.target.value)} placeholder="5" />
              <Button type="button" variant="outline" onClick={() => void saveNextPay()}>
                حفظ
              </Button>
            </div>
          </Field>
          <div className="text-sm text-slate-600 pb-2">
            المعاينة: <b className="font-mono">{voucher?.preview_pay || '—'}</b>
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="p-3 grid sm:grid-cols-2 lg:grid-cols-4 gap-2">
          <Input placeholder="بحث (PAY، وصف، مستفيد، منشئ...)" value={q} onChange={(e) => setQ(e.target.value)} />
          <Field label="السنة">
            <Input className="w-full" type="number" value={year} onChange={(e) => setYear(e.target.value ? Number(e.target.value) : '')} />
          </Field>
          <Field label="الشهر">
            <Input className="w-full" type="number" value={month} onChange={(e) => setMonth(e.target.value ? Number(e.target.value) : '')} />
          </Field>
          <Input placeholder="التصنيف" value={category} onChange={(e) => setCategory(e.target.value)} />
          <Input placeholder="البيان / الوصف" value={descriptionF} onChange={(e) => setDescriptionF(e.target.value)} />
          <Input placeholder="دُفع إلى" value={payee} onChange={(e) => setPayee(e.target.value)} />
          <Input placeholder="اسم الشخص" value={person} onChange={(e) => setPerson(e.target.value)} />
          <Input placeholder="اسم الشركة" value={companyNameF} onChange={(e) => setCompanyNameF(e.target.value)} />
          <Input placeholder="طريقة الدفع" value={payMethod} onChange={(e) => setPayMethod(e.target.value)} />
          <SafeDateInput value={from} onChange={(e) => { setFrom(e.target.value); setYear(''); setMonth(''); }} />
          <SafeDateInput value={to} onChange={(e) => { setTo(e.target.value); setYear(''); setMonth(''); }} />
          <Input type="number" placeholder="من مبلغ" value={minAmt} onChange={(e) => setMinAmt(e.target.value)} />
          <Input type="number" placeholder="إلى مبلغ" value={maxAmt} onChange={(e) => setMaxAmt(e.target.value)} />
          <select className="h-10 border rounded-md px-3" value={statusF} onChange={(e) => setStatusF(e.target.value as typeof statusF)}>
            <option value="all">كل الحالات</option>
            <option value="active">فعال</option>
            <option value="cancelled">ملغى</option>
          </select>
          <Button type="button" variant="ghost" onClick={resetFilters}>
            مسح الفلاتر
          </Button>
          {can('financial.expenses.restore') && (
            <label className="flex gap-2 items-center text-sm">
              <input type="checkbox" checked={deleted} onChange={(e) => setDeleted(e.target.checked)} />
              تحميل الملغى من الخادم
            </label>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardContent className="p-4">
          <small>إجمالي صرف النتائج الحالية</small>
          <b className="block text-2xl text-red-700">{money(filtered.filter((x) => !x.deleted).reduce((a, x) => a + x.amount, 0))}</b>
        </CardContent>
      </Card>
      <p className="text-sm text-slate-500">النتائج: {formatLatn(filtered.length, { maximumFractionDigits: 0 })} · محدد: {formatLatn(selected.length, { maximumFractionDigits: 0 })}</p>
      <CompactTable
        headers={[
          <ColSort key="seq" label="تسلسل" active={false} dir={sortDir} onClick={() => toggleSort('expense_date')} />,
          <span key="all" className="inline-flex items-center gap-2">
            <Checkbox checked={allFilteredSelected} onCheckedChange={(v) => toggleSelectAll(!!v)} aria-label="تحديد الكل" />
            تحديد الكل
          </span>,
          <ColSort key="num" label="رقم الوصل" active={sortKey === 'payment_number'} dir={sortDir} onClick={() => toggleSort('payment_number')} />,
          <ColSort key="dt" label="التاريخ" active={sortKey === 'expense_date'} dir={sortDir} onClick={() => toggleSort('expense_date')} />,
          <ColSort key="payee" label="دُفع إلى" active={sortKey === 'payee'} dir={sortDir} onClick={() => toggleSort('payee')} />,
          <ColSort key="person" label="اسم الشخص" active={sortKey === 'person'} dir={sortDir} onClick={() => toggleSort('person')} />,
          <ColSort key="co" label="اسم الشركة" active={sortKey === 'company'} dir={sortDir} onClick={() => toggleSort('company')} />,
          <ColSort key="cat" label="التصنيف" active={sortKey === 'category'} dir={sortDir} onClick={() => toggleSort('category')} />,
          <ColSort key="desc" label="البيان" active={sortKey === 'description'} dir={sortDir} onClick={() => toggleSort('description')} />,
          <ColSort key="amt" label="المبلغ" active={sortKey === 'amount'} dir={sortDir} onClick={() => toggleSort('amount')} />,
          <ColSort key="st" label="الحالة" active={sortKey === 'status'} dir={sortDir} onClick={() => toggleSort('status')} />,
          'الإجراءات',
        ]}
      >
        {filtered.map((x, idx) => (
          <tr key={x.id} className={`border-t ${x.deleted ? 'opacity-60' : ''}`}>
            <td className="p-3 font-mono">{idx + 1}</td>
            <td className="p-3 print:hidden">
              <Checkbox
                checked={selected.includes(x.id)}
                onCheckedChange={(v) => setSelected((ids) => (v ? [...ids, x.id] : ids.filter((id) => id !== x.id)))}
              />
            </td>
            <td className="p-3 font-mono font-bold">{x.payment_number || '-'}</td>
            <td className="font-mono">{x.expense_date}</td>
            <td>{x.payee || '—'}</td>
            <td>{x.person_name || '—'}</td>
            <td>{x.company_name || '—'}</td>
            <td>{x.category}</td>
            <td className="max-w-48 whitespace-normal text-sm">{x.description}</td>
            <td>{money(x.amount)}</td>
            <td>
              <StatusBadge value={x.deleted || x.status === 'cancelled' ? 'cancelled' : 'active'} />
            </td>
            <td className="print:hidden">
              <div className="flex flex-wrap gap-1">
                <ActionButton label="عرض الوصل" icon={Eye} onClick={() => viewVoucher(x)} />
                <ActionButton label="PDF" icon={FileDown} onClick={() => void pdfVoucher(x)} />
                <ActionButton label="طباعة" icon={Printer} onClick={() => printVoucher(x)} />
                {x.receipt_key && (
                  <Button size="icon" variant="ghost" onClick={() => financialErpApi.openDocument(x.receipt_key!)}>
                    <Eye className="w-4 h-4" />
                  </Button>
                )}
                {!x.deleted && can('financial.expenses.edit') && (
                  <Button size="icon" variant="ghost" onClick={() => openEdit(x)}>
                    <Edit3 className="w-4 h-4" />
                  </Button>
                )}
                {!x.deleted && can('financial.expenses.delete') && (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={async () => {
                      if (!confirm(`إلغاء الوصل ${x.payment_number}؟ سيبقى رقمه محجوزًا.`)) return;
                      await financialErpApi.deleteExpense(x.id);
                      await load();
                      success(`تم إلغاء ${x.payment_number}`);
                    }}
                  >
                    إلغاء
                  </Button>
                )}
                {x.deleted && can('financial.expenses.restore') && (
                  <ActionButton
                    label="إعادة تفعيل"
                    icon={RotateCcw}
                    onClick={async () => {
                      await financialErpApi.restoreExpense(x.id);
                      await load();
                    }}
                  />
                )}
              </div>
            </td>
          </tr>
        ))}
        {!filtered.length && (
          <tr>
            <td colSpan={12}>
              <Empty title="لا نتائج" description="عدّل البحث أو الفلاتر." />
            </td>
          </tr>
        )}
      </CompactTable>

      <FormDialog open={open} onOpenChange={setOpen} title={edit ? `تعديل وصل ${edit.payment_number}` : 'وصل صرف جديد'} className="max-w-3xl">
        <div className="grid md:grid-cols-2 gap-3">
          <Field label="رقم الوصل">
            <Input className="font-mono font-bold" value={edit?.payment_number || voucher?.preview_pay || 'PAY-…'} disabled />
          </Field>
          <Field label="دُفع إلى">
            <Input value={form.payee} onChange={(e) => setForm({ ...form, payee: e.target.value })} />
          </Field>
          <Field label="اسم الشخص">
            <Input value={form.person_name} onChange={(e) => setForm({ ...form, person_name: e.target.value })} />
          </Field>
          <Field label="اسم الشركة">
            <Input value={form.company_name} onChange={(e) => setForm({ ...form, company_name: e.target.value })} />
          </Field>
          <Field label="التاريخ">
            <SafeDateInput value={form.expense_date} onChange={(e) => setForm({ ...form, expense_date: e.target.value })} />
          </Field>
          <Field label="المبلغ">
            <Input type="number" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} />
          </Field>
          <Field label="طريقة الدفع">
            <Input value={form.payment_method} onChange={(e) => setForm({ ...form, payment_method: e.target.value })} />
          </Field>
          <Field label="التصنيف">
            <Input value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} />
          </Field>
          <Field label="البيان/الغرض من الصرف" className="md:col-span-2">
            <Input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          </Field>
          <Field label="الملاحظات">
            <Textarea value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
          </Field>
          <Field label="المرفقات">
            <FileButton
              label={form.receipt_key ? 'تم رفع المرفق' : 'رفع مرفق'}
              onFile={async (file) => {
                const u = await financialErpApi.upload('receipts', file);
                setForm({ ...form, receipt_key: u.object_key });
              }}
            />
          </Field>
        </div>
        <div className="flex flex-wrap gap-2 mt-2">
          <Button type="button" variant="outline" onClick={() => setPreviewForm(true)}>
            <ReceiptText className="w-4 h-4 ml-2" />
            معاينة الوصل
          </Button>
          <Button type="button" onClick={() => void save()}>
            <Save className="w-4 h-4 ml-2" />
            حفظ
          </Button>
        </div>
      </FormDialog>

      <FormDialog open={previewForm} onOpenChange={setPreviewForm} title="معاينة قبل الحفظ (لا تستهلك رقمًا)" className="max-w-3xl">
        {(() => {
          const d = draftPreview();
          return (
            <div className="space-y-3">
              <iframe title="معاينة وصل صرف" className="w-full h-[65vh] border rounded-xl bg-white" srcDoc={paymentHtml(d, 'view')} />
              <Button type="button" onClick={() => void save()}>
                تأكيد الحفظ
              </Button>
            </div>
          );
        })()}
      </FormDialog>

      <FormDialog open={!!viewRow} onOpenChange={(v) => !v && setViewRow(undefined)} title={`عرض وصل ${viewRow?.payment_number || ''}`} className="max-w-5xl">
        {viewRow && (
          <div className="space-y-3">
            <iframe title="وصل صرف" className="w-full h-[75vh] border rounded-xl bg-white" srcDoc={paymentHtml(viewRow, 'view')} />
            <div className="flex flex-wrap gap-2">
              <Button type="button" variant="outline" onClick={() => printVoucher(viewRow)}>
                <Printer className="w-4 h-4 ml-2" />
                طباعة
              </Button>
              <Button type="button" variant="outline" onClick={() => void pdfVoucher(viewRow)}>
                <FileDown className="w-4 h-4 ml-2" />
                PDF
              </Button>
            </div>
          </div>
        )}
      </FormDialog>
    </div>
  );
}
