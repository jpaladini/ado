import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  fetchReports,
  fetchWorkItemTypes,
  type OpenItem,
  type ReportsPayload,
} from "../api";
import { Card, Empty, ErrorMsg, H1, Loading } from "../components/ui";
import PlotFigure from "../components/PlotFigure";
import ReportBuilder from "./ReportBuilder";
import { stateChip } from "../lib/tokens";

const RANGES = ["7d", "14d", "30d", "90d"] as const;

// StateCategory stacking order (bottom → top) and token color per category.
const CAT_ORDER = ["Proposed", "InProgress", "Resolved"];

export default function Reports({ project }: { project: string }) {
  const [range, setRange] = useState<string>("30d");
  const [types, setTypes] = useState<Set<string>>(new Set());
  const [assignees, setAssignees] = useState<Set<string>>(new Set());

  const typesQ = useQuery({
    queryKey: ["witypes", project],
    queryFn: () => fetchWorkItemTypes(project),
    staleTime: 5 * 60_000,
  });

  const q = useQuery({
    queryKey: ["reports", project, range, [...types].sort().join("|"), [...assignees].sort().join("|")],
    queryFn: () => fetchReports(project, range, [...types], [...assignees]),
  });
  const d = q.data;

  // assignee filter options: whoever appears in the current data, plus selections
  const assigneeOptions = useMemo(() => {
    const seen = new Set<string>(assignees);
    for (const i of d?.openItems ?? []) seen.add(i.assignee ?? "Unassigned");
    return [...seen].sort();
  }, [d, assignees]);

  const toggle = (set: Set<string>, setter: (s: Set<string>) => void, v: string) => {
    const next = new Set(set);
    if (next.has(v)) next.delete(v);
    else next.add(v);
    setter(next);
  };

  return (
    <div>
      <div className="flex items-baseline justify-between">
        <H1>Reports</H1>
        <span className="flex items-center gap-[12px] text-[11px] text-faint">
          All durations in <span className="font-semibold text-text-3">business days</span> (Mon–Fri)
          {(["xlsx", "pdf"] as const).map((fmt) => (
            <a
              key={fmt}
              href={`/api/projects/${encodeURIComponent(project)}/reports/export?range=${range}&format=${fmt}${
                types.size ? `&types=${encodeURIComponent([...types].join(","))}` : ""
              }${assignees.size ? `&assignees=${encodeURIComponent([...assignees].join(","))}` : ""}`}
              download
              className="rounded-[7px] border border-border bg-surface px-[10px] py-[4px] text-[11.5px] font-medium text-text-3 hover:border-faint"
            >
              Export .{fmt}
            </a>
          ))}
        </span>
      </div>

      {/* -------- filter bar -------- */}
      <div className="mb-[16px] mt-4 flex flex-wrap items-center gap-x-[14px] gap-y-[8px]">
        <div className="flex gap-[5px]">
          {RANGES.map((r) => (
            <FilterChip key={r} on={range === r} onClick={() => setRange(r)}>
              {r}
            </FilterChip>
          ))}
        </div>
        <span className="h-[18px] w-px bg-border" />
        <div className="flex flex-wrap gap-[5px]">
          {(typesQ.data?.value ?? []).map((t) => (
            <FilterChip key={t.name} on={types.has(t.name)} onClick={() => toggle(types, setTypes, t.name)}>
              {t.name}
            </FilterChip>
          ))}
        </div>
        <span className="h-[18px] w-px bg-border" />
        <div className="flex flex-wrap gap-[5px]">
          {assigneeOptions.map((a) => (
            <FilterChip key={a} on={assignees.has(a)} onClick={() => toggle(assignees, setAssignees, a)}>
              {a}
            </FilterChip>
          ))}
        </div>
      </div>

      {q.isLoading && <Loading label="Aggregating…" />}
      {q.isError && <ErrorMsg error={q.error} />}

      {d && (
        <>
          {/* -------- KPI strip -------- */}
          <div className="grid grid-cols-5 gap-[12px]">
            <Kpi label={`Completed · ${range}`} value={d.kpis.throughput} />
            <Kpi
              label="Net flow"
              value={(d.kpis.netFlow > 0 ? "+" : "") + d.kpis.netFlow}
              hint={d.kpis.netFlow > 0 ? "backlog growing" : d.kpis.netFlow < 0 ? "backlog burning" : "steady"}
              tone={d.kpis.netFlow > 0 ? "warn" : "ok"}
            />
            <Kpi label="WIP now" value={d.kpis.wip} />
            <Kpi label="Cycle p50" value={fmtDays(d.kpis.cycleP50)} hint="business days" />
            <Kpi label="Cycle p85" value={fmtDays(d.kpis.cycleP85)} hint="business days" />
          </div>

          {/* -------- charts -------- */}
          <div className="mt-[14px] grid grid-cols-2 gap-[14px]">
            <ChartCard title="Created vs completed" sub="per day">
              <CreatedVsCompleted d={d} />
            </ChartCard>
            <ChartCard title="Cumulative flow" sub="open items by state category">
              <Cfd d={d} />
            </ChartCard>
            <ChartCard title="Cycle time" sub="each dot is a completed item · p50/p85 bands">
              <CycleScatter d={d} />
            </ChartCard>
            <ChartCard title="Aging WIP" sub="open items vs the cycle-time bands — top-right is the danger zone">
              <AgingWip d={d} />
            </ChartCard>
            <ChartCard title="Workload" sub="open items by assignee and state category">
              <Workload d={d} />
            </ChartCard>
            <ChartCard title="Needs attention" sub="oldest open items">
              <StaleList items={d.openItems} />
            </ChartCard>
          </div>
        </>
      )}

      {/* -------- 4E: self-serve report builder (UC metric view, batch plane) -------- */}
      <ReportBuilder />
    </div>
  );
}

