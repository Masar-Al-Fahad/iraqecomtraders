import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { client, localAuth } from '@/lib/localApi';
import { getAPIBaseURL } from '@/lib/config';

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

type DynField = { id: string; label: string };

type PrintItem = {
  membership_number?: string | null;
  business_name: string;
  merchant_name: string;
  phone: string;
  governorate: string;
  area: string;
  business_type?: string | null;
  status: string;
  membership_status?: string | null;
  created_at?: string | null;
  approved_at?: string | null;
  last_modified_by?: string | null;
  updated_at?: string | null;
  notes?: string | null;
  extra_fields?: Record<string, { label?: string; value?: any }> | null;
};

function resolveLogo(path?: string) {
  if (!path) return '/brand/mfec-logo.png';
  if (path.startsWith('http') || path.startsWith('data:')) return path;
  if (path.startsWith('/api/')) {
    const base = (getAPIBaseURL() || '').replace(/\/$/, '');
    return `${base}${path}`;
  }
  return path;
}

function dynValue(item: PrintItem, field: DynField): string {
  const entry = item.extra_fields?.[field.id];
  if (entry && entry.value !== undefined && entry.value !== null && entry.value !== '') {
    return Array.isArray(entry.value) ? entry.value.join(', ') : String(entry.value);
  }
  // fallback: notes "Label: value"
  const notes = String(item.notes || '');
  for (const line of notes.split(/\r?\n/)) {
    const idx = line.indexOf(':');
    if (idx <= 0) continue;
    if (line.slice(0, idx).trim() === field.label) return line.slice(idx + 1).trim();
  }
  return '-';
}

