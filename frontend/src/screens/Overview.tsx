import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import {
  fetchAnalytics,
  fetchBuilds,
  fetchCommits,
  fetchPullRequests,
  fetchRepos,
  fetchSettings,
  fetchWorkItems,
  type WorkItem,
} from "../api";
import { Bars, Card, Donut, H1, Pill, Sparkline, relTime, type Seg } from "../components/ui";
import { stateChip, typeDot } from "../lib/tokens";

/** Map a numeric series to polyline points in a 100×28 viewBox. */
function trendPoints(series: number[]): string {
  if (series.length < 2) return "0,14 100,14";
  const min = Math.min(...series);
  const max = Math.max(...series);
  const span = max - min || 1;
  const n = series.length;
  return series
    .map((v, i) => `${((i / (n - 1)) * 100).toFixed(1)},${(24 - ((v - min) / span) * 20).toFixed(1)}`)
    .join(" ");
}

const RANGES = ["24h", "7d", "30d"] as const;
type Range = (typeof RANGES)[number];

const lc = (s: string) => (s ?? "").toLowerCase();
const isDone = (s: string) => ["done", "closed", "completed"].includes(lc(s));
const isActive = (s: string) => ["active", "doing", "committed", "in progress"].includes(lc(s));
const isResolved = (s: string) => lc(s) === "resolved";
const isClosedish = (s: string) => isDone(s) || lc(s) === "removed";

