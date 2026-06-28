import { useQuery } from "@tanstack/react-query";
import { fetchBuilds } from "../api";
import { Badge, buildTone, Empty, ErrorMsg, Loading, relTime } from "./ui";

export default function PipelinesPanel({ project }: { project: string }) {
  const q = useQuery({
    queryKey: ["builds", project],
    queryFn: () => fetchBuilds(project),
  });

  if (q.isLoading) return <Loading />;
  if (q.isError) return <ErrorMsg error={q.error} />;
  const builds = q.data?.value ?? [];
  if (!builds.length) return <Empty>No pipeline runs.</Empty>;

  return (
    <ul className="divide-y divide-slate-100">
      {builds.map((b) => (
        <li key={b.id} className="flex items-center gap-3 py-2.5">
          <span className="flex-1 truncate text-sm text-slate-800" title={b.definition ?? ""}>
            {b.definition ?? "—"}
            <span className="ml-2 text-xs text-slate-400">{b.buildNumber}</span>
          </span>
          <Badge tone={buildTone(b.status, b.result)}>
            {b.status === "completed" ? (b.result ?? "done") : (b.status ?? "—")}
          </Badge>
          <span className="hidden w-32 shrink-0 truncate text-xs text-slate-500 md:inline">
            {b.sourceBranch}
          </span>
          <span className="w-28 shrink-0 truncate text-right text-xs text-slate-500">
            {b.requestedFor ?? "—"}
          </span>
          <span className="w-20 shrink-0 text-right text-xs text-slate-400">
            {relTime(b.startTime)}
          </span>
        </li>
      ))}
    </ul>
  );
}
