import type { BrandSettings } from '@/lib/brand';

/** Opacity fraction 0.05–0.10 from brand percent setting (5–10). */
export function watermarkOpacity(brand: BrandSettings): number {
  const raw = Number(brand.watermark_opacity);
  const pct = Number.isFinite(raw) ? raw : 7;
  const clamped = Math.min(10, Math.max(5, pct));
  return clamped / 100;
}

export function watermarkEnabled(brand: BrandSettings): boolean {
  const v = String(brand.watermark_enabled ?? 'true').toLowerCase();
  return v === 'true' || v === '1' || v === 'yes';
}

export function WatermarkLayer({
  logoUrl,
  brand,
  className = '',
}: {
  logoUrl: string;
  brand: BrandSettings;
  className?: string;
}) {
  if (!watermarkEnabled(brand)) return null;
  const opacity = watermarkOpacity(brand);
  return (
    <div
      aria-hidden
      className={`pointer-events-none absolute inset-0 flex items-center justify-center overflow-hidden ${className}`}
      style={{ zIndex: 0 }}
    >
      <img
        src={logoUrl}
        alt=""
        className="select-none max-w-[70%] max-h-[70%] object-contain"
        style={{ opacity, filter: 'grayscale(10%)' }}
      />
    </div>
  );
}
