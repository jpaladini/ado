import { useState } from "react";
import { useMutation, useQueries, useQueryClient } from "@tanstack/react-query";
import { fetchPullRequests, setPullRequestStatus, votePullRequest, type PullRequest } from "../api";
import { Card, Empty, ErrorMsg, H1, Loading, Pill, relTime } from "../components/ui";
import { IconCheck } from "../components/icons";
import { prChip } from "../lib/tokens";
import { useToast } from "../components/Toast";

const STATUSES = ["active", "completed", "abandoned"] as const;
type Status = (typeof STATUSES)[number];

export default function PullRequests({ project }: { project: string }) {
  const [status, setStatus] = useState<Status>("active");
  const [approved, setApproved] = useState<Set<number>>(new Set());

  // one query per status → gives us list + chip counts together
  const results = useQueries({
    queries: STATUSES.map((s) => ({
      queryKey: ["prs", project, s],
      queryFn: () => fetchPullRequests(project, s),
    })),
  });
  const byStatus = Object.fromEntries(STATUSES.map((s, i) => [s, results[i]])) as Record<
    Status,
    (typeof results)[number]
  >;
  const active = byStatus[status];

  return (
    <div>
      <H1>Pull Requests</H1>

      <div className="mb-[14px] mt-4 flex gap-[6px]">
        {STATUSES.map((s) => {
          const on = status === s;
          return (
            <button
              key={s}
              onClick={() => setStatus(s)}
              className={`rounded-[7px] border px-[14px] py-[6px] text-[12px] capitalize ${
                on ? "border-ink-bg bg-ink-bg font-semibold text-ink-fg" : "border-border bg-surface font-medium text-text-3 hover:border-faint"
              }`}
            >
              {s} <span className="font-mono opacity-70">{byStatus[s].data?.value.length ?? 0}</span>
            </button>
          );
        })}
      </div>

      {active.isLoading && <Loading />}
      {active.isError && <ErrorMsg error={active.error} />}

      {active.data && (
        <Card className="overflow-hidden">
          {active.data.value.map((pr) => (
            <Row
              key={pr.id}
              project={project}
              pr={pr}
              approved={approved.has(pr.id)}
              onApproved={() => setApproved((s) => new Set(s).add(pr.id))}
            />
          ))}
          {active.data.value.length === 0 && <Empty>No {status} pull requests.</Empty>}
        </Card>
      )}
    </div>
  );
}

function Row({
  project,
  pr,
  approved,
  onApproved,
}: {
  project: string;
  pr: PullRequest;
  approved: boolean;
  onApproved: () => void;
}) {
  const qc = useQueryClient();
  const toast = useToast();
  const invalidate = () => qc.invalidateQueries({ queryKey: ["prs", project] });
  const repoId = pr.repositoryId;

  const vote = useMutation({
    mutationFn: () => votePullRequest(project, repoId!, pr.id, 10),
    onSuccess: () => {
      onApproved();
      toast(`PR !${pr.id} approved`);
    },
  });
  const setStatusMut = useMutation({
    mutationFn: (s: string) => setPullRequestStatus(project, repoId!, pr.id, s),
    onSuccess: (_d, s) => {
      invalidate();
      toast(`PR !${pr.id} ${s === "abandoned" ? "abandoned" : "reactivated"}`);
    },
  });
  const busy = vote.isPending || setStatusMut.isPending;
  const canAct = !!repoId;

  return (
    <div className="flex items-center gap-3 border-t border-line px-[18px] py-[13px] hover:bg-hover">
      <span className="w-[42px] flex-none font-mono text-[12px] text-faint">!{pr.id}</span>
      <div className="min-w-0 flex-1">
        <div className="truncate text-[13px] font-medium text-text">{pr.title}</div>
        <div className="mt-[2px] font-mono text-[11px] text-faint">
          {pr.sourceRef} → {pr.targetRef}
        </div>
      </div>
      {pr.isDraft && <Pill className="bg-nbg text-nfg">draft</Pill>}
      <Pill className={prChip(pr.status, pr.isDraft)}>{pr.status}</Pill>

      {canAct && pr.status === "active" && !approved && (
        <div className="flex gap-[7px]">
          <button
            onClick={() => vote.mutate()}
            disabled={busy}
            className="rounded-[7px] bg-btn-ok px-[12px] py-[6px] text-[11.5px] font-semibold text-white disabled:opacity-50"
          >
            Approve
          </button>
          <button
            onClick={() => confirm(`Abandon PR !${pr.id}?`) && setStatusMut.mutate("abandoned")}
            disabled={busy}
            className="rounded-[7px] border border-abandon-border bg-surface px-[12px] py-[6px] text-[11.5px] font-semibold text-danger disabled:opacity-50"
          >
            Abandon
          </button>
        </div>
      )}
      {pr.status === "active" && approved && (
        <span className="inline-flex items-center gap-[5px] text-[11.5px] font-semibold text-ok">
          <IconCheck size={14} />
          approved
        </span>
      )}
      {canAct && pr.status === "abandoned" && (
        <button
          onClick={() => setStatusMut.mutate("active")}
          disabled={busy}
          className="rounded-[7px] border border-border bg-surface px-[12px] py-[6px] text-[11.5px] font-semibold text-text-3 disabled:opacity-50"
        >
          Reactivate
        </button>
      )}

      <span className="w-[72px] flex-none text-right text-[12px] text-text-3">{pr.createdBy ?? "—"}</span>
      <span className="w-[44px] flex-none text-right font-mono text-[11px] text-faint">
        {relTime(pr.creationDate)}
      </span>
    </div>
  );
}
