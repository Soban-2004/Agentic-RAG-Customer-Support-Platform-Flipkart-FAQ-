export function BrandMark({ className = "" }: { className?: string }) {
  return <svg className={className} viewBox="0 0 40 40" fill="none" aria-hidden="true"><path d="M20 3C20 14 26 20 37 20C26 20 20 26 20 37C20 26 14 20 3 20C14 20 20 14 20 3Z" fill="currentColor" /><circle cx="20" cy="20" r="3" fill="var(--bg)" /></svg>
}
export function Brand({ compact = false }: { compact?: boolean }) {
  return <div className={`brand-lockup ${compact ? "brand-compact" : ""}`}><span className="brand-symbol"><BrandMark /></span><div><span className="brand-name">aster<span className="brand-period">.</span></span>{!compact && <span className="brand-caption">A clearer kind of support</span>}</div></div>
}
export function Aperture({ className = "" }: { className?: string }) {
  return <div className={`aperture ${className}`} aria-hidden="true"><div className="aperture-haze" /><svg className="aperture-rings" viewBox="0 0 240 180" fill="none"><ellipse className="aperture-ring ring-one" cx="120" cy="90" rx="102" ry="48" /><ellipse className="aperture-ring ring-two" cx="120" cy="90" rx="102" ry="48" /><ellipse className="aperture-ring ring-three" cx="120" cy="90" rx="102" ry="48" /><circle cx="218" cy="84" r="3.5" fill="var(--accent)" /></svg><div className="aperture-core"><BrandMark /></div></div>
}
