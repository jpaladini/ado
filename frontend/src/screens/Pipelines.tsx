import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  fetchBuildLog,
  fetchBuilds,
  fetchBuildTimeline,
  type Build,
  type TimelineRecord,
} from "../api";
import { Card, Empty, ErrorMsg, H1, Loading, Pill, relTime } from "../components/ui";
import { buildChip, buildDot } from "../lib/tokens";

function label(b: Build): string {
  if (b.status && b.status !== "completed") return b.status === "inProgress" ? "running" : b.status;
  if (b.result === "partiallySucceeded") return "partial";
  return b.result ?? "—";
}

function durationSec(start?: string, finish?: string): number | null {
  if (!start || !finish) return null;
  const d = (new Date(finish).getTime() - new Date(start).getTime()) / 1000;
  return d > 0 ? d : null;
}

function fmtDur(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

function isToday(iso?: string): boolean {
  if (!iso) return false;
  const d = new Date(iso);
  const now = new Date();
  return d.toDateString() === now.toDateString();
}

export default function Pipelines({ project }: { project: string }) {
  const q = useQuery({ queryKey: ["builds", project], queryFn: () => fetchBuilds(project) });
  const builds = q.data?.value ?? [];
  const [openId, setOpenId] = useState<number | null>(null);

  const completed = builds.filter((b) => b.status === "completed");
  const succeeded = completed.filter((b) => b.result === "succeeded").length;
  const successRate = completed.length ? Math.round((succeeded / completed.length) * 100) : null;
  const durations = builds
    .map((b) => durationSec(b.startTime, b.finishTime))
    .filter((d): d is number => d !== null);
  const avgDur = durations.length ? durations.reduce((a, b) => a + b, 0) / durations.length : null;
  const runsToday = builds.filter((b) => isToday(b.startTime)).length;

  return (
    <div>
      <H1>Pipelines</H1>

      <div className="mb-4 mt-4 grid grid-cols-3 gap-[14px]">
        <Kpi label="Success rate" value={successRate === null ? "—" : `${successRate}`} suffix={successRate === null ? "" : "%"} />
        <Kpi label="Avg duration" value={avgDur === null ? "—" : fmtDur(avgDur)} />
        <Kpi label="Runs today" value={String(runsToday)} />
      </div>

      {q.isLoading && <Loading />}
      {q.isError && <ErrorMsg error={q.error} />}

      {q.data && (
        <Card className="overflow-hidden">
          <div className="border-b border-border-2 px-[18px] py-[13px] text-[13px] font-semibold text-text">
            Recent runs
          </div>
          {builds.map((b) => (
            <div key={b.id} className="border-t border-line">
              <button
                className="flex w-full items-center gap-3 px-[18px] py-[11px] text-left hover:bg-hover"
                onClick={() => setOpenId(openId === b.id ? null : b.id)}
              >
                <span className={`h-2 w-2 flex-none rounded-full ${buildDot(b.status, b.result)}`} />
                <div className="min-w-0 flex-1">
                  <span className="text-[13px] font-medium text-text">{b.definition ?? "—"}</span>
                  <span className="ml-2 font-mono text-[11px] text-faint">{b.buildNumber}</span>
                </div>
                <Pill className={buildChip(b.status, b.result)}>{label(b)}</Pill>
                <span className="w-[160px] truncate font-mono text-[11.5px] text-text-3">{b.sourceBranch}</span>
                <span className="w-[80px] flex-none text-right text-[12px] text-text-3">{b.requestedFor ?? "—"}</span>
                <span className="w-[44px] flex-none text-right font-mono text-[11px] text-faint">{relTime(b.startTime)}</span>
                <span className="w-[14px] flex-none text-center text-[10px] text-faint">{openId === b.id ? "▾" : "▸"}</span>
              </button>
              {openId === b.id && <BuildDetail project={project} buildId={b.id} />}
            </div>
          ))}
          {builds.length === 0 && <Empty>No pipeline runs.</Empty>}
        </Card>
      )}
    </div>
  );
}

/** Timeline rows we render, flattened with a display depth. Phases are
 * transparent (ADO nests Stage → Phase → Job → Task; the Phase adds noise). */
function flattenTimeline(records: TimelineRecord[]): { rec: TimelineRecord; depth: number }[] {
  const byParent = new Map<string | null, TimelineRecord[]>();
  for (const r of records) {
    const list = byParent.get(r.parentId ?? null) ?? [];
    list.push(r);
    byParent.set(r.parentId ?? null, list);
  }
  const out: { rec: TimelineRecord; depth: number }[] = [];
  const walk = (parentId: string | null, depth: number) => {
    for (const r of byParent.get(parentId) ?? []) {
      if (r.type === "Phase") {
        walk(r.id, depth); // transparent
      } else if (r.type === "Stage" || r.type === "Job" || r.type === "Task") {
        out.push({ rec: r, depth });
        walk(r.id, depth + 1);
      }
    }
  };
  walk(null, 0);
  // Orphan-safe fallback: if parent links didn't resolve to anything, show flat.
  return out.length ? out : records.filter((r) => r.type !== "Phase").map((rec) => ({ rec, depth: 0 }));
}

function BuildDetail({ project, buildId }: { project: string; buildId: number }) {
  const tq = useQuery({
    queryKey: ["buildTimeline", project, buildId],
    queryFn: () => fetchBuildTimeline(project, buildId),
  });
  const records = useMemo(() => tq.data?.value ?? [], [tq.data]);
  const rows = useMemo(() => flattenTimeline(records), [records]);
  const [sel, setSel] = useState<TimelineRecord | null>(null);

  // A failed build should open on its evidence: auto-select the first failed
  // step that has a log.
  useEffect(() => {
    if (records.length === 0) return;
    setSel((cur) => {
      if (cur) return cur;
      return records.find((r) => r.type === "Task" && r.result === "failed" && r.logId) ?? null;
    });
  }, [records]);

  return (
    <div className="border-t border-line bg-surface-2 px-[18px] py-[12px]">
      {tq.isLoading && <Loading />}
      {tq.isError && <ErrorMsg error={tq.error} />}
      {tq.data && rows.length === 0 && <Empty>No timeline yet.</Empty>}

      {rows.map(({ rec, depth }) => {
        const dur = durationSec(rec.startTime, rec.finishTime);
        const clickable = rec.logId !== null;
        const selected = sel?.id === rec.id;
        return (
          <div key={rec.id}>
            <button
              disabled={!clickable}
              onClick={() => clickable && setSel(selected ? null : rec)}
              className={`flex w-full items-center gap-2 rounded px-[6px] py-[4px] text-left ${
                clickable ? "hover:bg-hover" : "cursor-default"
              } ${selected ? "bg-hover" : ""}`}
              style={{ paddingLeft: 6 + depth * 18 }}
            >
              <span className={`h-[7px] w-[7px] flex-none rounded-full ${buildDot(rec.state, rec.result)}`} />
              <span className={`min-w-0 flex-1 truncate text-[12.5px] ${rec.type === "Stage" ? "font-semibold text-text" : "text-text-2"}`}>
                {rec.name}
              </span>
              {rec.errorCount > 0 && (
                <Pill className="bg-danger-bg text-danger">{rec.errorCount} err</Pill>
              )}
              {dur !== null && <span className="flex-none font-mono text-[11px] text-faint">{fmtDur(dur)}</span>}
              {clickable && <span className="flex-none text-[10.5px] text-faint">log</span>}
            </button>
            {selected && (
              <div className="mb-[6px] mt-[2px]" style={{ marginLeft: 6 + depth * 18 }}>
                {rec.issues.length > 0 && (
                  <div className="mb-[6px] space-y-[3px]">
                    {rec.issues.map((i, k) => (
                      <div key={k} className={`text-[12px] ${i.type === "error" ? "text-danger" : "text-warn"}`}>
                        {i.message}
                      </div>
                    ))}
                  </div>
                )}
                {rec.logId !== null && <LogView project={project} buildId={buildId} logId={rec.logId} />}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ADO prefixes every log line with an ISO timestamp; strip it for reading.
const TS_PREFIX = /^\d{4}-\d{2}-\d{2}T[\d:.]+Z /;

function logLineClass(line: string): string {
  if (line.includes("##[error]")) return "text-danger";
  if (line.includes("##[warning]")) return "text-warn";
  if (line.includes("##[section]")) return "font-semibold text-text";
  return "text-text-2";
}

function LogView({ project, buildId, logId }: { project: string; buildId: number; logId: number }) {
  const lq = useQuery({
    queryKey: ["buildLog", project, buildId, logId],
    queryFn: () => fetchBuildLog(project, buildId, logId),
  });

  if (lq.isLoading) return <Loading />;
  if (lq.isError) return <ErrorMsg error={lq.error} />;
  const log = lq.data;
  if (!log) return null;
  const lines = log.content.replace(/\n$/, "").split("\n");

  return (
    <div className="overflow-hidden rounded-md border border-border-2 bg-surface">
      {log.truncated && (
        <div className="border-b border-line px-[12px] py-[6px] text-[11px] text-muted">
          Long log — showing the tail.
        </div>
      )}
      <pre className="m-0 max-h-[380px] overflow-auto px-[12px] py-[8px] font-mono text-[11.5px] leading-[17px]">
        {lines.map((l, i) => (
          <div key={i} className={logLineClass(l)}>
            {l.replace(TS_PREFIX, "") || " "}
          </div>
        ))}
      </pre>
    </div>
  );
}

function Kpi({ label, value, suffix = "" }: { label: string; value: string; suffix?: string }) {
  return (
    <Card className="p-[14px_16px]">
      <div className="text-[11.5px] text-muted">{label}</div>
      <div className="mt-[6px] font-mono text-[26px] font-semibold text-text">
        {value}
        {suffix && <span className="text-[15px] text-muted">{suffix}</span>}
      </div>
    </Card>
  );
}