export default function PrintMembers() {
  const [params] = useSearchParams();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [data, setData] = useState<any>(null);

  const queryString = useMemo(() => {
    const q = new URLSearchParams(params);
    return q.toString();
  }, [params]);

  useEffect(() => {
    const run = async () => {
      if (!localAuth.getToken()) {
        setError('يجب تسجيل الدخول أولاً');
        setLoading(false);
        return;
      }
      try {
        const res = await client.apiCall.invoke({
          url: `/api/v1/admin/registrations/print-data?${queryString}`,
          method: 'GET',
          data: {},
        });
        setData(res.data);
        setLoading(false);
        setTimeout(() => window.print(), 700);
      } catch (e: any) {
        setError(e?.message || 'فشل تحميل بيانات الطباعة');
        setLoading(false);
      }
    };
    run();
  }, [queryString]);

  if (loading) {
    return <div className="print-root p-8 text-center" dir="rtl">جاري تجهيز معاينة الطباعة...</div>;
  }
  if (error) {
    return <div className="print-root p-8 text-center text-red-600" dir="rtl">{error}</div>;
  }

  const items: PrintItem[] = data?.items || [];
  const dynFields: DynField[] = (data?.dynamic_fields || []).filter((f: DynField) => f?.id && f?.label);
  const colCount = 14 + dynFields.length;
  const navy = data?.primary_color || data?.brand?.primary_color || '#1F2937';
  const gold = data?.secondary_color || data?.brand?.secondary_color || '#C89B3C';
  const brand = data?.brand || {};
  const wmEnabled = String(brand.watermark_enabled ?? 'true').toLowerCase() !== 'false';
  const wmPct = Math.min(10, Math.max(5, Number(brand.watermark_opacity) || 7));
  const printedAt = data?.printed_at ? new Date(data.printed_at) : new Date();
  const printDate = printedAt.toLocaleDateString('ar-IQ');
  const printTime = printedAt.toLocaleTimeString('ar-IQ');
  const logo = resolveLogo(data?.logo || brand.report_logo || brand.system_logo);

  return (
    <div className="print-root" dir="rtl">
      <style>{`
        :root {
          --navy: ${navy};
          --gold: ${gold};
          --alt: #F3F4F6;
          --wm-opacity: ${wmEnabled ? wmPct / 100 : 0};
        }
        html, body { background: #fff; margin: 0; }
        .print-root {
          font-family: Tahoma, Arial, "Segoe UI", sans-serif;
          color: #111;
          padding: 10px 12px 20px;
          position: relative;
        }
        .no-print { margin-bottom: 12px; }
        .print-wm {
          position: fixed;
          inset: 0;
          display: flex;
          align-items: center;
          justify-content: center;
          pointer-events: none;
          z-index: 0;
        }
        .print-wm img {
          max-width: 52%;
          max-height: 52%;
          object-fit: contain;
          opacity: var(--wm-opacity);
        }
        .brand-banner {
          position: relative;
          z-index: 1;
          background: var(--navy);
          color: #fff;
          text-align: center;
          padding: 12px 10px 10px;
        }
        .brand-banner img {
          width: 64px;
          height: 64px;
          object-fit: contain;
          display: block;
          margin: 0 auto 6px;
        }
        .brand-banner .org { font-size: 16px; font-weight: 800; }
        .brand-banner .abbr { color: var(--gold); font-weight: 800; margin-top: 2px; }
        .brand-banner .title { font-size: 13px; font-weight: 700; margin-top: 4px; }
        .meta-bar {
          position: relative;
          z-index: 1;
          display: flex;
          flex-wrap: wrap;
          gap: 10px 18px;
          justify-content: center;
          font-size: 11px;
          padding: 8px 6px;
          border-bottom: 3px solid var(--gold);
          background: #fff;
        }
        .table-wrap { position: relative; z-index: 1; }
        table.print-table {
          width: 100%;
          border-collapse: collapse;
          font-size: 10.5px;
          background: transparent;
        }
        table.print-table thead { display: table-header-group; }
        table.print-table tfoot { display: table-footer-group; }
        table.print-table tbody { display: table-row-group; }
        table.print-table th.col-h {
          background: var(--navy) !important;
          color: #fff !important;
          border: 1px solid #9CA3AF;
          padding: 7px 4px;
          text-align: center;
          font-weight: 700;
          -webkit-print-color-adjust: exact;
          print-color-adjust: exact;
        }
        table.print-table td {
          padding: 5px 4px;
          border: 1px solid #9CA3AF;
          text-align: right;
          vertical-align: top;
          word-break: break-word;
          background: #fff;
        }
        table.print-table tbody tr:nth-child(even) td { background: var(--alt); }
        table.print-table tr { page-break-inside: avoid; }
        .footer-cell {
          text-align: center;
          font-size: 11px;
          color: #1F2937;
          border: none !important;
          border-top: 2px solid var(--gold) !important;
          padding-top: 10px !important;
          padding-bottom: 4px !important;
          background: #fff !important;
        }
        .page-foot {
          text-align: center;
          font-size: 10px;
          color: #4B5563;
          padding-top: 4px;
        }
        @page {
          size: A4 landscape;
          margin: 10mm 8mm 14mm;
          @bottom-center {
            content: "Page " counter(page) " of " counter(pages);
            font-size: 10px;
            color: #4B5563;
            font-family: Tahoma, Arial, sans-serif;
          }
        }
        @media print {
          .no-print { display: none !important; }
          .print-root { padding: 0; }
          .brand-banner { page-break-after: avoid; }
          .meta-bar { page-break-after: avoid; }
          a { text-decoration: none; color: inherit; }
          table.print-table thead { display: table-header-group; }
        }
      `}</style>

      <div className="no-print flex gap-2 justify-center">
        <button
          type="button"
          onClick={() => window.print()}
          className="px-4 py-2 rounded text-white"
          style={{ background: navy }}
        >
          طباعة الآن
        </button>
        <button type="button" onClick={() => window.close()} className="px-4 py-2 rounded border">
          إغلاق
        </button>
      </div>

      {wmEnabled && logo ? (
        <div className="print-wm" aria-hidden>
          <img src={logo} alt="" />
        </div>
      ) : null}

      <div className="brand-banner">
        <img src={logo} alt="MFEC" />
        <div className="org">{data.org_name || brand.system_name || 'تجمع تجار التجارة الإلكترونية في العراق'}</div>
        <div className="abbr">{data.org_abbr || brand.org_abbr || 'MFEC'}</div>
        <div className="title">{data.report_title || brand.report_title || 'تقرير أعضاء تجمع تجار التجارة الإلكترونية في العراق'}</div>
      </div>
      <div className="meta-bar">
        <span>اسم المستخدم: {data.printed_by || '-'}</span>
        <span>تاريخ الطباعة: {printDate}</span>
        <span>وقت الطباعة: {printTime}</span>
        <span>إجمالي عدد السجلات: {data.total ?? items.length}</span>
      </div>

      <div className="table-wrap">
        <table className="print-table">
          <thead>
            <tr>
              <th className="col-h">#</th>
              <th className="col-h">رقم العضوية</th>
              <th className="col-h">اسم النشاط التجاري</th>
              <th className="col-h">اسم التاجر</th>
              <th className="col-h">رقم الهاتف</th>
              <th className="col-h">المحافظة</th>
              <th className="col-h">المنطقة</th>
              <th className="col-h">نوع النشاط</th>
              <th className="col-h">حالة الطلب</th>
              <th className="col-h">حالة العضوية</th>
              <th className="col-h">تاريخ الطلب</th>
              <th className="col-h">تاريخ الموافقة</th>
              <th className="col-h">آخر تعديل بواسطة</th>
              <th className="col-h">تاريخ آخر تعديل</th>
              {dynFields.map((f) => (
                <th key={f.id} className="col-h">{f.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {items.map((it, idx) => (
              <tr key={idx}>
                <td style={{ textAlign: 'center' }}>{idx + 1}</td>
                <td style={{ textAlign: 'center' }}>{it.membership_number || '-'}</td>
                <td>{it.business_name}</td>
                <td>{it.merchant_name}</td>
                <td style={{ textAlign: 'center', direction: 'ltr' }}>{it.phone}</td>
                <td>{it.governorate}</td>
                <td>{it.area}</td>
                <td>{it.business_type || '-'}</td>
                <td style={{ textAlign: 'center' }}>{statusLabel[it.status] || it.status}</td>
                <td style={{ textAlign: 'center' }}>
                  {msLabel[it.membership_status || ''] || it.membership_status || '-'}
                </td>
                <td>{it.created_at ? String(it.created_at).slice(0, 19) : '-'}</td>
                <td>{it.approved_at ? String(it.approved_at).slice(0, 19) : '-'}</td>
                <td>{it.last_modified_by || '-'}</td>
                <td>{it.updated_at ? String(it.updated_at).slice(0, 19) : '-'}</td>
                {dynFields.map((f) => (
                  <td key={f.id}>{dynValue(it, f)}</td>
                ))}
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td className="footer-cell" colSpan={colCount}>
                <div>{data.sponsor || 'برعاية شركة مسار الفهد للتجارة العامة والنقل العام'}</div>
                <div>{data.brand?.company_name || brand.company_name || ''}</div>
                <div style={{ marginTop: 4 }}>
                  {data.website || brand.website || 'www.masaralfahad.com'} |{' '}
                  {data.email || brand.email || 'management@masaralfahad.com'} |{' '}
                  {data.phone || brand.phone || '07748077716'}
                </div>
                <div style={{ marginTop: 4 }}>{data.brand?.copyright || brand.copyright || ''}</div>
                <div className="page-foot">Page — of — (يظهر تلقائياً عند الطباعة)</div>
              </td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  );
}
