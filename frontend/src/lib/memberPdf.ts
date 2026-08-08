import { jsPDF } from 'jspdf';
import html2canvas from 'html2canvas';
import JSZip from 'jszip';
import type { BrandSettings } from '@/lib/brand';
import { watermarkEnabled, watermarkOpacity } from '@/lib/Watermark';
import { getAPIBaseURL } from '@/lib/config';

export type MemberForPdf = {
  id: number;
  membership_number?: string | null;
  request_number?: string | null;
  business_name: string;
  merchant_name: string;
  phone: string;
  governorate: string;
  area: string;
  business_type?: string | null;
  notes?: string | null;
  status: string;
  membership_status?: string | null;
  created_at?: string | null;
  approved_at?: string | null;
  image_key?: string | null;
  last_modified_by?: string | null;
  extra_fields?: Record<string, { label?: string; value?: any }> | null;
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

type JsPdfImageFormat = 'JPEG' | 'PNG';

export function membershipPdfFileName(member: MemberForPdf): string {
  const raw = (member.membership_number || '').trim();
  let base = raw.replace(/^MF-/i, '').replace(/[^\w-]/g, '');
  if (!base) base = String(member.id);
  return `${base}.pdf`;
}

function absoluteUrl(path: string): string {
  if (!path) return '';
  if (path.startsWith('data:') || path.startsWith('http://') || path.startsWith('https://')) return path;
  if (path.startsWith('/api/')) {
    const base = (getAPIBaseURL() || '').replace(/\/$/, '');
    return base ? `${base}${path}` : `${typeof window !== 'undefined' ? window.location.origin : ''}${path}`;
  }
  if (path.startsWith('/')) {
    return `${typeof window !== 'undefined' ? window.location.origin : ''}${path}`;
  }
  return path;
}

/** Detect real image type from data-URL / bytes — never trust extension alone. */
function detectDataUrlFormat(dataUrl: string): JsPdfImageFormat | null {
  if (!dataUrl || !dataUrl.startsWith('data:')) return null;
  const header = dataUrl.slice(0, 64).toLowerCase();
  if (header.startsWith('data:image/jpeg') || header.startsWith('data:image/jpg')) return 'JPEG';
  if (header.startsWith('data:image/png')) return 'PNG';
  // Inspect base64 magic if MIME missing/wrong
  const b64 = dataUrl.split(',')[1] || '';
  if (!b64) return null;
  try {
    const bin = atob(b64.slice(0, 24));
    const bytes = Array.from(bin).map((c) => c.charCodeAt(0));
    // PNG: 89 50 4E 47
    if (bytes[0] === 0x89 && bytes[1] === 0x50 && bytes[2] === 0x4e && bytes[3] === 0x47) return 'PNG';
    // JPEG: FF D8 FF
    if (bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff) return 'JPEG';
  } catch {
    return null;
  }
  return null;
}

function isLikelyHtmlBlob(blob: Blob, sampleText: string): boolean {
  const t = (blob.type || '').toLowerCase();
  if (t.includes('text/html') || t.includes('application/json') || t.includes('text/plain')) return true;
  const s = sampleText.trim().slice(0, 64).toLowerCase();
  return s.startsWith('<!doctype') || s.startsWith('<html') || s.startsWith('{');
}

/** Re-encode any valid image into a clean JPEG data-URL (jsPDF-safe). */
async function reencodeToJpegDataUrl(src: string, maxEdge = 1600): Promise<string | null> {
  if (!src || !src.startsWith('data:image/')) return null;
  return new Promise((resolve) => {
    const img = new Image();
    const timer = setTimeout(() => resolve(null), 10000);
    img.onload = () => {
      clearTimeout(timer);
      try {
        let w = img.naturalWidth || img.width || 1;
        let h = img.naturalHeight || img.height || 1;
        const scale = Math.min(1, maxEdge / Math.max(w, h));
        w = Math.max(1, Math.round(w * scale));
        h = Math.max(1, Math.round(h * scale));
        const canvas = document.createElement('canvas');
        canvas.width = w;
        canvas.height = h;
        const ctx = canvas.getContext('2d');
        if (!ctx) {
          resolve(null);
          return;
        }
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(0, 0, w, h);
        ctx.drawImage(img, 0, 0, w, h);
        const out = canvas.toDataURL('image/jpeg', 0.92);
        resolve(detectDataUrlFormat(out) === 'JPEG' ? out : null);
      } catch (err) {
        console.warn('[PDF] reencode failed', err);
        resolve(null);
      }
    };
    img.onerror = () => {
      clearTimeout(timer);
      resolve(null);
    };
    img.src = src;
  });
}

async function fetchAsValidatedDataUrl(url: string): Promise<string | null> {
  try {
    const res = await fetch(url, { mode: 'cors', credentials: 'omit', cache: 'no-cache' });
    if (!res.ok) {
      console.warn('[PDF] image HTTP', res.status, url);
      return null;
    }
    const blob = await res.blob();
    if (!blob || blob.size < 24) return null;
    // Peek text for HTML/JSON error bodies
    const peek = await blob.slice(0, 64).text().catch(() => '');
    if (isLikelyHtmlBlob(blob, peek)) {
      console.warn('[PDF] image URL returned HTML/JSON, skipped', url);
      return null;
    }
    const raw = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ''));
      reader.onerror = () => reject(reader.error);
      reader.readAsDataURL(blob);
    });
    // Always re-encode to JPEG so jsPDF never sees WebP / bad PNG signatures
    return (await reencodeToJpegDataUrl(raw)) || null;
  } catch (err) {
    console.warn('[PDF] fetch image failed', url, err);
    return null;
  }
}