export default function Overview({ project }: { project: string }) {
  const [range, setRange] = useState<Range>("7d");
  const rangeTouched = useRef(false);

  // apply the user's default_range setting until they pick one themselves
  const settings = useQuery({ queryKey: ["settings"], queryFn: fetchSettings, staleTime: 60_000 });
  const preferred = settings.data?.settings?.default_range as Range | undefined;
  useEffect(() => {
    if (!rangeTouched.current && preferred && RANGES.includes(preferred)) setRange(preferred);
  }, [preferred]);

  const analytics = useQuery({
    queryKey: ["analytics", project, range],
    queryFn: () => fetchAnalytics(project, range),
  });
  const wi = useQuery({ queryKey: ["workitems", project], queryFn: () => fetchWorkItems(project) });
  const prs = useQuery({ queryKey: ["prs", project, "active"], queryFn: () => fetchPullRequests(project, "active") });
  const builds = useQuery({ queryKey: ["builds", project], queryFn: () => fetchBuilds(project) });
  const repos = useQuery({ queryKey: ["repos", project], queryFn: () => fetchRepos(project) });
  const firstRepo = repos.data?.value[0]?.id ?? null;
  const commits = useQuery({
    queryKey: ["commits", project, firstRepo],
    queryFn: () => fetchCommits(project, firstRepo!),
    enabled: !!firstRepo,
  });

  const items = wi.data?.value ?? [];
  const activePrs = prs.data?.value.length ?? null;

  const buildList = builds.data?.value ?? [];
  const completed = buildList.filter((b) => b.status === "completed");
  const succeeded = completed.filter((b) => b.result === "succeeded").length;
  const successRate = completed.length ? Math.round((succeeded / completed.length) * 100) : null;

  // Prefer server-side OData aggregates (StateCategory); fall back to a client-side
  // rollup of the fetched items when Analytics is unavailable.
  const a = analytics.data;
  const aOk = !!a && a.available && a.total > 0;

  const openItems = aOk ? a!.open : items.filter((i) => !isClosedish(i.state)).length;

  let done: number, active: number, resolved: number, other: number, donutTotal: number;
  if (aOk) {
    done = a!.byCategory["Completed"] ?? 0;
    active = a!.byCategory["InProgress"] ?? 0;
    resolved = a!.byCategory["Resolved"] ?? 0;
    other = a!.total - done - active - resolved;
    donutTotal = a!.total;
  } else {
    done = items.filter((i) => isDone(i.state)).length;
    active = items.filter((i) => isActive(i.state)).length;
    resolved = items.filter((i) => isResolved(i.state)).length;
    other = items.length - done - active - resolved;
    donutTotal = items.length;
  }
  const segments: Seg[] = [
    { value: done, color: "var(--ok)" },
    { value: active, color: "var(--info)" },
    { value: other, color: "var(--faint)" },
    { value: resolved, color: "var(--purple)" },
  ];

  const openSpark =
    a && a.trend.length > 1
      ? trendPoints(a.trend.map((t) => t.count))
      : "0,20 14,16 28,17 42,11 56,13 70,7 84,9 100,5";

  const recent = items.slice(0, 6);

  return (
    <div>
      <div className="mb-[18px] flex items-end justify-between">
        <div>
          <H1>Overview</H1>
          <p className="m-0 mt-[5px] text-[12.5px] text-muted">
            {project} · synced just now · {repos.data?.value.length ?? "—"} repos
          </p>
        </div>
        <div className="flex overflow-hidden rounded-[8px] border border-border bg-surface">
          {RANGES.map((r, i) => {
            const on = range === r;
            return (
              <span
                key={r}
                onClick={() => {
                  rangeTouched.current = true;
                  setRange(r);
                }}
                className={`cursor-pointer px-[13px] py-[7px] text-[12px] ${i === 1 ? "border-x border-border" : ""} ${
                  on ? "bg-bg font-semibold text-text" : "font-medium text-muted"
                }`}
              >
                {r}
              </span>
            );
          })}
        </div>
      </div>

      {/* KPI row */}
      <div className="mb-4 grid grid-cols-4 gap-[14px]">
        <KpiCard label="Open work items" value={analytics.isLoading && wi.isLoading ? "…" : String(openItems)} spark={openSpark} color="var(--accent)" context={aOk ? `${donutTotal} total · ${range}` : "in this project"} />
        <KpiCard label="Active PRs" value={activePrs === null ? "…" : String(activePrs)} spark="0,8 14,10 28,6 42,12 56,11 70,16 84,14 100,18" color="var(--info)" context="open for review" />
        <KpiCard label="Pipeline success" value={successRate === null ? "—" : String(successRate)} suffix={successRate === null ? "" : "%"} spark="0,18 14,20 28,14 42,15 56,9 70,11 84,6 100,4" color="var(--ok)" context={`last ${completed.length} runs`} />
        <KpiCard label="Commits" value={commits.isLoading ? "…" : String(commits.data?.value.length ?? "—")} spark="0,22 14,18 28,20 42,12 56,14 70,8 84,10 100,4" color="var(--purple)" context={`recent in ${repos.data?.value[0]?.name ?? "repo"}`} />
      </div>

      {/* charts */}
      <div className="mb-4 grid grid-cols-2 gap-[14px]">
        <Card className="p-[16px_18px]">
          <div className="mb-[14px] flex items-center justify-between">
            <div className="text-[13px] font-semibold text-text">Pipeline runs · last 14</div>
            <div className="flex gap-[12px] text-[10.5px] text-muted">
              <Legend color="var(--c-green)">passed</Legend>
              <Legend color="var(--c-amber)">partial</Legend>
              <Legend color="var(--c-red)">failed</Legend>
            </div>
          </div>
          <Bars bars={barsFromBuilds(buildList)} />
          <div className="mt-[10px] flex justify-between border-t border-border-2 pt-[10px] text-[11px] text-muted">
            <span>
              passed <span className="font-mono font-semibold text-text">{succeeded}</span> / {completed.length}
            </span>
            <span>{buildList.length} runs</span>
          </div>
        </Card>

        <Card className="p-[16px_18px]">
          <div className="mb-2 text-[13px] font-semibold text-text">Work items by state</div>
          <div className="flex items-center gap-[20px]">
            <Donut segments={segments} total={donutTotal} />
            <div className="flex flex-1 flex-col gap-[9px]">
              <LegendRow color="var(--ok)" label="Done / Closed" value={done} />
              <LegendRow color="var(--info)" label="Active / Doing" value={active} />
              <LegendRow color="var(--faint)" label="New / Other" value={other} />
              <LegendRow color="var(--purple)" label="Resolved" value={resolved} />
            </div>
          </div>
        </Card>
      </div>

      {/* recent work items */}
      <Card className="overflow-hidden">
        <div className="border-b border-border-2 px-[18px] py-[13px] text-[13px] font-semibold text-text">
          Recent work items
        </div>
        <table className="w-full border-collapse text-[12.5px]">
          <thead>
            <tr className="text-[10.5px] uppercase tracking-[0.5px] text-faint">
              <th className="px-[18px] py-[9px] text-left font-semibold">ID</th>
              <th className="px-[8px] py-[9px] text-left font-semibold">Type</th>
              <th className="px-[8px] py-[9px] text-left font-semibold">Title</th>
              <th className="px-[8px] py-[9px] text-left font-semibold">State</th>
              <th className="px-[8px] py-[9px] text-left font-semibold">Assignee</th>
              <th className="px-[18px] py-[9px] text-right font-semibold">Updated</th>
            </tr>
          </thead>
          <tbody>
            {recent.map((wi) => (
              <RecentRow key={wi.id} wi={wi} />
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

function KpiCard({
  label,
  value,
  suffix = "",
  spark,
  color,
  context,
}: {
  label: string;
  value: string;
  suffix?: string;
  spark: string;
  color: string;
  context: string;
}) {
  return (
    <Card className="p-[14px_16px]">
      <div className="text-[11.5px] font-medium text-muted">{label}</div>
      <div className="mt-2 flex items-end justify-between">
        <div className="font-mono text-[28px] font-semibold leading-none text-text">
          {value}
          {suffix && <span className="text-[16px] text-muted">{suffix}</span>}
        </div>
        <Sparkline points={spark} color={color} />
      </div>
      <div className="mt-2 text-[11px] text-faint">{context}</div>
    </Card>
  );
}

function Legend({ color, children }: { color: string; children: React.ReactNode }) {
  return (
    <span className="flex items-center gap-[5px]">
      <span className="h-2 w-2 rounded-[2px]" style={{ background: color }} />
      {children}
    </span>
  );
}

function LegendRow({ color, label, value }: { color: string; label: string; value: number }) {
  return (
    <div className="flex items-center justify-between text-[12px]">
      <span className="flex items-center gap-2 text-text-2">
        <span className="h-[9px] w-[9px] rounded-[2px]" style={{ background: color }} />
        {label}
      </span>
      <span className="font-mono font-semibold text-text">{value}</span>
    </div>
  );
}

function RecentRow({ wi }: { wi: WorkItem }) {
  return (
    <tr className="border-t border-line hover:bg-hover">
      <td className="px-[18px] py-[9px] font-mono text-faint">#{wi.id}</td>
      <td className="px-[8px] py-[9px]">
        <span className="inline-flex items-center gap-[6px] text-text-2">
          <span className={`h-2 w-2 rounded-[2px] ${typeDot(wi.type)}`} />
          {wi.type}
        </span>
      </td>
      <td className="px-[8px] py-[9px] font-medium text-text">{wi.title}</td>
      <td className="px-[8px] py-[9px]">
        <Pill className={stateChip(wi.state)}>{wi.state}</Pill>
      </td>
      <td className="px-[8px] py-[9px]">
        <span className={wi.assignedTo ? "text-text-3" : "text-faint"}>{wi.assignedTo ?? "Unassigned"}</span>
      </td>
      <td className="px-[18px] py-[9px] text-right font-mono text-faint">{relTime(wi.changedDate)}</td>
    </tr>
  );
}

function barsFromBuilds(builds: { status: string | null; result: string | null; startTime?: string; finishTime?: string }[]) {
  const last = builds.slice(0, 14);
  const durs = last.map((b) =>
    b.startTime && b.finishTime ? (new Date(b.finishTime).getTime() - new Date(b.startTime).getTime()) / 1000 : 0,
  );
  const max = Math.max(...durs, 1);
  return last.map((b, i) => {
    let color = "var(--c-green)";
    if (b.status && b.status !== "completed") color = "var(--c-amber)";
    else if (b.result === "failed") color = "var(--c-red)";
    else if (b.result === "partiallySucceeded") color = "var(--c-amber)";
    const h = durs[i] > 0 ? Math.max(40, Math.min(96, (durs[i] / max) * 96)) : 70;
    return { h, color };
  });
}
