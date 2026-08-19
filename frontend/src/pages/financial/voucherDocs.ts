/** Shared electronic voucher HTML + print/PDF helpers (REC/PAY). */
import html2canvas from 'html2canvas';
import { jsPDF } from 'jspdf';

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

const amountWords = (amount: number) =>
  `فقط ${Math.round(amount).toLocaleString('ar-IQ')} دينار عراقي لا غير`;

const money = (n: number) =>
  `${Number(n || 0).toLocaleString('ar-IQ')} د.ع`;

const sheetCss = (accent: string) => `
body{font-family:Tahoma,Arial,sans-serif;padding:28px;color:#172033;background:#f5f7fa;margin:0}
.sheet{border:2px solid ${accent};padding:28px;max-width:760px;margin:auto;background:#fff}
.head{display:flex;justify-content:space-between;align-items:center;border-bottom:2px solid ${accent};padding-bottom:16px;gap:12px}
.head img{width:90px;height:90px;object-fit:contain}
h1{text-align:center;margin:18px 0;font-size:22px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin:24px 0}
.field{border-bottom:1px solid #bbb;padding:10px}
.amount{font-size:22px;font-weight:bold}
.sign{margin-top:55px;display:flex;justify-content:space-between;gap:12px}
.foot{margin-top:24px;font-size:12px;color:#555;text-align:center}
.no-print{margin-top:16px;text-align:center}
@media print{body{background:#fff;padding:0}.no-print{display:none!important}}
`;

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
  const actions =
    mode === 'print'
      ? `<div class="no-print"><button onclick="window.print()">طباعة الوصل</button></div>`
      : mode === 'pdf'
        ? `<div class="no-print"><button onclick="window.print()">حفظ كـ PDF من مربع الطباعة</button></div>`
        : '';
  return `<!doctype html><html dir="rtl"><head><meta charset="utf-8"><title>وصل ${escapeHtml(row.receipt_number)}</title>
<style>${sheetCss(accent)}</style></head><body>
<div class="sheet" id="voucher-sheet">
  <div class="head">
    <img src="${escapeHtml(logoUrl)}" alt="logo"/>
    <div><b>${escapeHtml(brand.system_name)}</b><p>${escapeHtml(brand.org_abbr || 'MFEC')}</p><small>${escapeHtml(brand.company_name || '')}</small></div>
    <div>رقم الوصل<br><b>${escapeHtml(row.receipt_number)}</b></div>
  </div>
  <h1>وصل قبض إلكتروني</h1>
  <div class="grid">
    <div class="field">استلمنا من: <b>${escapeHtml(row.company_name || '-')}</b></div>
    <div class="field">التاريخ: <b>${escapeHtml(row.received_at)}</b></div>
    <div class="field amount">المبلغ: ${escapeHtml(money(row.amount))}</div>
    <div class="field">طريقة القبض: ${escapeHtml(row.receipt_method)}</div>
    <div class="field">التصنيف: ${escapeHtml(row.category || '-')}</div>
    <div class="field">الفترة: ${escapeHtml(row.period_start || '-')} — ${escapeHtml(row.period_end || '-')}</div>
    <div class="field">أنشأ الوصل: ${escapeHtml(row.created_by || '-')}</div>
  </div>
  <p><b>المبلغ كتابة:</b> ${escapeHtml(amountWords(row.amount))}</p>
  <p><b>وصف الإيراد:</b> ${escapeHtml(row.description)}</p>
  <p><b>ملاحظات:</b> ${escapeHtml(row.notes || '-')}</p>
  <div class="sign"><span>توقيع المستلم: __________</span><span>الختم/الاعتماد: __________</span></div>
  <div class="foot">${escapeHtml(brand.footer_text || '')}<br>${escapeHtml(brand.phone || '')} · ${escapeHtml(brand.email || '')}</div>
</div>${actions}
${mode === 'print' ? '<script>window.onload=function(){setTimeout(function(){window.print()},300)}</script>' : ''}
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
  const actions =
    mode === 'print'
      ? `<div class="no-print"><button onclick="window.print()">طباعة الوصل</button></div>`
      : mode === 'pdf'
        ? `<div class="no-print"><button onclick="window.print()">حفظ كـ PDF من مربع الطباعة</button></div>`
        : '';
  return `<!doctype html><html dir="rtl"><head><meta charset="utf-8"><title>وصل ${escapeHtml(row.payment_number)}</title>
