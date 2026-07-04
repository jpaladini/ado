import { useEffect, useState } from "react";
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createPrThread,
  fetchPrDiff,
  fetchPrFiles,
  fetchPrThreads,
  fetchPullRequests,
  reviewPr,
  mergePullRequest,
  setPullRequestStatus,
  votePullRequest,
  type PullRequest,
  type ReviewComment,
} from "../api";
import { Card, Empty, ErrorMsg, H1, Loading, Pill, relTime } from "../components/ui";
import { Drawer, INPUT } from "../components/Drawer";
import { AIButton, useCopilotConfigured } from "../components/AIButton";
import { IconCheck, IconChevron } from "../components/icons";
import { prChip } from "../lib/tokens";
import { renderMarkdown } from "../lib/markdown";
import { useToast } from "../components/Toast";

const STATUSES = ["active", "completed", "abandoned"] as const;
type Status = (typeof STATUSES)[number];

export default function PullRequests({
  project,
  openTarget,
}: {
  project: string;
  openTarget?: PullRequest | null;
}) {
  const [status, setStatus] = useState<Status>("active");
  const [approved, setApproved] = useState<Set<number>>(new Set());
  const [openPr, setOpenPr] = useState<PullRequest | null>(null);

  // deep link from the header search — a fresh object per pick re-triggers this;
  // the search result row is the same shape the list renders, so it drives the
  // drawer directly and the status filter follows it
  useEffect(() => {
    if (!openTarget) return;
    if (STATUSES.includes(openTarget.status as Status)) setStatus(openTarget.status as Status);
    setOpenPr(openTarget);
  }, [openTarget]);

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
              onOpen={() => setOpenPr(pr)}
            />
          ))}
          {active.data.value.length === 0 && <Empty>No {status} pull requests.</Empty>}
        </Card>
      )}

      {openPr && (
        <PRDrawer
          project={project}
          pr={openPr}
          approved={approved.has(openPr.id)}
          onApproved={() => setApproved((s) => new Set(s).add(openPr.id))}
          onClose={() => setOpenPr(null)}
        />
      )}
    </div>
  );
}

/** Approve / abandon / reactivate mutations, shared by the row and the drawer. */
function usePrActions(project: string, pr: PullRequest, onApproved: () => void) {
  const qc = useQueryClient();
  const toast = useToast();
  const repoId = pr.repositoryId;

  const vote = useMutation({
    mutationFn: () => votePullRequest(project, repoId!, pr.id, 10),
    onSuccess: () => {
      onApproved();
      // refetch so ADO's approval state lands and the Merge button appears
      qc.invalidateQueries({ queryKey: ["prs", project] });
      toast(`PR !${pr.id} approved`);
    },
    // a silent failure looks like a dead button — always say what happened
    onError: (e) => toast(`Approve failed: ${(e as Error).message}`),
  });
  const setStatusMut = useMutation({
    mutationFn: (s: string) => setPullRequestStatus(project, repoId!, pr.id, s),
    onSuccess: (_d, s) => {
      qc.invalidateQueries({ queryKey: ["prs", project] });
      toast(`PR !${pr.id} ${s === "abandoned" ? "abandoned" : "reactivated"}`);
    },
    onError: (e) => toast(`Failed: ${(e as Error).message}`),
  });
  const merge = useMutation({
    mutationFn: () => mergePullRequest(project, repoId!, pr.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["prs", project] });
      toast(`PR !${pr.id} merged`);
    },
    // policy failures (required build, min reviewers) surface here from ADO
    onError: (e) => toast(`Merge failed: ${(e as Error).message}`),
  });
  return {
    vote,
    setStatusMut,
    merge,
    busy: vote.isPending || setStatusMut.isPending || merge.isPending,
    canAct: !!repoId,
    // approved per ADO (any reviewer set counts) and mergeable (no conflicts)
    canMerge: !!repoId && pr.status === "active" && !!pr.isApproved && pr.mergeStatus === "succeeded",
  };
}