async function loadImageSafe(url: string): Promise<string | null> {
  if (!url) return null;
  if (url.startsWith('data:')) {
    if (detectDataUrlFormat(url) === 'JPEG') return url;
    return reencodeToJpegDataUrl(url);
  }
  const abs = absoluteUrl(url);
  return fetchAsValidatedDataUrl(abs);
}

/** Load brand logo with fallbacks; never throws — empty string if unavailable. */
export async function loadBrandLogoDataUrl(
  brand: BrandSettings,
  preferredUrl?: string
): Promise<string> {
  const candidates = [
    preferredUrl,
    brand.report_logo,
    brand.system_logo,
    '/brand/mfec-logo.png',
  ].filter(Boolean) as string[];

  const seen = new Set<string>();
  for (const c of candidates) {
    const abs = absoluteUrl(c);
    if (!abs || seen.has(abs)) continue;
    seen.add(abs);
    try {
      const data = await loadImageSafe(abs);
      if (data && detectDataUrlFormat(data) === 'JPEG') return data;
    } catch (err) {
      console.warn('[PDF] logo candidate failed', abs, err);
    }
  }
  console.warn('[PDF] no usable brand logo — continuing without logo/watermark');
  return '';
}

function waitForImages(root: HTMLElement): Promise<void> {
  const imgs = Array.from(root.querySelectorAll('img'));
  return Promise.all(
    imgs.map(
      (img) =>
        new Promise<void>((resolve) => {
          if (img.complete && img.naturalWidth > 0) {
            resolve();
            return;
          }
          const done = () => resolve();
          img.onload = done;
          img.onerror = done;
          setTimeout(done, 5000);
        })
    )
  ).then(() => undefined);
}