<style>${sheetCss(accent)}</style></head><body>
<div class="sheet" id="voucher-sheet">
  <div class="head">
    <img src="${escapeHtml(logoUrl)}" alt="logo"/>
    <div><b>${escapeHtml(brand.system_name)}</b><p>${escapeHtml(brand.org_abbr || 'MFEC')}</p><small>${escapeHtml(brand.company_name || '')}</small></div>
    <div>رقم الوصل<br><b>${escapeHtml(row.payment_number || '-')}</b></div>
  </div>
  <h1>وصل صرف إلكتروني</h1>
  <div class="grid">
    <div class="field">دُفع إلى: <b>${escapeHtml(row.payee || '-')}</b></div>
    <div class="field">اسم الشخص: <b>${escapeHtml(row.person_name || '-')}</b></div>
    <div class="field">اسم الشركة: <b>${escapeHtml(row.company_name || '-')}</b></div>
    <div class="field">التاريخ: <b>${escapeHtml(row.expense_date)}</b></div>
    <div class="field amount">المبلغ: ${escapeHtml(money(row.amount))}</div>
    <div class="field">طريقة الدفع: ${escapeHtml(row.payment_method || '-')}</div>
    <div class="field">التصنيف: ${escapeHtml(row.category)}</div>
    <div class="field">أنشأ الوصل: ${escapeHtml(row.created_by || '-')}</div>
  </div>
  <p><b>المبلغ كتابة:</b> ${escapeHtml(amountWords(row.amount))}</p>
  <p><b>البيان/الغرض:</b> ${escapeHtml(row.description)}</p>
  <p><b>ملاحظات:</b> ${escapeHtml(row.notes || '-')}</p>
  <div class="sign"><span>توقيع المستلم: __________</span><span>الختم/الاعتماد: __________</span></div>
  <div class="foot">${escapeHtml(brand.footer_text || '')}<br>${escapeHtml(brand.phone || '')} · ${escapeHtml(brand.email || '')}</div>
</div>${actions}
${mode === 'print' ? '<script>window.onload=function(){setTimeout(function(){window.print()},300)}</script>' : ''}
</body></html>`;
}

export function openVoucherWindow(html: string, autoPrint = false) {
  const w = window.open('', '_blank', 'noopener,noreferrer,width=900,height=900');
  if (!w) throw new Error('تعذر فتح نافذة الوصل — اسمح بالنوافذ المنبثقة');
  w.document.write(html);
  w.document.close();
  if (autoPrint) {
    // print script also embedded for reliability
  }
  return w;
}

/** Render voucher HTML off-screen and download a real PDF file. */
export async function downloadVoucherPdf(html: string, filename: string) {
  const host = document.createElement('div');
  host.style.position = 'fixed';
  host.style.left = '-10000px';
  host.style.top = '0';
  host.style.width = '800px';
  host.style.background = '#fff';
  host.setAttribute('dir', 'rtl');
  document.body.appendChild(host);
  try {
    const doc = new DOMParser().parseFromString(html, 'text/html');
    const sheet = doc.getElementById('voucher-sheet');
    if (!sheet) throw new Error('تعذر بناء الوصل لـ PDF');
    // copy styles
    const style = doc.querySelector('style');
    if (style) host.appendChild(style.cloneNode(true));
    host.appendChild(sheet.cloneNode(true));
    const canvas = await html2canvas(host, { scale: 2, useCORS: true, backgroundColor: '#ffffff' });
    const img = canvas.toDataURL('image/png');
    const pdf = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' });
    const pageW = pdf.internal.pageSize.getWidth();
    const pageH = pdf.internal.pageSize.getHeight();
    const imgW = pageW - 16;
    const imgH = (canvas.height * imgW) / canvas.width;
    let y = 8;
    if (imgH <= pageH - 16) {
      pdf.addImage(img, 'PNG', 8, y, imgW, imgH);
    } else {
      // multi-page crop
      let remaining = imgH;
      let srcY = 0;
      const pxPerMm = canvas.height / imgH;
      while (remaining > 0) {
        const sliceH = Math.min(remaining, pageH - 16);
        const sliceCanvas = document.createElement('canvas');
        sliceCanvas.width = canvas.width;
        sliceCanvas.height = Math.max(1, Math.floor(sliceH * pxPerMm));
        const ctx = sliceCanvas.getContext('2d')!;
        ctx.drawImage(
          canvas,
          0,
          Math.floor(srcY * pxPerMm),
          canvas.width,
          sliceCanvas.height,
          0,
          0,
          canvas.width,
          sliceCanvas.height,
        );
        pdf.addImage(sliceCanvas.toDataURL('image/png'), 'PNG', 8, 8, imgW, sliceH);
        remaining -= sliceH;
        srcY += sliceH;
        if (remaining > 0) pdf.addPage();
      }
    }
    pdf.save(filename.endsWith('.pdf') ? filename : `${filename}.pdf`);
  } finally {
    host.remove();
  }
}

export { money, amountWords, escapeHtml };