// ---- small pieces --------------------------------------------------------------

function FilterChip({ on, onClick, children }: { on: boolean; onClick: () => void; children: React.ReactNode }) {
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

function Kpi({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: number | string;
  hint?: string;
  tone?: "ok" | "warn";
}) {
  return (
    <Card className="p-[12px_14px]">
      <div className="text-[10.5px] font-semibold uppercase tracking-[0.5px] text-faint">{label}</div>
      <div
        className={`mt-[4px] font-mono text-[24px] font-semibold leading-none ${
          tone === "warn" ? "text-warn" : tone === "ok" ? "text-ok" : "text-text"
        }`}
      >
        {value}
      </div>
      {hint && <div className="mt-[4px] text-[10.5px] text-faint">{hint}</div>}
    </Card>
  );
}

function ChartCard({ title, sub, children }: { title: string; sub: string; children: React.ReactNode }) {
  return (
    <Card className="min-w-0 p-[14px_16px]">
      <div className="mb-[10px] flex items-baseline gap-[8px]">
        <span className="text-[13px] font-semibold text-text">{title}</span>
        <span className="text-[11px] text-faint">{sub}</span>
      </div>
      {children}
    </Card>
  );
}

function fmtDays(v: number): string {
  return Number.isInteger(v) ? `${v}d` : `${v.toFixed(1)}d`;
}

function skToDate(sk: number): Date {
  const s = String(sk);
  return new Date(`${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}T00:00:00Z`);
}

const FONT = "'IBM Plex Sans', system-ui, sans-serif";

// ---- charts ----------------------------------------------------------------------

function CreatedVsCompleted({ d }: { d: ReportsPayload }) {
  const completed = d.completedPerDay.map((r) => ({ date: skToDate(r.dateSK), count: r.count }));
  const created = d.createdPerDay.map((r) => ({ date: skToDate(r.dateSK), count: r.count }));
  if (!completed.length && !created.length)
    return <Empty>No items created or completed in this window.</Empty>;
  return (
    <PlotFigure
      deps={[d]}
      build={(Plot, c, width) =>
        Plot.plot({
          width,
          height: 220,
          style: { fontFamily: FONT, fontSize: "11px", background: "transparent" },
          x: { type: "utc", label: null, tickFormat: "%b %d" },
          y: { label: "items / day", grid: true, tickFormat: (v: number) => (Number.isInteger(v) ? String(v) : "") },
          color: { domain: ["completed", "created"], range: [c.ok, c.info], legend: true },
          marks: [
            // completed = green bars; created = blue step line — independent flows,
            // never stacked (stacking two flows overstates the busy days)
            Plot.rectY(completed, {
              x: "date",
              y: "count",
              interval: "day",
              fill: () => "completed",
              insetLeft: 1,
              insetRight: 1,
              opacity: 0.85,
              tip: true,
            }),
            Plot.lineY(created, {
              x: "date",
              y: "count",
              curve: "step-after",
              stroke: () => "created",
              strokeWidth: 2,
            }),
            Plot.dot(created, { x: "date", y: "count", r: 3, fill: () => "created", tip: true }),
            Plot.ruleY([0], { stroke: c.line }),
          ],
        })
      }
    />
  );
}

function Cfd({ d }: { d: ReportsPayload }) {
  const rows = d.cfd
    .filter((r) => r.category !== "Completed")
    .map((r) => ({ ...r, date: new Date(`${r.date}T00:00:00Z`) }));
  if (!rows.length) return <Empty>No snapshot history yet.</Empty>;
  return (
    <PlotFigure
      deps={[d]}
      build={(Plot, c, width) =>
        Plot.plot({
          width,
          height: 220,
          style: { fontFamily: FONT, fontSize: "11px", background: "transparent" },
          x: { type: "utc", label: null, tickFormat: "%b %d" },
          y: { label: "open items", grid: true },
          color: { domain: CAT_ORDER, range: [c.faint, c.info, c.purple], legend: true },
          marks: [
            Plot.areaY(rows, {
              x: "date",
              y: "count",
              fill: "category",
              order: CAT_ORDER,
              curve: "step-after",
              opacity: 0.75,
              tip: true,
            }),
            Plot.ruleY([0], { stroke: c.line }),
          ],
        })
      }
    />
  );
}

function CycleScatter({ d }: { d: ReportsPayload }) {
  const rows = d.cycleItems.map((i) => ({ ...i, closed: new Date(`${i.closedDate}T00:00:00Z`) }));
  if (!rows.length) return <Empty>Nothing completed in this window yet.</Empty>;
  const { cycleP50, cycleP85 } = d.kpis;
  return (
    <PlotFigure
      deps={[d]}
      build={(Plot, c, width) =>
        Plot.plot({
          width,
          height: 220,
          style: { fontFamily: FONT, fontSize: "11px", background: "transparent" },
          x: { type: "utc", label: null, tickFormat: "%b %d" },
          y: { label: "cycle time (business days)", grid: true, zero: true },
          marks: [
            Plot.ruleY([cycleP85], { stroke: c.warn, strokeDasharray: "4 3" }),
            Plot.text([{ y: cycleP85 }], { y: "y", x: rows[0].closed, text: () => `p85 ${fmtDays(cycleP85)}`, dy: -7, dx: 4, fill: c.warn, textAnchor: "start", fontSize: 10 }),
            Plot.ruleY([cycleP50], { stroke: c.ok, strokeDasharray: "4 3" }),
            Plot.text([{ y: cycleP50 }], { y: "y", x: rows[0].closed, text: () => `p50 ${fmtDays(cycleP50)}`, dy: -7, dx: 4, fill: c.ok, textAnchor: "start", fontSize: 10 }),
            Plot.dot(rows, {
              x: "closed",
              y: "cycleBdays",
              r: 5,
              fill: c.info,
              opacity: 0.75,
              stroke: "none",
              channels: { item: (i: (typeof rows)[number]) => `#${i.id} ${i.title}` },
              tip: { format: { item: true, x: false } },
            }),
          ],
        })
      }
    />
  );
}

function AgingWip({ d }: { d: ReportsPayload }) {
  const rows = d.openItems;
  if (!rows.length) return <Empty>No open items — enjoy it while it lasts.</Empty>;
  const { cycleP50, cycleP85 } = d.kpis;
  return (
    <PlotFigure
      deps={[d]}
      build={(Plot, c, width) =>
        Plot.plot({
          width,
          height: 220,
          style: { fontFamily: FONT, fontSize: "11px", background: "transparent" },
          x: { label: null, domain: [...new Set(rows.map((r) => r.state))] },
          y: { label: "age (business days)", grid: true, zero: true },
          marks: [
            ...(cycleP85 > 0
              ? [Plot.ruleY([cycleP85], { stroke: c.warn, strokeDasharray: "4 3" })]
              : []),
            ...(cycleP50 > 0 ? [Plot.ruleY([cycleP50], { stroke: c.ok, strokeDasharray: "4 3" })] : []),
            Plot.dot(rows, {
              x: "state",
              y: "ageBdays",
              r: 6,
              fill: (i: OpenItem) => (cycleP85 > 0 && i.ageBdays > cycleP85 ? c.danger : c.purple),
              opacity: 0.8,
              channels: { item: (i: OpenItem) => `#${i.id} ${i.title} — ${i.assignee ?? "unassigned"}` },
              tip: { format: { item: true, x: false } },
            }),
          ],
        })
      }
    />
  );
}

function Workload({ d }: { d: ReportsPayload }) {
  const grouped: Record<string, Record<string, number>> = {};
  for (const i of d.openItems) {
    const who = i.assignee ?? "Unassigned";
    (grouped[who] ??= {})[i.category] = (grouped[who][i.category] ?? 0) + 1;
  }
  const rows = Object.entries(grouped).flatMap(([assignee, cats]) =>
    Object.entries(cats).map(([category, count]) => ({ assignee, category, count })),
  );
  if (!rows.length) return <Empty>No open items.</Empty>;
  return (
    <PlotFigure
      deps={[d]}
      build={(Plot, c, width) =>
        Plot.plot({
          width,
          height: Math.max(140, Object.keys(grouped).length * 34 + 60),
          marginLeft: 110,
          style: { fontFamily: FONT, fontSize: "11px", background: "transparent" },
          x: { label: "open items", grid: true },
          y: { label: null },
          color: { domain: CAT_ORDER, range: [c.faint, c.info, c.purple], legend: true },
          marks: [
            Plot.barX(rows, {
              x: "count",
              y: "assignee",
              fill: "category",
              order: CAT_ORDER,
              tip: true,
              sort: { y: "-x" },
            }),
            Plot.ruleX([0], { stroke: c.line }),
          ],
        })
      }
    />
  );
}

function StaleList({ items }: { items: OpenItem[] }) {
  const oldest = [...items].sort((a, b) => b.ageBdays - a.ageBdays).slice(0, 6);
  if (!oldest.length) return <Empty>Nothing stale.</Empty>;
  return (
    <div>
      {oldest.map((i) => (
        <div key={i.id} className="flex items-center gap-[10px] border-t border-line py-[8px] first:border-t-0">
          <span className="font-mono text-[11.5px] text-faint">#{i.id}</span>
          <span className="min-w-0 flex-1 truncate text-[12.5px] text-text">{i.title}</span>
          <span className={`rounded-[7px] px-[8px] py-[2px] text-[10.5px] font-semibold ${stateChip(i.state)}`}>
            {i.state}
          </span>
          <span className="w-[90px] text-right text-[11.5px] text-text-3">{i.assignee ?? "—"}</span>
          <span
            className={`w-[52px] text-right font-mono text-[12px] font-semibold ${
              i.ageBdays >= 10 ? "text-danger" : i.ageBdays >= 5 ? "text-warn" : "text-text-3"
            }`}
          >
            {i.ageBdays}bd
          </span>
        </div>
      ))}
    </div>
  );
}