function esc(v: any) {
  return String(v ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function collectDynamicRows(member: MemberForPdf): [string, string][] {
  const rows: [string, string][] = [];
  const seen = new Set<string>();
  const extras = member.extra_fields || {};
  Object.values(extras).forEach((entry) => {
    if (!entry) return;
    const label = String(entry.label || '').trim();
    const value = entry.value;
    if (!label || value === undefined || value === null || value === '') return;
    const shown = Array.isArray(value) ? value.join(', ') : String(value);
    rows.push([label, shown]);
    seen.add(label);
  });
  String(member.notes || '')
    .split(/\r?\n/)
    .forEach((line) => {
      const idx = line.indexOf(':');
      if (idx <= 0) return;
      const label = line.slice(0, idx).trim();
      const value = line.slice(idx + 1).trim();
      if (!label || !value || seen.has(label)) return;
      rows.push([label, value]);
      seen.add(label);
    });
  return rows;
}

function buildFormPageHtml(
  member: MemberForPdf,
  brand: BrandSettings,
  logoDataUrl: string,
  meta: { generatedBy: string; generatedAt: string }
): HTMLElement {
  const navy = brand.primary_color || '#1F2937';
  const gold = brand.secondary_color || '#C89B3C';
  const wmOn = watermarkEnabled(brand) && !!logoDataUrl;
  const wmOp = Math.max(watermarkOpacity(brand), 0.06);
  const wrap = document.createElement('div');
  wrap.setAttribute('dir', 'rtl');
  wrap.style.cssText = `
    width: 794px; background: #fff; color: #111;
    font-family: ${brand.font_family || 'Tahoma, Arial, sans-serif'};
    box-sizing: border-box; position: relative;
  `;

  const dynRows = collectDynamicRows(member);
  const rows: [string, string][] = [
    ['رقم العضوية', member.membership_number || '-'],
    ['رقم الطلب', member.request_number || '-'],
    ['اسم النشاط التجاري', member.business_name || '-'],
    ['اسم التاجر', member.merchant_name || '-'],
    ['رقم الهاتف', member.phone || '-'],
    ['المحافظة', member.governorate || '-'],
    ['المنطقة', member.area || '-'],
    ['نوع النشاط', member.business_type || '-'],
    ['حالة الطلب', statusLabel[member.status] || member.status || '-'],
    ['حالة العضوية', msLabel[member.membership_status || ''] || member.membership_status || '-'],
    ['تاريخ التسجيل', member.created_at ? String(member.created_at).slice(0, 19) : '-'],
    ['تاريخ القبول', member.approved_at ? String(member.approved_at).slice(0, 19) : '-'],
    ['آخر تعديل بواسطة', member.last_modified_by || '-'],
    ...dynRows,
  ];

  const dynLabels = new Set(dynRows.map(([l]) => l));
  const leftoverNotes = String(member.notes || '')
    .split(/\r?\n/)
    .filter((line) => {
      const idx = line.indexOf(':');
      if (idx <= 0) return !!line.trim();
      return !dynLabels.has(line.slice(0, idx).trim());
    })
    .join('\n')
    .trim();
  if (leftoverNotes) rows.push(['ملاحظات', leftoverNotes]);

  const fieldsHtml = rows
    .map(
      ([label, value]) => `
      <div style="display:flex; gap:12px; border-bottom:1px solid #E5E7EB; padding:9px 4px;">
        <div style="width:200px; font-weight:700; color:${navy}; flex-shrink:0;">${esc(label)}</div>
        <div style="flex:1; text-align:right; color:#111;">${esc(value)}</div>
      </div>`
    )
    .join('');

  const logoTag = logoDataUrl
    ? `<img src="${logoDataUrl}" width="64" height="64" style="width:64px;height:64px;object-fit:contain;background:rgba(255,255,255,.12);border-radius:8px;display:block;" />`
    : '';

  const wmHtml = wmOn
    ? `<div style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;pointer-events:none;z-index:0;">
         <img src="${logoDataUrl}" style="max-width:58%;max-height:58%;object-fit:contain;opacity:${wmOp};" />
       </div>`
    : '';

  wrap.innerHTML = `
    <div style="background:${navy};color:#fff;padding:16px 18px;position:relative;z-index:2;">
      <div style="display:flex;align-items:center;gap:14px;justify-content:center;">
        ${logoTag}
        <div style="text-align:center;">
          <div style="font-size:18px;font-weight:800;">${esc(brand.system_name)}</div>
          <div style="color:${gold};font-weight:800;margin-top:2px;">${esc(brand.org_abbr || 'MFEC')}</div>
          <div style="margin-top:6px;font-size:14px;font-weight:700;">${esc(brand.report_title || 'استمارة عضوية')}</div>
        </div>
      </div>
      <div style="margin-top:10px;font-size:11px;opacity:.95;text-align:center;">
        التاريخ والوقت: ${esc(meta.generatedAt)} · بواسطة: ${esc(meta.generatedBy)}
      </div>
    </div>
    <div style="height:3px;background:${gold};position:relative;z-index:2;"></div>
    <div style="position:relative;padding:18px 22px 12px;min-height:560px;">
      ${wmHtml}
      <div style="position:relative;z-index:1;">
        <div style="font-weight:800;color:${navy};margin-bottom:8px;font-size:15px;">بيانات العضو</div>
        ${fieldsHtml}
      </div>
    </div>
    <div style="margin:0 22px 0;padding:12px 0 28px;border-top:2px solid ${gold};text-align:center;font-size:11px;color:#374151;position:relative;z-index:2;background:#fff;line-height:1.55;">
      <div style="font-weight:700;">${esc(brand.company_name)}</div>
      <div>${esc(brand.website)} | ${esc(brand.email)} | ${esc(brand.phone)}</div>
      <div>${esc(brand.copyright)}</div>
      <div style="margin-top:4px;padding-bottom:8px;">${esc(brand.footer_text)}</div>
    </div>
  `;
  return wrap;
}

function buildImagePageHtml(brand: BrandSettings, imageDataUrl: string, logoDataUrl: string): HTMLElement {
  const navy = brand.primary_color || '#1F2937';
  const gold = brand.secondary_color || '#C89B3C';
  const wrap = document.createElement('div');
  wrap.setAttribute('dir', 'rtl');
  wrap.style.cssText = `
    width: 794px; min-height: 1123px; background: #fff; color: #111;
    font-family: ${brand.font_family || 'Tahoma, Arial, sans-serif'};
    box-sizing: border-box;
  `;
  const logoTag = logoDataUrl
    ? `<img src="${logoDataUrl}" width="48" height="48" style="width:48px;height:48px;object-fit:contain;" />`
    : '';
  wrap.innerHTML = `
    <div style="background:${navy};color:#fff;padding:14px 18px;text-align:center;">
      <div style="display:flex;align-items:center;justify-content:center;gap:10px;">
        ${logoTag}
        <div style="font-weight:800;">صورة النشاط التجاري</div>
      </div>
      <div style="height:3px;background:${gold};margin-top:10px;"></div>
    </div>
    <div style="padding:24px;display:flex;align-items:center;justify-content:center;min-height:980px;">
      <img src="${imageDataUrl}" style="max-width:100%;max-height:920px;object-fit:contain;" />
    </div>
  `;
  return wrap;
}

function safeAddImage(doc: jsPDF, dataUrl: string, x: number, y: number, w: number, h: number) {
  const fmt = detectDataUrlFormat(dataUrl);
  if (!fmt) {
    console.warn('[PDF] skip addImage — invalid image payload');
    return;
  }
  // Prefer JPEG always for reliability with jsPDF
  if (fmt === 'JPEG') {
    doc.addImage(dataUrl, 'JPEG', x, y, w, h);
    return;
  }
  // PNG only if signature truly PNG
  try {
    doc.addImage(dataUrl, 'PNG', x, y, w, h);
  } catch (err) {
    console.warn('[PDF] PNG addImage failed, skipped', err);
  }
}

async function renderElementToPdfPage(doc: jsPDF, el: HTMLElement, addPage: boolean) {
  const host = document.createElement('div');
  host.style.cssText =
    'position:fixed;left:0;top:0;width:794px;opacity:0.01;pointer-events:none;z-index:0;overflow:hidden;';
  host.appendChild(el);
  document.body.appendChild(host);
  try {
    await waitForImages(el);
    await new Promise((r) => setTimeout(r, 100));
    const canvas = await html2canvas(el, {
      scale: 2,
      useCORS: true,
      allowTaint: false,
      backgroundColor: '#ffffff',
      logging: false,
      imageTimeout: 20000,
    });
    const pageW = doc.internal.pageSize.getWidth();
    const pageH = doc.internal.pageSize.getHeight();
    // Keep bottom margin so footer text is never clipped at page edge
    const marginBottomMm = 12;
    const usablePageH = Math.max(pageH - marginBottomMm, pageH * 0.92);
    const imgW = canvas.width;
    const imgH = canvas.height;
    const pxPerMm = imgW / pageW;
    const pageHeightPx = usablePageH * pxPerMm;
    let y = 0;
    let page = 0;
    while (y < imgH) {
      const sliceH = Math.min(pageHeightPx, imgH - y);
      const sliceCanvas = document.createElement('canvas');
      sliceCanvas.width = imgW;
      sliceCanvas.height = sliceH;
      const ctx = sliceCanvas.getContext('2d');
      if (!ctx) break;
      ctx.fillStyle = '#fff';
      ctx.fillRect(0, 0, imgW, sliceH);
      ctx.drawImage(canvas, 0, y, imgW, sliceH, 0, 0, imgW, sliceH);
      // Always JPEG for jsPDF — avoids "wrong PNG signature"
      const data = sliceCanvas.toDataURL('image/jpeg', 0.92);
      if (detectDataUrlFormat(data) !== 'JPEG') {
        console.warn('[PDF] canvas export was not JPEG — skipping slice');
        break;
      }
      if (addPage || page > 0) doc.addPage();
      const hMm = (sliceH / imgW) * pageW;
      safeAddImage(doc, data, 0, 0, pageW, Math.min(hMm, usablePageH));
      y += sliceH;
      page += 1;
    }
  } finally {
    document.body.removeChild(host);
  }
}

export async function buildMemberPdfBlob(
  member: MemberForPdf,
  brand: BrandSettings,
  opts: {
    logoUrl: string;
    imageUrl?: string | null;
    generatedBy?: string;
  }
): Promise<Blob> {
  const doc = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' });

  let logoDataUrl = '';
  try {
    logoDataUrl = await loadBrandLogoDataUrl(brand, opts.logoUrl);
  } catch (err) {
    console.warn('[PDF] logo load error — continuing without logo', err);
  }

  let imageDataUrl: string | null = null;
  if (opts.imageUrl && member.image_key && member.image_key !== 'manual_entry') {
    try {
      imageDataUrl = await loadImageSafe(opts.imageUrl);
      if (!imageDataUrl) console.warn('[PDF] business image skipped (invalid/unsupported)');
    } catch (err) {
      console.warn('[PDF] business image load error — page omitted', err);
      imageDataUrl = null;
    }
  }

  const now = new Date();
  const formEl = buildFormPageHtml(member, brand, logoDataUrl, {
    generatedBy: opts.generatedBy || '-',
    generatedAt: now.toLocaleString('ar-IQ'),
  });
  await renderElementToPdfPage(doc, formEl, false);

  if (imageDataUrl) {
    const imageEl = buildImagePageHtml(brand, imageDataUrl, logoDataUrl);
    await renderElementToPdfPage(doc, imageEl, true);
  }

  return doc.output('blob');
}

function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export async function downloadMemberPdf(
  member: MemberForPdf,
  brand: BrandSettings,
  opts: { logoUrl: string; imageUrl?: string | null; generatedBy?: string }
) {
  const blob = await buildMemberPdfBlob(member, brand, opts);
  triggerDownload(blob, membershipPdfFileName(member));
}

export async function downloadMembersZip(
  members: MemberForPdf[],
  brand: BrandSettings,
  resolveImageUrl: (member: MemberForPdf) => Promise<string | null>,
  logoUrl: string,
  generatedBy?: string,
  onProgress?: (done: number, total: number) => void
) {
  await loadBrandLogoDataUrl(brand, logoUrl);
  const zip = new JSZip();
  const usedNames = new Set<string>();
  let i = 0;
  for (const member of members) {
    const imageUrl = await resolveImageUrl(member);
    const blob = await buildMemberPdfBlob(member, brand, { logoUrl, imageUrl, generatedBy });
    let name = membershipPdfFileName(member);
    if (usedNames.has(name)) name = name.replace(/\.pdf$/i, `_${member.id}.pdf`);
    usedNames.add(name);
    zip.file(name, blob);
    i += 1;
    onProgress?.(i, members.length);
  }
  const zipBlob = await zip.generateAsync({ type: 'blob' });
  triggerDownload(zipBlob, `members_pdf_${new Date().toISOString().slice(0, 10)}.zip`);
}

export function buildWelcomeMessage(template: string, membershipNumber: string, brand: BrandSettings) {
  return (template || '')
    .replaceAll('{membership_number}', membershipNumber || '-')
    .replaceAll('{system_name}', brand.system_name || '')
    .replaceAll('{org_abbr}', brand.org_abbr || 'MFEC');
}
