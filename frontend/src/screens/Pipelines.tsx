import { useQuery } from "@tanstack/react-query";
import { fetchBuilds, type Build } from "../api";
import { Card, Empty, ErrorMsg, H1, Loading, Pill, relTime } from "../components/ui";
import { buildChip, buildDot } from "../lib/tokens";

function label(b: Build): string {
  if (b.status && b.status !== "completed") return b.status === "inProgress" ? "running" : b.status;
  if (b.result === "partiallySucceeded") return "partial";
  return b.result ?? "—";
}

function durationSec(b: Build): number | null {
  if (!b.startTime || !b.finishTime) return null;
  const d = (new Date(b.finishTime).getTime() - new Date(b.startTime).getTime()) / 1000;
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

  const completed = builds.filter((b) => b.status === "completed");
  const succeeded = completed.filter((b) => b.result === "succeeded").length;
  const successRate = completed.length ? Math.round((succeeded / completed.length) * 100) : null;
  const durations = builds.map(durationSec).filter((d): d is number => d !== null);
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
            <div key={b.id} className="flex items-center gap-3 border-t border-line px-[18px] py-[11px] hover:bg-hover">
              <span className={`h-2 w-2 flex-none rounded-full ${buildDot(b.status, b.result)}`} />
              <div className="min-w-0 flex-1">
                <span className="text-[13px] font-medium text-text">{b.definition ?? "—"}</span>
                <span className="ml-2 font-mono text-[11px] text-faint">{b.buildNumber}</span>
              </div>
              <Pill className={buildChip(b.status, b.result)}>{label(b)}</Pill>
              <span className="w-[160px] truncate font-mono text-[11.5px] text-text-3">{b.sourceBranch}</span>
              <span className="w-[80px] flex-none text-right text-[12px] text-text-3">{b.requestedFor ?? "—"}</span>
              <span className="w-[44px] flex-none text-right font-mono text-[11px] text-faint">{relTime(b.startTime)}</span>
            </div>
          ))}
          {builds.length === 0 && <Empty>No pipeline runs.</Empty>}
        </Card>
      )}
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
