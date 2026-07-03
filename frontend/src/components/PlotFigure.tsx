import { useEffect, useRef, useState } from "react";
import { chartColors, loadPlot, type ChartColors, type PlotModule } from "../lib/plot";

/** Host for an Observable Plot figure. `build` receives the Plot module, the
 * token-resolved palette, and the measured container width, and returns a DOM
 * node (or null for "nothing to draw"). Re-renders on deps, container resize,
 * and theme flips (the `dark` class on <html>). */
export default function PlotFigure({
  build,
  deps,
  minHeight = 200,
}: {
  build: (Plot: PlotModule, colors: ChartColors, width: number) => Element | null;
  deps: unknown[];
  minHeight?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [tick, setTick] = useState(0);

  // theme flips and container resizes both invalidate the rendered SVG
  useEffect(() => {
    const bump = () => setTick((t) => t + 1);
    const mo = new MutationObserver(bump);
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    const ro = new ResizeObserver(bump);
    if (ref.current) ro.observe(ref.current);
    return () => {
      mo.disconnect();
      ro.disconnect();
    };
  }, []);

  useEffect(() => {
    let alive = true;
    loadPlot().then((Plot) => {
      if (!alive || !ref.current) return;
      const width = ref.current.clientWidth || 480;
      const node = build(Plot, chartColors(), width);
      ref.current.replaceChildren(...(node ? [node] : []));
    });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  return <div ref={ref} style={{ minHeight }} className="w-full" />;
}
