import { useCallback, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { useToast } from '@/hooks/use-toast';
import { Toaster } from '@/components/ui/toaster';
import { client, downloadAuthorizedFile } from '@/lib/localApi';
import { useBrand } from '@/lib/brand';
import { ArrowRight, FileSpreadsheet, Printer, Search } from 'lucide-react';

type Row = {
  id: number;
  membership_number?: string;
  business_name: string;
  merchant_name: string;
  phone: string;
  governorate: string;
  business_type?: string;
  membership_status?: string;
  status: string;
  created_at?: string;
  approved_at?: string;
};

const statusLabel: Record<string, string> = {
  approved: 'مقبول',
  rejected: 'مرفوض',
  pending: 'قيد المراجعة',
};
const msLabel: Record<string, string> = {
  active: 'فعال',
  suspended: 'معلق',
  expired: 'منتهي',
};

function parseDate(v?: string | null): Date | null {
  if (!v) return null;
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? null : d;
}

function inRange(iso: string | undefined, from: string, to: string): boolean {
  const d = parseDate(iso);
  if (!d) return false;
  const start = from ? new Date(`${from}T00:00:00`) : null;
  const end = to ? new Date(`${to}T23:59:59`) : null;
  if (start && d < start) return false;
  if (end && d > end) return false;
  return true;
}

export default function MembershipReport() {
  const navigate = useNavigate();
  const { toast } = useToast();
  const { brand, resolveAssetUrl } = useBrand();
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [loading, setLoading] = useState(false);
  const [rows, setRows] = useState<Row[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [search, setSearch] = useState('');
  const [sortKey, setSortKey] = useState<keyof Row>('created_at');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');

  const load = useCallback(async () => {
    if (!dateFrom || !dateTo) {
      toast({ title: 'تنبيه', description: 'حدد تاريخ البداية والنهاية', variant: 'destructive' });
      return;
    }
    if (new Date(dateFrom) > new Date(dateTo)) {
      toast({ title: 'تنبيه', description: 'تاريخ البداية يجب أن يكون قبل النهاية', variant: 'destructive' });
      return;
    }
    setLoading(true);
    try {
      const res = await client.apiCall.invoke({
        url: '/api/v1/admin/registrations/export-all?sort=-created_at',
        method: 'GET',
        data: {},
      });
      const items: Row[] = res.data?.items || [];
      const filtered = items.filter(
        (it) => inRange(it.created_at, dateFrom, dateTo) || inRange(it.approved_at, dateFrom, dateTo)
      );
      setRows(filtered);
      setLoaded(true);
      toast({ title: 'تم التحميل', description: `عدد الأعضاء: ${filtered.length}` });
    } catch (e: any) {
      toast({ title: 'خطأ', description: e?.message || 'فشل تحميل البيانات', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  }, [dateFrom, dateTo, toast]);

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    let list = rows;
    if (q) {
      list = list.filter((r) =>
        [
          r.membership_number,
          r.business_name,
          r.merchant_name,
          r.phone,
          r.governorate,
          r.business_type,
          r.status,
          r.membership_status,
        ]
          .join(' ')
          .toLowerCase()
          .includes(q)
      );
    }
    const dir = sortDir === 'asc' ? 1 : -1;
    return [...list].sort((a, b) => {
      const av = String(a[sortKey] ?? '');
      const bv = String(b[sortKey] ?? '');
      return av.localeCompare(bv, 'ar') * dir;
    });
  }, [rows, search, sortKey, sortDir]);

  const toggleSort = (key: keyof Row) => {
    if (sortKey === key) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    else {
      setSortKey(key);
      setSortDir('asc');
    }
  };

  const exportExcel = async () => {
    if (!visible.length) {
      toast({ title: 'تنبيه', description: 'لا توجد سجلات للتصدير', variant: 'destructive' });
      return;
    }
    try {
      toast({ title: 'جاري التصدير...', description: 'تقرير Excel بهوية MFEC' });
      const ids = visible.map((r) => r.id).join(',');
      await downloadAuthorizedFile(
        `/api/v1/admin/registrations/export-xlsx?ids=${encodeURIComponent(ids)}&sort=-created_at`,
        `membership_report_${dateFrom}_${dateTo}.xlsx`
      );
      toast({ title: 'تم التصدير', description: 'تم تنزيل ملف Excel بنفس تنسيق تقرير الأعضاء' });
    } catch (e: any) {
      toast({ title: 'خطأ', description: e?.message || 'فشل التصدير', variant: 'destructive' });
    }
  };

  const printReport = () => {
    if (!visible.length) {
      toast({ title: 'تنبيه', description: 'لا توجد سجلات للطباعة', variant: 'destructive' });
      return;
    }
    const ids = visible.map((r) => r.id).join(',');
    window.open(`/admin/print?ids=${encodeURIComponent(ids)}&sort=-created_at`, '_blank', 'noopener,noreferrer');
  };

  return (
    <div className="min-h-screen bg-[#F9FAFB]" dir="rtl">
      <Toaster />
      <header className="sticky top-0 z-10 text-white no-print" style={{ background: brand.header_color || brand.primary_color }}>
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between gap-2 flex-wrap">
          <div className="flex items-center gap-3">
            <img src={resolveAssetUrl(brand.system_logo)} alt="" className="w-10 h-10 object-contain bg-white/10 rounded" />
            <div>
              <h1 className="font-bold">كشف العضوية</h1>
              <p className="text-xs opacity-80">تقرير الأعضاء حسب الفترة</p>
            </div>
          </div>
          <Button variant="secondary" size="sm" onClick={() => navigate('/admin')} className="gap-1">
            <ArrowRight className="w-4 h-4" /> رجوع
          </Button>
        </div>
        <div className="h-1" style={{ background: brand.secondary_color }} />
      </header>

      <main className="max-w-7xl mx-auto p-4 space-y-4">
        <Card className="no-print">
          <CardHeader><CardTitle className="text-right text-base">اختيار الفترة</CardTitle></CardHeader>
          <CardContent className="grid sm:grid-cols-4 gap-3 items-end text-right">
            <div className="space-y-1">
              <Label>من تاريخ</Label>
              <Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label>إلى تاريخ</Label>
              <Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
            </div>
            <Button onClick={load} disabled={loading} className="text-white" style={{ background: brand.button_color }}>
              {loading ? 'جاري التحميل...' : 'عرض الأعضاء'}
            </Button>
            {loaded && (
              <div className="flex gap-2">
                <Button variant="outline" size="sm" className="gap-1" onClick={printReport}>
                  <Printer className="w-4 h-4" /> طباعة
                </Button>
                <Button variant="outline" size="sm" className="gap-1" onClick={exportExcel}>
                  <FileSpreadsheet className="w-4 h-4" /> Excel
                </Button>
              </div>
            )}
          </CardContent>
        </Card>

        {loaded && (
          <>
            <div className="report-brand text-center text-white rounded-t-lg p-4" style={{ background: brand.primary_color }}>
              <img src={resolveAssetUrl(brand.report_logo || brand.system_logo)} alt="" className="mx-auto object-contain mb-2" style={{ width: Number(brand.report_logo_size) || 72, height: Number(brand.report_logo_size) || 72 }} />
              <div className="font-bold text-lg">{brand.system_name}</div>
              <div style={{ color: brand.secondary_color }} className="font-bold">{brand.org_abbr}</div>
              <div className="mt-1 font-semibold">كشف العضوية</div>
              <div className="text-sm mt-2 opacity-90">من {dateFrom} إلى {dateTo} · إجمالي الأعضاء: <strong>{visible.length}</strong></div>
            </div>
            <div className="h-1" style={{ background: brand.secondary_color }} />

            <Card>
              <CardContent className="p-3 space-y-3">
                <div className="relative no-print max-w-md mr-auto">
                  <Search className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                  <Input className="pr-10 text-right" placeholder="بحث..." value={search} onChange={(e) => setSearch(e.target.value)} />
                </div>
                <div className="overflow-x-auto">
                  <Table className="text-sm">
                    <TableHeader>
                      <TableRow style={{ background: brand.table_header_color || brand.primary_color }}>
                        {[
                          ['#', null],
                          ['رقم العضوية', 'membership_number'],
                          ['اسم النشاط', 'business_name'],
                          ['اسم التاجر', 'merchant_name'],
                          ['الهاتف', 'phone'],
                          ['المحافظة', 'governorate'],
                          ['نوع النشاط', 'business_type'],
                          ['حالة العضوية', 'membership_status'],
                          ['حالة الطلب', 'status'],
                          ['تاريخ التسجيل', 'created_at'],
                          ['تاريخ القبول', 'approved_at'],
                        ].map(([label, key]) => (
                          <TableHead
                            key={label as string}
                            className="text-white text-right cursor-pointer whitespace-nowrap"
                            onClick={() => key && toggleSort(key as keyof Row)}
                          >
                            {label as string}
                          </TableHead>
                        ))}
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {visible.map((r, i) => (
                        <TableRow key={r.id} style={{ background: i % 2 ? brand.table_alt_row_color : undefined }}>
                          <TableCell>{i + 1}</TableCell>
                          <TableCell className="font-mono">{r.membership_number || '-'}</TableCell>
                          <TableCell>{r.business_name}</TableCell>
                          <TableCell>{r.merchant_name}</TableCell>
                          <TableCell dir="ltr">{r.phone}</TableCell>
                          <TableCell>{r.governorate}</TableCell>
                          <TableCell>{r.business_type || '-'}</TableCell>
                          <TableCell>{msLabel[r.membership_status || ''] || r.membership_status || '-'}</TableCell>
                          <TableCell>{statusLabel[r.status] || r.status}</TableCell>
                          <TableCell>{r.created_at ? String(r.created_at).slice(0, 10) : '-'}</TableCell>
                          <TableCell>{r.approved_at ? String(r.approved_at).slice(0, 10) : '-'}</TableCell>
                        </TableRow>
                      ))}
                      {visible.length === 0 && (
                        <TableRow>
                          <TableCell colSpan={11} className="text-center text-gray-500 py-8">لا توجد نتائج ضمن الفترة</TableCell>
                        </TableRow>
                      )}
                    </TableBody>
                  </Table>
                </div>
              </CardContent>
            </Card>

            <footer className="text-center text-sm text-gray-600 py-4 border-t">
              <div>{brand.footer_text}</div>
              <div>{brand.company_name}</div>
              <div>{brand.website} | {brand.email} | {brand.phone}</div>
              <div>{brand.copyright}</div>
            </footer>
          </>
        )}
      </main>

      <style>{`
        @media print {
          .no-print { display: none !important; }
          body { background: #fff; }
        }
      `}</style>
    </div>
  );
}
