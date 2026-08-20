/** Shared electronic voucher HTML + print/PDF/ZIP helpers (REC/PAY). */
import html2canvas from 'html2canvas';
import { jsPDF } from 'jspdf';
import JSZip from 'jszip';

export type BrandSlice = {
  system_name?: string;
  org_abbr?: string;
  company_name?: string;
  footer_text?: string;
  phone?: string;
  email?: string;
  report_logo?: string;
  system_logo?: string;
};

const escapeHtml = (value: unknown) =>
  String(value ?? '').replace(/[&<>"']/g, (ch) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]!),
  );

/** Always Western digits 0-9 (never Arabic-Indic ١٢٣). Display only. */
export const formatLatn = (n: number | string | undefined, opts?: Intl.NumberFormatOptions) =>
  Number(n || 0).toLocaleString('en-US', { maximumFractionDigits: 3, ...opts });

const amountWords = (amount: number) =>
  `فقط ${formatLatn(Math.round(amount), { maximumFractionDigits: 0 })} دينار عراقي لا غير`;

const money = (n: number) => `${formatLatn(n)} د.ع`;

const a4Css = (accent: string) => `
@page{size:A4 portrait;margin:10mm}
*{box-sizing:border-box}
html,body{margin:0;padding:0;background:#fff;color:#172033;font-family:Tahoma,"Segoe UI",Arial,sans-serif}
body{padding:0}
.sheet{
  width:190mm;min-height:277mm;margin:0 auto;padding:10mm 12mm;
  border:2.5px solid ${accent};display:flex;flex-direction:column;gap:0;
  background:#fff;
}
.head{display:flex;justify-content:space-between;align-items:center;gap:12px;border-bottom:2px solid ${accent};padding-bottom:10px}
.head img{width:78px;height:78px;object-fit:contain}
.head .brand{text-align:center;flex:1}
.head .brand b{font-size:16px;display:block}
.head .brand p{margin:4px 0 0;font-size:13px;color:#445}
.head .num{text-align:left;font-size:13px;min-width:110px}
.head .num b{font-size:18px;font-family:ui-monospace,Consolas,monospace;display:block;margin-top:4px;letter-spacing:.02em}
h1{text-align:center;margin:14px 0 10px;font-size:22px;color:${accent}}
.meta{display:grid;grid-template-columns:1fr 1fr;gap:10px 16px;margin:8px 0 12px}
.field{border:1px solid #d5dbe3;border-radius:6px;padding:10px 12px;min-height:52px;background:#fafbfc}
.field label{display:block;font-size:11px;color:#64748b;margin-bottom:4px}
.field b,.field .val{font-size:14px;font-weight:700;word-break:break-word}
.field.amount{grid-column:1/-1;background:#f8fafc;border-color:${accent}}
.field.amount .val{font-size:22px;color:${accent}}
.field.full{grid-column:1/-1}
.block{border:1px solid #d5dbe3;border-radius:6px;padding:12px;margin:8px 0;min-height:64px}
.block label{display:block;font-size:11px;color:#64748b;margin-bottom:6px}
.block .val{font-size:14px;line-height:1.6;white-space:pre-wrap;word-break:break-word}
.words{margin:10px 0;padding:10px 12px;background:#f1f5f9;border-radius:6px;font-size:14px}
.sign{margin-top:auto;padding-top:28px;display:flex;justify-content:space-between;gap:24px}
.sign .box{flex:1;text-align:center;border-top:1px solid #94a3b8;padding-top:10px;font-size:13px;min-height:70px}
.foot{margin-top:16px;padding-top:10px;border-top:1px dashed #cbd5e1;font-size:11px;color:#64748b;text-align:center;line-height:1.5}
.no-print{margin:12px auto;text-align:center}
.no-print button{font:inherit;padding:8px 16px;cursor:pointer}
@media print{
  body{background:#fff}
  .no-print{display:none!important}
  .sheet{border-width:2px;width:auto;min-height:auto;padding:0;margin:0}
}
`;

function headBlock(brand: BrandSlice, logoUrl: string, numberLabel: string, numberValue: string) {
  return `<div class="head">
  <img src="${escapeHtml(logoUrl)}" alt="logo"/>
  <div class="brand">
    <b>${escapeHtml(brand.system_name || '')}</b>
    <p>${escapeHtml(brand.org_abbr || 'MFEC')}</p>
    <small>${escapeHtml(brand.company_name || '')}</small>
  </div>
  <div class="num">${escapeHtml(numberLabel)}<b>${escapeHtml(numberValue)}</b></div>
</div>`;
}

function footBlock(brand: BrandSlice) {
  return `<div class="foot">${escapeHtml(brand.footer_text || '')}<br/>${escapeHtml(brand.phone || '')} · ${escapeHtml(brand.email || '')}</div>`;
}

function printChrome(mode: 'view' | 'print' | 'pdf') {
  if (mode === 'print') {
    return `<div class="no-print"><button type="button" onclick="window.print()">طباعة الوصل</button></div>
<script>
(function(){
  function go(){ try{ window.focus(); window.print(); }catch(e){} }
  if(document.readyState==='complete') setTimeout(go,250);
  else window.addEventListener('load',function(){ setTimeout(go,250); });
})();
</script>`;
  }
  return '';
}

export function receiptVoucherHtml(opts: {
  brand: BrandSlice;
  logoUrl: string;
  row: {
    receipt_number: string;
    company_name: string;
    received_at: string;
    amount: number;
    receipt_method: string;
    category?: string;
    description: string;
    period_start?: string;
    period_end?: string;
    notes?: string;
    created_by?: string;
  };
  mode: 'view' | 'print' | 'pdf';
}) {
  const { brand, logoUrl, row, mode } = opts;
  const accent = '#1e506b';
  const period =
    row.period_start || row.period_end
      ? `${row.period_start || '—'} — ${row.period_end || '—'}`
      : '—';
  return `<!doctype html><html dir="rtl" lang="ar"><head><meta charset="utf-8"/><title>وصل ${escapeHtml(row.receipt_number)}</title>
<style>${a4Css(accent)}</style></head><body>
<div class="sheet" id="voucher-sheet">
  ${headBlock(brand, logoUrl, 'رقم الوصل', row.receipt_number)}
  <h1>وصل قبض إلكتروني</h1>
  <div class="meta">
    <div class="field"><label>التاريخ</label><b>${escapeHtml(row.received_at)}</b></div>
    <div class="field"><label>استلمنا من / الشركة</label><b>${escapeHtml(row.company_name || '—')}</b></div>
    <div class="field amount"><label>المبلغ رقمًا</label><div class="val">${escapeHtml(money(row.amount))}</div></div>
    <div class="field"><label>طريقة القبض</label><b>${escapeHtml(row.receipt_method || '—')}</b></div>
    <div class="field"><label>التصنيف</label><b>${escapeHtml(row.category || '—')}</b></div>
    <div class="field"><label>الفترة</label><b>${escapeHtml(period)}</b></div>
    <div class="field"><label>منشئ الوصل</label><b>${escapeHtml(row.created_by || '—')}</b></div>
  </div>
  <div class="words"><b>المبلغ كتابة:</b> ${escapeHtml(amountWords(row.amount))}</div>
  <div class="block full"><label>البيان / الوصف</label><div class="val">${escapeHtml(row.description || '—')}</div></div>
  <div class="block"><label>الملاحظات</label><div class="val">${escapeHtml(row.notes || '—')}</div></div>
  <div class="sign"><div class="box">توقيع المستلم</div><div class="box">الختم / الاعتماد</div></div>
  ${footBlock(brand)}
</div>
${printChrome(mode)}
</body></html>`;
}

export function paymentVoucherHtml(opts: {
  brand: BrandSlice;
  logoUrl: string;
  row: {
    payment_number?: string;
    expense_date: string;
    payee?: string;
    person_name?: string;
    company_name?: string;
    payment_method?: string;
    category: string;
    description: string;
    amount: number;
    notes?: string;
    created_by?: string;
  };
  mode: 'view' | 'print' | 'pdf';
}) {
  const { brand, logoUrl, row, mode } = opts;
  const accent = '#7a2e2e';
  const number = row.payment_number || '—';
  return `<!doctype html><html dir="rtl" lang="ar"><head><meta charset="utf-8"/><title>وصل ${escapeHtml(number)}</title>
<style>${a4Css(accent)}</style></head><body>
<div class="sheet" id="voucher-sheet">
  ${headBlock(brand, logoUrl, 'رقم الوصل', number)}
  <h1>وصل صرف إلكتروني</h1>
  <div class="meta">
    <div class="field"><label>التاريخ</label><b>${escapeHtml(row.expense_date)}</b></div>
    <div class="field"><label>دُفع إلى</label><b>${escapeHtml(row.payee || '—')}</b></div>
    <div class="field"><label>اسم الشخص</label><b>${escapeHtml(row.person_name || '—')}</b></div>
    <div class="field"><label>اسم الشركة</label><b>${escapeHtml(row.company_name || '—')}</b></div>
    <div class="field amount"><label>المبلغ رقمًا</label><div class="val">${escapeHtml(money(row.amount))}</div></div>
    <div class="field"><label>طريقة الدفع</label><b>${escapeHtml(row.payment_method || '—')}</b></div>
    <div class="field"><label>التصنيف</label><b>${escapeHtml(row.category || '—')}</b></div>
    <div class="field"><label>منشئ الوصل</label><b>${escapeHtml(row.created_by || '—')}</b></div>
  </div>
  <div class="words"><b>المبلغ كتابة:</b> ${escapeHtml(amountWords(row.amount))}</div>
  <div class="block"><label>البيان / الوصف</label><div class="val">${escapeHtml(row.description || '—')}</div></div>
  <div class="block"><label>الملاحظات</label><div class="val">${escapeHtml(row.notes || '—')}</div></div>
  <div class="sign"><div class="box">توقيع المستلم</div><div class="box">الختم / الاعتماد</div></div>
  ${footBlock(brand)}
</div>
${printChrome(mode)}
</body></html>`;
}

/**
 * Open voucher in a real document via Blob URL.
 * Avoids about:blank caused by window.open('',…) + noopener (null handle / no write).
 */
export function openVoucherWindow(html: string) {
  const blob = new Blob([html], { type: 'text/html;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const w = window.open(url, '_blank');
  if (!w) {
    URL.revokeObjectURL(url);
    throw new Error('تعذر فتح نافذة الوصل — اسمح بالنوافذ المنبثقة لهذا الموقع ثم أعد المحاولة');
  }
  window.setTimeout(() => URL.revokeObjectURL(url), 120_000);
  return w;
}

async function renderVoucherCanvas(html: string) {
  const host = document.createElement('div');
  host.style.position = 'fixed';
  host.style.left = '-12000px';
  host.style.top = '0';
  host.style.width = '794px'; // ~A4 CSS px at 96dpi
  host.style.background = '#ffffff';
  host.setAttribute('dir', 'rtl');
  document.body.appendChild(host);
  try {
    const doc = new DOMParser().parseFromString(html, 'text/html');
    const sheet = doc.getElementById('voucher-sheet');
    if (!sheet) throw new Error('تعذر بناء الوصل لـ PDF');
    const style = doc.querySelector('style');
    if (style) host.appendChild(style.cloneNode(true));
    const clone = sheet.cloneNode(true) as HTMLElement;
    clone.style.width = '190mm';
    clone.style.minHeight = '277mm';
    clone.style.margin = '0';
    host.appendChild(clone);
    // wait fonts/images
    await new Promise((r) => setTimeout(r, 80));
    const canvas = await html2canvas(clone, {
      scale: 2,
      useCORS: true,
      allowTaint: true,
      backgroundColor: '#ffffff',
      logging: false,
    });
    return canvas;
  } finally {
    host.remove();
  }
}

export async function voucherPdfBlob(html: string): Promise<Blob> {
  const canvas = await renderVoucherCanvas(html);
  const img = canvas.toDataURL('image/jpeg', 0.95);
  const pdf = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' });
  const pageW = pdf.internal.pageSize.getWidth();
  const pageH = pdf.internal.pageSize.getHeight();
  const margin = 8;
  const imgW = pageW - margin * 2;
  const imgH = (canvas.height * imgW) / canvas.width;
  if (imgH <= pageH - margin * 2) {
    pdf.addImage(img, 'JPEG', margin, margin, imgW, imgH);
  } else {
    // Scale to fit one page (prefer single-page A4 voucher)
    const fitH = pageH - margin * 2;
    const fitW = (canvas.width * fitH) / canvas.height;
    const x = margin + Math.max(0, (imgW - fitW) / 2);
    pdf.addImage(img, 'JPEG', x, margin, Math.min(fitW, imgW), fitH);
  }
  return pdf.output('blob');
}

export async function downloadVoucherPdf(html: string, filename: string) {
  const blob = await voucherPdfBlob(html);
  const name = filename.endsWith('.pdf') ? filename : `${filename}.pdf`;
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  a.rel = 'noopener';
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/** One PDF file per voucher, packed into a single ZIP. */
export async function downloadVoucherPdfZip(
  items: { html: string; filename: string }[],
  zipName: string,
) {
  if (!items.length) throw new Error('لم يتم تحديد أي وصولات للتصدير');
  const zip = new JSZip();
  for (const item of items) {
    const blob = await voucherPdfBlob(item.html);
    const name = item.filename.endsWith('.pdf') ? item.filename : `${item.filename}.pdf`;
    zip.file(name, blob);
  }
  const out = await zip.generateAsync({ type: 'blob' });
  const url = URL.createObjectURL(out);
  const a = document.createElement('a');
  a.href = url;
  a.download = zipName.endsWith('.zip') ? zipName : `${zipName}.zip`;
  a.rel = 'noopener';
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export { money, amountWords, escapeHtml };
