import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchPullRequests,
  setPullRequestStatus,
  votePullRequest,
  type PullRequest,
} from "../api";
import { Badge, Empty, ErrorMsg, Loading, prTone, relTime } from "./ui";

const STATUSES = ["active", "completed", "abandoned"] as const;
type Status = (typeof STATUSES)[number];

export default function PullRequestsPanel({ project }: { project: string }) {
  const [status, setStatus] = useState<Status>("active");
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
          <PrRow key={pr.id} project={project} pr={pr} status={status} />
        ))}
      </ul>
    </div>
  );
}

function PrRow({ project, pr, status }: { project: string; pr: PullRequest; status: Status }) {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: ["prs", project] });

  const vote = useMutation({
    mutationFn: (v: number) => votePullRequest(project, pr.repositoryId!, pr.id, v),
    onSuccess: invalidate,
  });
  const setStatusMut = useMutation({
    mutationFn: (s: string) => setPullRequestStatus(project, pr.repositoryId!, pr.id, s),
    onSuccess: invalidate,
  });

  const busy = vote.isPending || setStatusMut.isPending;
  const err = (vote.error || setStatusMut.error) as Error | null;
  const canAct = !!pr.repositoryId;

  return (
    <li className="py-2.5">
      <div className="flex items-center gap-3">
        <span className="w-14 shrink-0 text-xs text-slate-400">!{pr.id}</span>
        <span className="flex-1 truncate text-sm text-slate-800" title={pr.title}>
          {pr.title}
        </span>
        {pr.isDraft && <Badge tone="slate">draft</Badge>}
        <Badge tone={prTone(pr.status, pr.isDraft)}>{pr.status}</Badge>

        {canAct && status === "active" && (
          <>
            <button
              onClick={() => vote.mutate(10)}
              disabled={busy}
              className="shrink-0 rounded-md bg-emerald-600 px-2.5 py-1 text-xs font-medium text-white disabled:opacity-50"
            >
              Approve
            </button>
            <button
              onClick={() => {
                if (confirm(`Abandon PR !${pr.id}?`)) setStatusMut.mutate("abandoned");
              }}
              disabled={busy}
              className="shrink-0 rounded-md border border-rose-200 px-2.5 py-1 text-xs font-medium text-rose-600 hover:bg-rose-50 disabled:opacity-50"
            >
              Abandon
            </button>
          </>
        )}
        {canAct && status === "abandoned" && (
          <button
            onClick={() => setStatusMut.mutate("active")}
            disabled={busy}
            className="shrink-0 rounded-md border border-slate-200 px-2.5 py-1 text-xs font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-50"
          >
            Reactivate
          </button>
        )}

        <span className="w-24 shrink-0 truncate text-right text-xs text-slate-500">
          {pr.createdBy ?? "—"}
        </span>
        <span className="w-16 shrink-0 text-right text-xs text-slate-400">
          {relTime(pr.creationDate)}
        </span>
      </div>
      {err && <p className="ml-14 mt-1 text-xs text-rose-600">{err.message}</p>}
    </li>
  );
}
