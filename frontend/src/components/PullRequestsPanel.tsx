import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchPullRequests } from "../api";
import { Badge, Empty, ErrorMsg, Loading, prTone, relTime } from "./ui";

const STATUSES = ["active", "completed", "abandoned"] as const;

export default function PullRequestsPanel({ project }: { project: string }) {
  const [status, setStatus] = useState<(typeof STATUSES)[number]>("active");
  const q = useQuery({
    queryKey: ["prs", project, status],
    queryFn: () => fetchPullRequests(project, status),
  });

  return (
    <div>
      <div className="mb-3 flex gap-1">
        {STATUSES.map((s) => (
          <button
            key={s}
            onClick={() => setStatus(s)}
            className={`rounded-md px-2.5 py-1 text-xs font-medium capitalize transition ${
              status === s ? "bg-slate-800 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"
            }`}
          >
            {s}
          </button>
        ))}
      </div>

      {q.isLoading && <Loading />}
      {q.isError && <ErrorMsg error={q.error} />}
      {q.data?.value.length === 0 && <Empty>No {status} pull requests.</Empty>}

      <ul className="divide-y divide-slate-100">
        {q.data?.value.map((pr) => (
          <li key={pr.id} className="flex items-center gap-3 py-2.5">
            <span className="w-14 shrink-0 text-xs text-slate-400">!{pr.id}</span>
            <span className="flex-1 truncate text-sm text-slate-800" title={pr.title}>
              {pr.title}
            </span>
            {pr.isDraft && <Badge tone="slate">draft</Badge>}
            <Badge tone={prTone(pr.status, pr.isDraft)}>{pr.status}</Badge>
            <span className="hidden w-40 shrink-0 truncate text-xs text-slate-500 md:inline">
              {pr.sourceRef} → {pr.targetRef}
            </span>
            <span className="w-28 shrink-0 truncate text-right text-xs text-slate-500">
              {pr.createdBy ?? "—"}
            </span>
            <span className="w-20 shrink-0 text-right text-xs text-slate-400">
              {relTime(pr.creationDate)}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
