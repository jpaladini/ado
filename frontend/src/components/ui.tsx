import type { ReactNode } from "react";

// ---- containers -------------------------------------------------------------

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-[10px] border border-border bg-surface ${className}`}>{children}</div>
  );
}

export function H1({ children }: { children: ReactNode }) {
  return (
    <h1 className="m-0 text-[21px] font-bold tracking-[-0.3px] text-text">{children}</h1>
  );
}

export function SectionLabel({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`text-[10px] font-semibold uppercase tracking-[0.8px] text-faint ${className}`}>
      {children}
    </div>
  );
}

// ---- pill / chip ------------------------------------------------------------

export function Pill({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <span className={`inline-block rounded-[20px] px-[9px] py-[3px] text-[11px] font-semibold ${className}`}>
      {children}
    </span>
  );
}

// ---- async states -----------------------------------------------------------

export function Loading({ label = "Loading…" }: { label?: string }) {
  return <div className="p-9 text-center text-[13px] text-faint">{label}</div>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="p-9 text-center text-[13px] text-faint">{children}</div>;
}

export function ErrorMsg({ error }: { error: unknown }) {
  const msg = error instanceof Error ? error.message : String(error);
  return (
    <div className="rounded-[10px] border border-danger-bg bg-danger-bg px-4 py-3 text-[13px] text-danger">
      {msg}
    </div>
  );
}

// ---- charts -----------------------------------------------------------------

/** Decorative sparkline. `points` are in a 100×28 viewBox; `color` is a CSS var. */
export function Sparkline({ points, color }: { points: string; color: string }) {
  return (
    <svg width="76" height="28" viewBox="0 0 100 28" preserveAspectRatio="none">
      <polyline points={points} fill="none" stroke={color} strokeWidth="2.5" />
    </svg>
  );
}

export interface Seg {
  value: number;
  color: string; // CSS var
}

/** Donut over r=46, stroke-width 15 (118×118 viewBox), rotated -90°. */
export function Donut({ segments, total, centerLabel }: { segments: Seg[]; total: number; centerLabel?: string }) {
  const C = 2 * Math.PI * 46;
  let offset = 0;
  const arcs = segments.map((s, i) => {
    const len = total > 0 ? (s.value / total) * C : 0;
    const el = (
      <circle
        key={i}
        cx="59"
        cy="59"
        r="46"
        fill="none"
        stroke={s.color}
        strokeWidth="15"
        strokeDasharray={`${len} ${C - len}`}
        strokeDashoffset={-offset}
      />
    );
    offset += len;
    return el;
  });
  return (
    <svg width="118" height="118" viewBox="0 0 118 118">
      <g transform="rotate(-90 59 59)">
        <circle cx="59" cy="59" r="46" fill="none" stroke="var(--donut-track)" strokeWidth="15" />
        {arcs}
      </g>
      <text x="59" y="55" textAnchor="middle" fontFamily="'IBM Plex Mono',monospace" fontSize="22" fontWeight="600" fill="var(--text)">
        {centerLabel ?? total}
      </text>
      <text x="59" y="71" textAnchor="middle" fontFamily="'IBM Plex Sans',sans-serif" fontSize="9.5" fill="var(--muted)">
        total
      </text>
    </svg>
  );
}

/** Vertical bar chart; each bar is a height % (0..100) + CSS var color. */
export function Bars({ bars }: { bars: { h: number; color: string }[] }) {
  return (
    <div className="flex h-[104px] items-end gap-[7px]">
      {bars.map((b, i) => (
        <div
          key={i}
          className="flex-1 rounded-t-[3px]"
          style={{ height: `${b.h}%`, background: b.color }}
        />
      ))}
    </div>
  );
}

// ---- format -----------------------------------------------------------------

export function relTime(iso?: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60) return "now";
  const units: [number, string][] = [
    [60, "m"],
    [3600, "h"],
    [86400, "d"],
    [2592000, "mo"],
  ];
  for (let i = units.length - 1; i >= 0; i--) {
    const [secs, label] = units[i];
    if (diff >= secs) return `${Math.floor(diff / secs)}${label}`;
  }
  return `${Math.floor(diff)}s`;
}
