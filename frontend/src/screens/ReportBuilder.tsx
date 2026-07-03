import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  deleteSavedReport,
  fetchBuilderMeta,
  fetchSavedReports,
  runBuilderReport,
  saveReport,
  type BuilderDefinition,
  type BuilderMeta,
  type BuilderResult,
  type SavedReport,
} from "../api";
import { Card, Empty, ErrorMsg, Loading } from "../components/ui";
import PlotFigure from "../components/PlotFigure";
import type { ChartColors } from "../lib/plot";

/** 4E report builder: dimensions × measures × chart type over the UC metric
 * view (workspace semantic layer). The data is the ingest job's Delta copy —
 * historical, refreshed on the job's schedule — unlike the near-live curated
 * widgets above it. */

const CHART_TYPES = ["auto", "bar", "line", "area", "table"] as const;

export default function ReportBuilder() {
  const qc = useQueryClient();
  const metaQ = useQuery({ queryKey: ["builder-meta"], queryFn: fetchBuilderMeta, staleTime: 5 * 60_000 });
  const savedQ = useQuery({ queryKey: ["saved-reports"], queryFn: fetchSavedReports });

  const [dims, setDims] = useState<string[]>([]);
  const [measures, setMeasures] = useState<string[]>(["items"]);
  const [chartType, setChartType] = useState<string>("auto");
  const [name, setName] = useState("");

  const meta = metaQ.data;

  // Series is either the 2nd dimension or the 2nd..nth measure — never both.
  const toggleDim = (d: string) => {
    setDims((cur) => {
      if (cur.includes(d)) return cur.filter((x) => x !== d);
      const next = [...cur, d].slice(-2);
      if (next.length === 2) setMeasures((m) => m.slice(0, 1));
      return next;
    });
  };
  const toggleMeasure = (m: string) => {
    setMeasures((cur) => {
      if (cur.includes(m)) return cur.length > 1 ? cur.filter((x) => x !== m) : cur;
      if (dims.length === 2) setDims((d) => d.slice(0, 1));
      return [...cur, m];
    });
  };

  const definition: BuilderDefinition = useMemo(
    () => ({ dimensions: dims, measures, chartType }),
    [dims, measures, chartType],
  );

  const run = useMutation({ mutationFn: () => runBuilderReport(definition) });
  const save = useMutation({
    mutationFn: () => saveReport(name.trim(), definition),
    onSuccess: () => {
      setName("");
      qc.invalidateQueries({ queryKey: ["saved-reports"] });
    },
  });
  const del = useMutation({
    mutationFn: (id: string) => deleteSavedReport(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["saved-reports"] }),
  });

  if (metaQ.isLoading) return null;
  if (!meta) return null;

  return (
    <div className="mt-[22px]">
      <div className="mb-[10px] flex items-baseline justify-between">
        <span className="text-[14px] font-semibold text-text">Report builder</span>
        <span className="text-[11px] text-faint">
          semantic layer <span className="font-mono">{meta.view?.split(".").pop()}</span> · batch data,
          refreshed by the ingest job — not live
        </span>
      </div>

      {!meta.available && (
        <Card className="p-[14px_16px]">
          <Empty>
            Report builder unavailable{meta.reason ? ` — ${meta.reason}` : ""}. The app needs
            CREATE TABLE on its app-state schema and SELECT on the analytics schema.
          </Empty>
        </Card>
      )}

      {meta.available && (
        <>
          <Card className="p-[14px_16px]">
            <div className="flex flex-wrap items-start gap-x-[18px] gap-y-[10px]">
              <FieldGroup label="Dimensions (max 2 — 2nd becomes the series)">
                {meta.dimensions.map((d) => (
                  <BuilderChip key={d.name} on={dims.includes(d.name)} onClick={() => toggleDim(d.name)}>
                    {d.label}
                  </BuilderChip>
                ))}
              </FieldGroup>
              <FieldGroup label="Measures (2nd+ becomes the series)">
                {meta.measures.map((m) => (
                  <BuilderChip key={m.name} on={measures.includes(m.name)} onClick={() => toggleMeasure(m.name)}>
                    {m.label}
                  </BuilderChip>
                ))}
              </FieldGroup>
              <FieldGroup label="Chart">
                {CHART_TYPES.map((t) => (
                  <BuilderChip key={t} on={chartType === t} onClick={() => setChartType(t)}>
                    {t}
                  </BuilderChip>
                ))}
              </FieldGroup>
            </div>

            <div className="mt-[12px] flex items-center gap-[8px] border-t border-line pt-[12px]">
              <button
                onClick={() => run.mutate()}
                disabled={run.isPending || !measures.length}
                className="rounded-[7px] bg-ink-bg px-[14px] py-[6px] text-[12px] font-semibold text-ink-fg disabled:opacity-50"
              >
                {run.isPending ? "Running…" : "Run"}
              </button>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Report name…"
                className="w-[220px] rounded-[7px] border border-border bg-surface px-[10px] py-[5px] text-[12px] text-text placeholder:text-faint"
              />
              <button
                onClick={() => save.mutate()}
                disabled={save.isPending || !name.trim() || !measures.length}
                className="rounded-[7px] border border-border px-[14px] py-[5px] text-[12px] font-medium text-text-3 hover:border-faint disabled:opacity-50"
              >
                Save
              </button>
              {save.isError && <span className="text-[11px] text-danger">{String((save.error as Error).message)}</span>}
            </div>

            <div className="mt-[12px]">
              {run.isError && <ErrorMsg error={run.error} />}
              {run.isPending && <Loading label="Querying the metric view…" />}
              {run.data && <BuilderChart meta={meta} def={definition} result={run.data} />}
              {!run.data && !run.isPending && !run.isError && (
                <Empty>Pick dimensions and measures, then Run.</Empty>
              )}
            </div>
          </Card>

          {/* -------- saved reports -------- */}
          {(savedQ.data?.value ?? []).length > 0 && (
            <div className="mt-[14px] grid grid-cols-2 gap-[14px]">
              {(savedQ.data?.value ?? []).map((r) => (
                <SavedReportCard key={r.id} report={r} meta={meta} onDelete={() => del.mutate(r.id)} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function FieldGroup({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-[6px] text-[10.5px] font-semibold uppercase tracking-[0.5px] text-faint">{label}</div>
      <div className="flex max-w-[420px] flex-wrap gap-[5px]">{children}</div>
    </div>
  );
}

function BuilderChip({ on, onClick, children }: { on: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={`rounded-[7px] border px-[10px] py-[4px] text-[11.5px] ${
        on
          ? "border-ink-bg bg-ink-bg font-semibold text-ink-fg"
          : "border-border bg-surface font-medium text-text-3 hover:border-faint"
      }`}
    >
      {children}
    </button>
  );
}

function SavedReportCard({
  report,
  meta,
  onDelete,
}: {
  report: SavedReport;
  meta: BuilderMeta;
  onDelete: () => void;
}) {
  const def = useMemo<BuilderDefinition | null>(() => {
    try {
      return JSON.parse(report.definition) as BuilderDefinition;
    } catch {
      return null;
    }
  }, [report.definition]);

  const q = useQuery({
    queryKey: ["builder-run", report.id, report.definition],
    queryFn: () => runBuilderReport(def!),
    enabled: !!def,
    staleTime: 60_000,
  });

  const label = (names: string[], fields: { name: string; label: string }[]) =>
    names.map((n) => fields.find((f) => f.name === n)?.label ?? n).join(", ");

  return (
    <Card className="min-w-0 p-[14px_16px]">
      <div className="mb-[10px] flex items-baseline gap-[8px]">
        <span className="text-[13px] font-semibold text-text">{report.name}</span>
        <span className="min-w-0 flex-1 truncate text-[11px] text-faint">
          {def ? `${label(def.dimensions, meta.dimensions) || "—"} × ${label(def.measures, meta.measures)}` : "invalid definition"}
        </span>
        <button
          onClick={onDelete}
          title="Delete report"
          className="text-[11px] font-medium text-faint hover:text-danger"
        >
          delete
        </button>
      </div>
      {!def && <Empty>Could not parse this report's definition.</Empty>}
      {def && q.isLoading && <Loading label="Querying…" />}
      {def && q.isError && <ErrorMsg error={q.error} />}
      {def && q.data && <BuilderChart meta={meta} def={def} result={q.data} />}
    </Card>
  );
}

// ---- generic chart over builder rows ---------------------------------------------

const FONT = "'IBM Plex Sans', system-ui, sans-serif";

function seriesPalette(c: ChartColors): string[] {
  return [c.info, c.ok, c.purple, c.warn, c.danger, c.accent, c.muted];
}

function fmtValue(v: number | null, format?: string): string {
  if (v === null || v === undefined) return "—";
  const s = Number.isInteger(v) ? String(v) : v.toFixed(1);
  return format === "days" ? `${s}d` : s;
}

function BuilderChart({
  meta,
  def,
  result,
}: {
  meta: BuilderMeta;
  def: BuilderDefinition;
  result: BuilderResult;
}) {
  const dimMeta = (n: string) => meta.dimensions.find((d) => d.name === n);
  const measureMeta = (n: string) => meta.measures.find((m) => m.name === n);
  const labelOf = (n: string) => dimMeta(n)?.label ?? measureMeta(n)?.label ?? n;

  const xDim = def.dimensions[0];
  const isDate = xDim ? dimMeta(xDim)?.kind === "date" : false;
  const chart =
    def.chartType && def.chartType !== "auto"
      ? def.chartType
      : !xDim
        ? "kpi"
        : isDate
          ? "line"
          : "bar";

  if (!result.rows.length) return <Empty>The query returned no rows.</Empty>;

  // -------- KPI tiles (no dimensions) --------
  if (!xDim || chart === "kpi") {
    const row = result.rows[0];
    return (
      <div className="flex flex-wrap gap-[12px]">
        {def.measures.map((m) => (
          <div key={m} className="min-w-[140px] rounded-[9px] border border-line p-[10px_14px]">
            <div className="text-[10.5px] font-semibold uppercase tracking-[0.5px] text-faint">{labelOf(m)}</div>
            <div className="mt-[4px] font-mono text-[22px] font-semibold text-text">
              {fmtValue(row[m] as number | null, measureMeta(m)?.format)}
            </div>
          </div>
        ))}
      </div>
    );
  }

  // -------- table --------
  if (chart === "table") {
    return (
      <div className="max-h-[320px] overflow-auto">
        <table className="w-full text-[12px]">
          <thead>
            <tr className="text-left text-[10.5px] font-semibold uppercase tracking-[0.5px] text-faint">
              {result.columns.map((c) => (
                <th key={c} className={`py-[6px] pr-[12px] ${measureMeta(c) ? "text-right" : ""}`}>
                  {labelOf(c)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {result.rows.map((r, i) => (
              <tr key={i} className="border-t border-line">
                {result.columns.map((c) => (
                  <td key={c} className={`py-[6px] pr-[12px] ${measureMeta(c) ? "text-right font-mono" : "text-text"}`}>
                    {measureMeta(c) ? fmtValue(r[c] as number | null, measureMeta(c)?.format) : String(r[c] ?? "—")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  // -------- long-format reshape: series = 2nd dimension XOR extra measures --------
  const seriesDim = def.dimensions[1];
  const firstMeasure = def.measures[0];
  type Row = { x: string | Date; series: string; value: number };
  const rows: Row[] = [];
  for (const r of result.rows) {
    const rawX = r[xDim];
    if (rawX === null || rawX === undefined) continue;
    const x = isDate ? new Date(`${rawX}T00:00:00Z`) : String(rawX);
    if (seriesDim) {
      const v = r[firstMeasure];
      if (v !== null && v !== undefined)
        rows.push({ x, series: String(r[seriesDim] ?? "—"), value: v as number });
    } else {
      for (const m of def.measures) {
        const v = r[m];
        if (v !== null && v !== undefined) rows.push({ x, series: labelOf(m), value: v as number });
      }
    }
  }
  if (!rows.length) return <Empty>No plottable values (all nulls).</Empty>;

  const seriesNames = [...new Set(rows.map((r) => r.series))];
  const valueLabel = seriesDim || def.measures.length > 1 ? "value" : labelOf(firstMeasure);

  // -------- category axis → horizontal bars --------
  if (!isDate) {
    const categories = [...new Set(rows.map((r) => String(r.x)))];
    return (
      <PlotFigure
        deps={[result, chart]}
        build={(Plot, c, width) =>
          Plot.plot({
            width,
            height: Math.max(140, categories.length * 30 + 60),
            marginLeft: 120,
            style: { fontFamily: FONT, fontSize: "11px", background: "transparent" },
            x: { label: valueLabel, grid: true },
            y: { label: null, domain: categories },
            color:
              seriesNames.length > 1
                ? { domain: seriesNames, range: seriesPalette(c), legend: true }
                : undefined,
            marks: [
              Plot.barX(rows, {
                x: "value",
                y: "x",
                fill: seriesNames.length > 1 ? "series" : c.info,
                tip: true,
              }),
              Plot.ruleX([0], { stroke: c.line }),
            ],
          })
        }
      />
    );
  }

  // -------- date axis → line / area / bar over time --------
  return (
    <PlotFigure
      deps={[result, chart]}
      build={(Plot, c, width) =>
        Plot.plot({
          width,
          height: 240,
          style: { fontFamily: FONT, fontSize: "11px", background: "transparent" },
          x: { type: "utc", label: null },
          y: { label: valueLabel, grid: true, zero: true },
          color:
            seriesNames.length > 1
              ? { domain: seriesNames, range: seriesPalette(c), legend: true }
              : undefined,
          marks: [
            ...(chart === "area"
              ? [
                  Plot.areaY(rows, {
                    x: "x",
                    y: "value",
                    fill: seriesNames.length > 1 ? "series" : c.info,
                    curve: "step-after",
                    opacity: 0.75,
                    tip: true,
                  }),
                ]
              : chart === "bar"
                ? [
                    Plot.rectY(rows, {
                      x: "x",
                      y: "value",
                      fill: seriesNames.length > 1 ? "series" : c.info,
                      interval: intervalFor(xDim),
                      insetLeft: 1,
                      insetRight: 1,
                      opacity: 0.85,
                      tip: true,
                    }),
                  ]
                : [
                    Plot.lineY(rows, {
                      x: "x",
                      y: "value",
                      stroke: seriesNames.length > 1 ? "series" : c.info,
                      curve: "step-after",
                      strokeWidth: 2,
                    }),
                    Plot.dot(rows, {
                      x: "x",
                      y: "value",
                      r: 3,
                      fill: seriesNames.length > 1 ? "series" : c.info,
                      tip: true,
                    }),
                  ]),
            Plot.ruleY([0], { stroke: c.line }),
          ],
        })
      }
    />
  );
}

function intervalFor(dim: string): "day" | "week" | "month" {
  if (dim.endsWith("_month")) return "month";
  if (dim.endsWith("_week")) return "week";
  return "day";
}