function ActionButtons({
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
  const { vote, setStatusMut, merge, busy, canAct, canMerge } = usePrActions(project, pr, onApproved);
  return (
    <>
      {canMerge && (
        <button
          onClick={() => confirm(`Merge PR !${pr.id} into ${pr.targetRef}?`) && merge.mutate()}
          disabled={busy}
          title="Approved in ADO and free of conflicts — branch policies still apply on completion"
          className="mr-[7px] rounded-[7px] bg-accent px-[12px] py-[6px] text-[11.5px] font-semibold text-white hover:bg-accent-hover disabled:opacity-50"
        >
          Merge
        </button>
      )}
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
    </>
  );
}

function Row({
  project,
  pr,
  approved,
  onApproved,
  onOpen,
}: {
  project: string;
  pr: PullRequest;
  approved: boolean;
  onApproved: () => void;
  onOpen: () => void;
}) {
  return (
    <div
      onClick={onOpen}
      className="group flex cursor-pointer items-center gap-3 border-t border-line px-[18px] py-[13px] hover:bg-hover"
    >
      <span className="w-[42px] flex-none font-mono text-[12px] text-faint">!{pr.id}</span>
      <div className="min-w-0 flex-1">
        <div className="truncate text-[13px] font-medium text-text">{pr.title}</div>
        <div className="mt-[2px] font-mono text-[11px] text-faint">
          {pr.sourceRef} → {pr.targetRef}
        </div>
      </div>
      {pr.isDraft && <Pill className="bg-nbg text-nfg">draft</Pill>}
      <Pill className={prChip(pr.status, pr.isDraft)}>{pr.status}</Pill>

      <span onClick={(e) => e.stopPropagation()}>
        <ActionButtons project={project} pr={pr} approved={approved} onApproved={onApproved} />
      </span>

      <span className="w-[72px] flex-none text-right text-[12px] text-text-3">{pr.createdBy ?? "—"}</span>
      <span className="w-[44px] flex-none text-right font-mono text-[11px] text-faint">
        {relTime(pr.creationDate)}
      </span>
      <span className="inline-block flex-none -rotate-90 text-faint opacity-40 group-hover:opacity-100">
        <IconChevron size={11} />
      </span>
    </div>
  );
}

// ---- PR detail drawer: files, diffs, threads ---------------------------------------

function changeChip(changeType: string): string {
  const t = (changeType || "").toLowerCase();
  if (t.includes("add")) return "bg-ok-bg text-ok";
  if (t.includes("delete")) return "bg-danger-bg text-danger";
  if (t.includes("rename")) return "bg-purple-bg text-purple";
  return "bg-warn-bg text-warn"; // edit
}

function PRDrawer({
  project,
  pr,
  approved,
  onApproved,
  onClose,
}: {
  project: string;
  pr: PullRequest;
  approved: boolean;
  onApproved: () => void;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const toast = useToast();
  const rid = pr.repositoryId!;

  const files = useQuery({
    queryKey: ["prfiles", project, rid, pr.id],
    queryFn: () => fetchPrFiles(project, rid, pr.id),
    enabled: !!rid,
  });
  const threads = useQuery({
    queryKey: ["prthreads", project, rid, pr.id],
    queryFn: () => fetchPrThreads(project, rid, pr.id),
    enabled: !!rid,
  });

  const [comment, setComment] = useState("");
  const commentMut = useMutation({
    mutationFn: (t: string) => createPrThread(project, rid, pr.id, { comment: t }),
    onSuccess: () => {
      setComment("");
      qc.invalidateQueries({ queryKey: ["prthreads", project, rid, pr.id] });
      toast("Comment added");
    },
  });

  // -- in-place AI review: suggestions live under each file's diff ---------------
  const aiOn = useCopilotConfigured();
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [suggestions, setSuggestions] = useState<Record<string, ReviewComment[]>>({});
  const [reviewSummary, setReviewSummary] = useState<string | null>(null);

  const toggleFile = (path: string) =>
    setExpanded((s) => {
      const next = new Set(s);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });

  const applyReview = (comments: ReviewComment[], scope?: string) => {
    const grouped: Record<string, ReviewComment[]> = {};
    for (const c of comments) (grouped[c.path] ??= []).push(c);
    setSuggestions((prev) => (scope ? { ...prev, [scope]: grouped[scope] ?? [] } : grouped));
    // put every suggestion next to its code: expand the files that got comments
    setExpanded((s) => new Set([...s, ...Object.keys(grouped)]));
  };

  const review = useMutation({
    mutationFn: (path?: string) => reviewPr(project, rid, pr.id, path),
    onSuccess: (r, path) => {
      applyReview(r.comments, path);
      if (!path) setReviewSummary(r.summary);
      toast(r.comments.length ? `${r.comments.length} suggestion${r.comments.length > 1 ? "s" : ""}` : "Nothing to flag");
    },
  });

  return (
    <Drawer
      width="w-[720px]"
      onClose={onClose}
      title={
        <span className="inline-flex items-center gap-[10px]">
          <span className="font-mono text-faint">!{pr.id}</span>
          <span className="max-w-[380px] truncate">{pr.title}</span>
          <Pill className={prChip(pr.status, pr.isDraft)}>{pr.status}</Pill>
        </span>
      }
    >
      <div className="mb-[14px] flex items-center justify-between">
        <div className="font-mono text-[11.5px] text-faint">
          {pr.sourceRef} → {pr.targetRef} · {pr.createdBy ?? "—"} · {relTime(pr.creationDate)} ago
        </div>
        <span className="flex items-center gap-[8px]" onClick={(e) => e.stopPropagation()}>
          {aiOn && (
            <AIButton
              label="AI review"
              busy={review.isPending && review.variables === undefined}
              onClick={() => review.mutate(undefined)}
            />
          )}
          <ActionButtons project={project} pr={pr} approved={approved} onApproved={onApproved} />
        </span>
      </div>

      {pr.description && (
        <div
          className="markdown mb-[14px] max-h-[220px] overflow-auto rounded-[8px] border border-line bg-surface-2 px-[14px] py-[10px] text-[12.5px] text-text-2"
          dangerouslySetInnerHTML={{ __html: renderMarkdown(pr.description) }}
        />
      )}

      {review.isError && <ErrorMsg error={review.error} />}
      {reviewSummary && (
        <div className="mb-[12px] rounded-[8px] border border-accent-border bg-accent-tint px-[12px] py-[8px] text-[12.5px] text-text">
          <span className="font-semibold text-accent-text">AI review: </span>
          {reviewSummary}
        </div>
      )}

      <div className="mb-[10px] text-[10.5px] font-semibold uppercase tracking-[0.5px] text-faint">
        Files changed {files.data ? `(${files.data.files.length})` : ""}
      </div>
      {files.isLoading && <Loading />}
      {files.isError && <ErrorMsg error={files.error} />}
      {files.data?.files.map((f) => (
        <FileRow
          key={f.path}
          project={project}
          rid={rid}
          prId={pr.id}
          file={f}
          open={expanded.has(f.path)}
          onToggle={() => toggleFile(f.path)}
          suggestions={suggestions[f.path] ?? []}
          aiOn={aiOn}
          onReviewFile={() => review.mutate(f.path)}
          reviewBusy={review.isPending && review.variables === f.path}
        />
      ))}
      {files.data && files.data.files.length === 0 && (
        <div className="text-[12px] text-faint">No file changes found.</div>
      )}

      <div className="mt-[22px] border-t border-line pt-[14px]">
        <div className="mb-[10px] text-[10.5px] font-semibold uppercase tracking-[0.5px] text-faint">
          Comments {threads.data ? `(${threads.data.value.length})` : ""}
        </div>
        <div className="mb-[12px] flex items-start gap-[8px]">
          <textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="Add a comment…"
            rows={2}
            className={`${INPUT} flex-1 resize-none`}
          />
          <button
            onClick={() => comment.trim() && commentMut.mutate(comment.trim())}
            disabled={commentMut.isPending || !comment.trim()}
            className="rounded-[7px] bg-accent px-[13px] py-[8px] text-[12px] font-semibold text-white hover:bg-accent-hover disabled:opacity-50"
          >
            Send
          </button>
        </div>
        {commentMut.isError && <ErrorMsg error={commentMut.error} />}
        {threads.isLoading && <Loading label="Loading comments…" />}
        {threads.data?.value.map((t) => (
          <div key={t.id} className="mb-[10px] rounded-[8px] border border-line bg-bg p-[10px_12px]">
            {t.filePath && (
              <div className="mb-[6px] inline-block rounded-[4px] bg-nbg px-[6px] py-[1px] font-mono text-[10.5px] text-nfg">
                {t.filePath}
                {t.line ? `:${t.line}` : ""}
              </div>
            )}
            {t.comments.map((c) => (
              <div key={c.id} className="mb-[6px] last:mb-0">
                <div className="mb-[2px] flex items-center justify-between text-[11px]">
                  <span className="font-semibold text-text-2">{c.author ?? "—"}</span>
                  <span className="font-mono text-faint">{relTime(c.publishedDate)}</span>
                </div>
                <div className="whitespace-pre-wrap text-[12.5px] text-text-2">{c.content}</div>
              </div>
            ))}
          </div>
        ))}
        {threads.data && threads.data.value.length === 0 && (
          <div className="text-[12px] text-faint">No comments yet.</div>
        )}
      </div>
    </Drawer>
  );
}

function FileRow({
  project,
  rid,
  prId,
  file,
  open,
  onToggle,
  suggestions,
  aiOn,
  onReviewFile,
  reviewBusy,
}: {
  project: string;
  rid: string;
  prId: number;
  file: { path: string; originalPath?: string | null; changeType: string };
  open: boolean;
  onToggle: () => void;
  suggestions: ReviewComment[];
  aiOn: boolean;
  onReviewFile: () => void;
  reviewBusy: boolean;
}) {
  const diff = useQuery({
    queryKey: ["prdiff", project, rid, prId, file.path],
    queryFn: () => fetchPrDiff(project, rid, prId, file.path),
    enabled: open,
    staleTime: 60_000,
  });

  return (
    <div className="mb-[6px] overflow-hidden rounded-[8px] border border-line">
      <button
        onClick={onToggle}
        className="flex w-full items-center gap-[8px] bg-surface-2 px-[12px] py-[7px] text-left hover:bg-hover"
      >
        <span className={`text-faint transition-transform ${open ? "" : "-rotate-90"}`}>
          <IconChevron size={10} />
        </span>
        <span
          className={`rounded-[4px] px-[6px] py-[1px] text-[10.5px] font-semibold ${changeChip(file.changeType)}`}
        >
          {(file.changeType || "edit").replace(/,.*$/, "")}
        </span>
        <span className="min-w-0 flex-1 truncate font-mono text-[12px] text-text">
          {file.originalPath && file.originalPath !== file.path
            ? `${file.originalPath} → ${file.path}`
            : file.path}
        </span>
        {suggestions.length > 0 && (
          <span className="flex-none rounded-[10px] bg-accent-tint px-[7px] py-[1px] text-[10.5px] font-semibold text-accent-text">
            ✦ {suggestions.length}
          </span>
        )}
        {diff.data && !diff.data.binary && !diff.data.tooLarge && (
          <span className="flex-none font-mono text-[11px]">
            <span className="text-ok">+{diff.data.addedLines}</span>{" "}
            <span className="text-danger">−{diff.data.removedLines}</span>
          </span>
        )}
      </button>
      {open && (
        <div>
          {diff.isLoading && <Loading label="Loading diff…" />}
          {diff.isError && <ErrorMsg error={diff.error} />}
          {diff.data?.binary && <div className="px-[12px] py-[8px] text-[12px] text-faint">Binary file.</div>}
          {diff.data?.tooLarge && (
            <div className="px-[12px] py-[8px] text-[12px] text-warn">File too large to diff.</div>
          )}
          {diff.data && !diff.data.binary && !diff.data.tooLarge && (
            <>
              <DiffView diff={diff.data.diff} />
              {suggestions.map((s, i) => (
                <SuggestionCard key={`${s.line}-${i}`} project={project} rid={rid} prId={prId} s={s} />
              ))}
              <div className="flex items-center justify-between border-t border-line bg-surface-2 px-[10px] py-[5px]">
                {aiOn ? (
                  <AIButton label="Review this file" busy={reviewBusy} onClick={onReviewFile} />
                ) : (
                  <span />
                )}
              </div>
              <InlineFileComment project={project} rid={rid} prId={prId} path={file.path} />
            </>
          )}
        </div>
      )}
    </div>
  );
}

// ---- AI review suggestion card (in place, under the diff it belongs to) -----------

const SEVERITY_CHIP: Record<string, string> = {
  nit: "bg-nbg text-nfg",
  suggestion: "bg-info-bg text-info",
  issue: "bg-warn-bg text-warn",
};

function SuggestionCard({
  project,
  rid,
  prId,
  s,
}: {
  project: string;
  rid: string;
  prId: number;
  s: ReviewComment;
}) {
  const qc = useQueryClient();
  const toast = useToast();
  const [status, setStatus] = useState<"pending" | "applied" | "dismissed">("pending");

  const apply = useMutation({
    mutationFn: () =>
      createPrThread(project, rid, prId, { comment: s.comment, filePath: s.path, line: s.line }),
    onSuccess: () => {
      setStatus("applied");
      qc.invalidateQueries({ queryKey: ["prthreads", project, rid, prId] });
      toast("Review comment posted");
    },
  });

  if (status === "dismissed") return null;

  return (
    <div className="border-t border-accent-border bg-accent-tint px-[12px] py-[9px]">
      <div className="mb-[4px] flex items-center gap-[8px]">
        <span className={`rounded-[4px] px-[6px] py-[1px] text-[10.5px] font-semibold ${SEVERITY_CHIP[s.severity] ?? SEVERITY_CHIP.suggestion}`}>
          {s.severity}
        </span>
        <span className="font-mono text-[11px] text-faint">line {s.line}</span>
        {status === "applied" && (
          <span className="rounded-[10px] bg-ok-bg px-[7px] py-[1px] text-[10.5px] font-semibold text-ok">posted</span>
        )}
      </div>
      <div className="text-[12.5px] text-text">{s.comment}</div>
      {apply.isError && <div className="mt-[4px] text-[11px] text-danger">{(apply.error as Error).message}</div>}
      {status === "pending" && (
        <div className="mt-[8px] flex gap-[6px]">
          <button
            onClick={() => apply.mutate()}
            disabled={apply.isPending}
            className="rounded-[6px] bg-accent px-[11px] py-[4px] text-[11.5px] font-semibold text-white hover:bg-accent-hover disabled:opacity-50"
          >
            {apply.isPending ? "Posting…" : "Post comment"}
          </button>
          <button
            onClick={() => setStatus("dismissed")}
            className="rounded-[6px] border border-border bg-surface px-[10px] py-[4px] text-[11.5px] font-medium text-text-3 hover:bg-hover"
          >
            Dismiss
          </button>
        </div>
      )}
    </div>
  );
}

function DiffView({ diff }: { diff: string }) {
  if (!diff) return <div className="px-[12px] py-[8px] text-[12px] text-faint">No changes.</div>;
  return (
    <div className="overflow-x-auto font-mono text-[11.5px] leading-[18px]">
      {diff.split("\n").map((line, i) => {
        let cls = "text-text-2";
        if (line.startsWith("+++") || line.startsWith("---")) cls = "text-faint";
        else if (line.startsWith("@@")) cls = "text-info bg-info-bg";
        else if (line.startsWith("+")) cls = "bg-ok-bg text-ok";
        else if (line.startsWith("-")) cls = "bg-danger-bg text-danger";
        return (
          <div key={i} className={`whitespace-pre px-[12px] ${cls}`}>
            {line || " "}
          </div>
        );
      })}
    </div>
  );
}

function InlineFileComment({
  project,
  rid,
  prId,
  path,
}: {
  project: string;
  rid: string;
  prId: number;
  path: string;
}) {
  const qc = useQueryClient();
  const toast = useToast();
  const [line, setLine] = useState("");
  const [text, setText] = useState("");
  const mut = useMutation({
    mutationFn: () =>
      createPrThread(project, rid, prId, {
        comment: text.trim(),
        filePath: path,
        ...(line.trim() ? { line: Number(line) } : {}),
      }),
    onSuccess: () => {
      setText("");
      setLine("");
      qc.invalidateQueries({ queryKey: ["prthreads", project, rid, prId] });
      toast("Comment added");
    },
  });
  return (
    <div className="flex items-center gap-[6px] border-t border-line bg-surface-2 px-[10px] py-[7px]">
      <input
        value={line}
        onChange={(e) => setLine(e.target.value.replace(/\D/g, ""))}
        placeholder="line"
        className="w-[64px] flex-none rounded-[7px] border border-border bg-bg px-[6px] py-[5px] text-center text-[12.5px] text-text outline-none placeholder:text-faint focus:border-faint"
      />
      <input
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Comment on this file…"
        className={`${INPUT} flex-1 py-[5px]`}
      />
      <button
        onClick={() => text.trim() && mut.mutate()}
        disabled={mut.isPending || !text.trim()}
        className="rounded-[6px] bg-accent px-[11px] py-[5px] text-[11.5px] font-semibold text-white hover:bg-accent-hover disabled:opacity-50"
      >
        Post
      </button>
      {mut.isError && <span className="text-[11px] text-danger">{(mut.error as Error).message}</span>}
    </div>
  );
}
