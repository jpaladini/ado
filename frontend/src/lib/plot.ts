// Lazily-loaded Observable Plot (the d3 team's successor to hand-rolled d3).
// Same pattern as lib/highlight.ts: the chart library lives in its own Vite
// chunk and only loads when the Reports tab first renders a figure.

export type PlotModule = typeof import("@observablehq/plot");

let cached: Promise<PlotModule> | null = null;

export function loadPlot(): Promise<PlotModule> {
  cached ??= import("@observablehq/plot");
  return cached;
}

/** Chart palette resolved from the design tokens at render time — charts pick
 * up light/dark automatically because the CSS vars flip with the theme. */
export interface ChartColors {
  text: string;
  muted: string;
  faint: string;
  line: string;
  info: string;
  ok: string;
  warn: string;
  danger: string;
  purple: string;
  accent: string;
}

export function chartColors(): ChartColors {
  const css = getComputedStyle(document.documentElement);
  const v = (n: string) => css.getPropertyValue(n).trim() || "#888";
  return {
    text: v("--text"),
    muted: v("--muted"),
    faint: v("--faint"),
    line: v("--line"),
    info: v("--info"),
    ok: v("--ok"),
    warn: v("--warn"),
    danger: v("--danger"),
    purple: v("--purple"),
    accent: v("--accent"),
  };
}
