import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  addWorkItemComment,
  askCopilot,
  createCodePr,
  createPrThread,
  createWorkItem,
  deleteCopilotSession,
  downloadTableXlsx,
  fetchCopilotSession,
  fetchCopilotSessions,
  fetchHealth,
  saveCopilotSession,
  updateWorkItem,
  type CopilotProposal,
  type CopilotReply,
  type WorkItemCreatePayload,
  type WorkItemUpdatePayload,
} from "../api";
import { Card, H1 } from "../components/ui";
import FreshnessBar from "../components/FreshnessBar";
import { Spark } from "../components/icons";
import { textToHtml } from "../lib/text";
import { useToast } from "../components/Toast";

interface Turn {
  question: string;
  answer?: CopilotReply;
  error?: string;
}

const SUGGESTIONS = [
  "What's open right now, and who's overloaded?",
  "Create a task to tighten up the release checklist, assign it to me",
  "Read work item 2 and improve its description",
  "Any PRs waiting on review?",
];

export default function Copilot({ project, panel = false }: { project: string; panel?: boolean }) {
  const health = useQuery({ queryKey: ["health"], queryFn: fetchHealth });
  const qc = useQueryClient();
  const [turns, setTurns] = useState<Turn[]>([]);
  // Proposal outcomes ("applied" | "dismissed" | "failed: …"), keyed turnIdx:proposalId.
  // Fed back into the next turn's history so the model knows what actually happened.
  const [outcomes, setOutcomes] = useState<Record<string, string>>({});
  const [question, setQuestion] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  // -- session history: autosave after answered turns, restore on pick ------------
  const [sessionId, setSessionId] = useState<string | null>(null);
  const sessions = useQuery({
    queryKey: ["copilot-sessions", project],
    queryFn: () => fetchCopilotSessions(project),
    staleTime: 30_000,
  });

  const answeredTurns = turns.filter((t) => t.answer);
  useEffect(() => {
    if (!answeredTurns.length) return;
    const t = setTimeout(async () => {
      try {
        const saved = await saveCopilotSession({
          id: sessionId ?? undefined,
          project,
          title: turns[0]?.question.slice(0, 80),
          state: { turns: answeredTurns, outcomes },
        });
        if (saved.id !== sessionId) setSessionId(saved.id);
        qc.invalidateQueries({ queryKey: ["copilot-sessions", project] });
      } catch {
        // store unavailable — chat still works, it just won't persist
      }
    }, 800);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [answeredTurns.length, outcomes]);

  const restore = async (id: string) => {
    try {
      const s = await fetchCopilotSession(id);
      setSessionId(s.id);
      setTurns((s.state.turns as Turn[]) ?? []);
      setOutcomes(s.state.outcomes ?? {});
      setTimeout(() => endRef.current?.scrollIntoView(), 50);
    } catch {
      /* stay on the current chat */
    }
  };

  const newChat = () => {
    setSessionId(null);
    setTurns([]);
    setOutcomes({});
  };

  const removeSession = async (id: string) => {
    try {
      await deleteCopilotSession(id);
      qc.invalidateQueries({ queryKey: ["copilot-sessions", project] });
      if (id === sessionId) newChat();
    } catch {
      /* leave the list as is */
    }
  };

  const outcomeNote = (t: Turn, i: number) => {
    const ps = t.answer?.proposals ?? [];
    if (ps.length === 0) return "";
    const parts = ps.map((p) => `${proposalTitle(p)} → ${outcomes[`${i}:${p.id}`] ?? "not applied yet"}`);
    return `\n\n[Proposal outcomes: ${parts.join("; ")}]`;
  };

  const mut = useMutation({
    mutationFn: (q: string) => {
      const history = turns.flatMap((t, i) =>
        t.answer
          ? [
              { role: "user" as const, content: t.question },
              { role: "assistant" as const, content: t.answer.reply + outcomeNote(t, i) },
            ]
          : [],
      );
      return askCopilot(project, q, history);
    },
    onSuccess: (a) => setTurns((t) => [...t.slice(0, -1), { ...t[t.length - 1], answer: a }]),
    onError: (e) =>
      setTurns((t) => [...t.slice(0, -1), { ...t[t.length - 1], error: (e as Error).message }]),
    onSettled: () => setTimeout(() => endRef.current?.scrollIntoView({ behavior: "smooth" }), 50),
  });

  const ask = (q?: string) => {
    const text = (q ?? question).trim();
    if (!text || mut.isPending) return;
    setTurns((t) => [...t, { question: text }]);
    setQuestion("");
    mut.mutate(text);
  };

  if (health.data && !health.data.copilot_configured) return <NotConfigured panel={panel} />;

  return (
    <div className={panel ? "flex min-h-full flex-col" : "mx-auto max-w-[860px]"}>
      {!panel && (
        <>
          <H1>AI Copilot</H1>
          <p className="m-0 mt-[5px] text-[12.5px] text-muted">
            An agent over your live Azure DevOps data. It reads freely; every change it wants to make
            comes back as a proposal you apply.
          </p>
        </>
      )}
      <FreshnessBar />

      {/* -------- session history bar -------- */}
      {((sessions.data?.value ?? []).length > 0 || turns.length > 0) && (
        <div className="mt-[10px] flex flex-wrap items-center gap-[6px]">
          <button
            onClick={newChat}
            className={`rounded-[7px] border px-[10px] py-[4px] text-[11.5px] ${
              sessionId === null && turns.length === 0
                ? "border-ink-bg bg-ink-bg font-semibold text-ink-fg"
                : "border-border bg-surface font-medium text-text-3 hover:border-faint"
            }`}
          >
            + New chat
          </button>
          {(sessions.data?.value ?? []).slice(0, 8).map((s) => (
            <span
              key={s.id}
              className={`group flex items-center gap-[6px] rounded-[7px] border px-[10px] py-[4px] text-[11.5px] ${
                s.id === sessionId
                  ? "border-ink-bg bg-ink-bg font-semibold text-ink-fg"
                  : "border-border bg-surface font-medium text-text-3 hover:border-faint"
              }`}
            >
              <button onClick={() => restore(s.id)} className="max-w-[180px] truncate" title={s.title}>
                {s.title}
              </button>
              <button
                onClick={() => removeSession(s.id)}
                title="Delete this chat"
                className={`${s.id === sessionId ? "text-ink-fg" : "text-faint"} opacity-40 hover:opacity-100`}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}

      {turns.length === 0 && (
        <div className={`mt-6 grid gap-2 ${panel ? "grid-cols-1" : "grid-cols-2"}`}>
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              onClick={() => ask(s)}
              className="rounded-[7px] border border-border bg-surface px-[13px] py-[9px] text-left text-[12px] text-text-3 hover:border-faint"
            >
              {s}
            </button>
          ))}
        </div>
      )}

      <div className={`mt-5 space-y-5 ${panel ? "flex-1" : ""}`}>
        {turns.map((t, i) => (
          <TurnView
            key={i}
            turn={t}
            project={project}
            pending={mut.isPending && i === turns.length - 1}
            outcomes={outcomes}
            turnIndex={i}
            onOutcome={(pid, v) => setOutcomes((o) => ({ ...o, [`${i}:${pid}`]: v }))}
          />
        ))}
        <div ref={endRef} />
      </div>

      <div className="sticky bottom-0 mt-5 flex items-center gap-[10px] rounded-[10px] border border-border bg-surface p-[10px_12px]">
        <span className="text-accent">
          <Spark size={15} />
        </span>
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && ask()}
          placeholder="Ask, or tell it what to change…"
          disabled={mut.isPending}
          className="w-full border-none bg-transparent text-[13px] text-text outline-none placeholder:text-faint disabled:opacity-60"
        />
        <button
          onClick={() => ask()}
          disabled={mut.isPending || !question.trim()}
          className="rounded-[7px] bg-accent px-[16px] py-[8px] text-[12px] font-semibold text-white hover:bg-accent-hover disabled:opacity-50"
        >
          Send
        </button>
      </div>
    </div>
  );
}

function NotConfigured({ panel = false }: { panel?: boolean }) {
  return (
    <div className={panel ? "" : "mx-auto max-w-[860px]"}>
      {!panel && <H1>AI Copilot</H1>}
      <Card className="mt-5 p-6">
        <div className="text-[13px] font-semibold text-text">The copilot isn’t set up yet</div>
        <p className="mt-1 text-[12.5px] text-muted">
          Set the <code className="font-mono">ado/copilot_endpoint</code> secret to a Databricks
          FMAPI chat endpoint name (e.g. <code className="font-mono">databricks-llama-4-maverick</code>),
          and optionally <code className="font-mono">ado/mlflow_experiment_id</code> for tracing.
          See AGENTS.md — no redeploy needed.
        </p>
      </Card>
    </div>
  );
}

function TurnView({
  turn,
  project,
  pending,
  outcomes,
  turnIndex,
  onOutcome,
}: {
  turn: Turn;
  project: string;
  pending: boolean;
  outcomes: Record<string, string>;
  turnIndex: number;
  onOutcome: (pid: string, v: string) => void;
}) {
  return (
    <div>
      <div className="flex justify-end">
        <span className="max-w-[80%] rounded-[10px] bg-ink-bg px-[14px] py-[8px] text-[13px] text-ink-fg">
          {turn.question}
        </span>
      </div>
      <div className="mt-3">
        {pending && <p className="m-0 animate-pulse text-[12.5px] text-faint">Working — reading your project…</p>}
        {turn.error && <p className="m-0 text-[12.5px] text-danger">{turn.error}</p>}
        {turn.answer && (
          <AnswerView
            a={turn.answer}
            project={project}
            outcomes={outcomes}
            turnIndex={turnIndex}
            onOutcome={onOutcome}
          />
        )}
      </div>
    </div>
  );
}

function AnswerView({
  a,
  project,
  outcomes,
  turnIndex,
  onOutcome,
}: {
  a: CopilotReply;
  project: string;
  outcomes: Record<string, string>;
  turnIndex: number;
  onOutcome: (pid: string, v: string) => void;
}) {
  return (
    <Card className="space-y-3 p-[14px_16px]">
      {a.toolCalls.length > 0 && (
        <div className="flex flex-wrap gap-[5px]">
          {a.toolCalls.map((t, i) => (
            <span key={i} className="rounded-[5px] bg-nbg px-[7px] py-[2px] font-mono text-[10.5px] text-nfg" title={JSON.stringify(t.args)}>
              read: {t.name}
            </span>
          ))}
        </div>
      )}
      <p className="m-0 whitespace-pre-wrap text-[13px] text-text">{a.reply}</p>
      {(a.tables ?? []).length > 0 && (
        <div className="flex flex-wrap gap-[6px]">
          {(a.tables ?? []).map((t, i) => (
            <button
              key={i}
              onClick={() => downloadTableXlsx(t).catch(() => {})}
              title={`${t.rows.length} rows`}
              className="rounded-[7px] border border-border bg-surface px-[10px] py-[4px] text-[11.5px] font-medium text-text-3 hover:border-faint"
            >
              ⇩ {t.name}.xlsx
            </button>
          ))}
        </div>
      )}
      {a.proposals.map((p) => (
        <ProposalCard
          key={p.id}
          p={p}
          project={project}
          outcome={outcomes[`${turnIndex}:${p.id}`]}
          onOutcome={(v) => onOutcome(p.id, v)}
        />
      ))}
    </Card>
  );
}

/** One proposed file in a code-change proposal — path + size, content behind a toggle. */
function FileEditRow({ edit }: { edit: { path: string; content: string } }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-t border-line py-[4px] first:border-t-0">
      <button onClick={() => setOpen((o) => !o)} className="flex w-full items-center gap-[8px] text-left">
        <span className="min-w-0 flex-1 truncate font-mono text-[11.5px] text-text-2">{edit.path}</span>
        <span className="flex-none font-mono text-[10.5px] text-faint">
          {edit.content.split("\n").length} lines · {open ? "hide" : "view"}
        </span>
      </button>
      {open && (
        <pre className="mt-[4px] max-h-[260px] overflow-auto rounded-[6px] bg-surface-2 p-[8px] font-mono text-[11px] leading-[1.5] text-text-2">
          {edit.content}
        </pre>
      )}
    </div>
  );
}

const FIELD_LABELS: Record<string, string> = {
  type: "Type",
  title: "Title",
  description: "Description",
  assignedTo: "Assignee",
  state: "State",
  tags: "Tags",
  iterationPath: "Iteration",
  text: "Comment",
  comment: "Comment",
  prId: "PR",
  path: "File",
  line: "Line",
};

// Args that are plumbing, not content — hidden from the proposal card table.
const HIDDEN_ARGS = new Set(["repositoryId"]);

function proposalTitle(p: CopilotProposal): string {
  const a = p.args;
  if (p.tool === "create_work_item") return `Create ${a.type ?? "work item"}: ${a.title ?? ""}`;
  if (p.tool === "update_work_item") return `Update work item #${a.id}`;
  if (p.tool === "add_work_item_comment") return `Comment on #${a.id}`;
  if (p.tool === "comment_on_pr") return `Comment on PR !${a.prId}`;
  if (p.tool === "comment_on_pr_file") return `Comment on ${a.path}:${a.line} in PR !${a.prId}`;
  if (p.tool === "create_code_pr") {
    const n = Array.isArray(a.edits) ? a.edits.length : 0;
    return `Code change PR: ${a.title ?? ""} (${n} file${n === 1 ? "" : "s"} → ${a.baseBranch})`;
  }
  return p.tool;
}

function ProposalCard({
  p,
  project,
  outcome,
  onOutcome,
}: {
  p: CopilotProposal;
  project: string;
  outcome?: string;
  onOutcome: (v: string) => void;
}) {
  const qc = useQueryClient();
  const toast = useToast();
  // "failed: …" keeps the buttons so the user can retry.
  const status = outcome === "applied" ? "applied" : outcome === "dismissed" ? "dismissed" : "pending";

  const apply = useMutation({
    mutationFn: async () => {
      const a = p.args as Record<string, string | number | undefined>;
      if (p.tool === "create_work_item") {
        const body: WorkItemCreatePayload = {
          type: String(a.type),
          title: String(a.title),
          ...(a.description ? { description: textToHtml(String(a.description)) } : {}),
          ...(a.assignedTo ? { assignedTo: String(a.assignedTo) } : {}),
          ...(a.tags ? { tags: String(a.tags) } : {}),
          ...(a.iterationPath ? { iterationPath: String(a.iterationPath) } : {}),
        };
        return createWorkItem(project, body);
      }
      if (p.tool === "update_work_item") {
        const body: WorkItemUpdatePayload = {};
        if (a.title !== undefined) body.title = String(a.title);
        if (a.description !== undefined) body.description = textToHtml(String(a.description));
        if (a.assignedTo !== undefined) body.assignedTo = String(a.assignedTo);
        if (a.state !== undefined) body.state = String(a.state);
        if (a.tags !== undefined) body.tags = String(a.tags);
        if (a.iterationPath !== undefined) body.iterationPath = String(a.iterationPath);
        return updateWorkItem(project, Number(a.id), body);
      }
      if (p.tool === "add_work_item_comment") {
        return addWorkItemComment(project, Number(a.id), String(a.text));
      }
      if (p.tool === "comment_on_pr" || p.tool === "comment_on_pr_file") {
        return createPrThread(project, String(a.repositoryId), Number(a.prId), {
          comment: String(a.comment),
          ...(p.tool === "comment_on_pr_file"
            ? { filePath: String(a.path), line: Number(a.line) }
            : {}),
        });
      }
      if (p.tool === "create_code_pr") {
        return createCodePr(project, String(a.repositoryId), {
          baseBranch: String(a.baseBranch),
          title: String(a.title),
          description: a.description ? String(a.description) : undefined,
          edits: (p.args.edits as { path: string; content: string }[]) ?? [],
        });
      }
      throw new Error(`Unknown proposal type: ${p.tool}`);
    },
    onSuccess: (d: unknown) => {
      onOutcome("applied");
      qc.invalidateQueries({ queryKey: ["workitems", project] });
      if (p.tool.startsWith("comment_on_pr")) {
        qc.invalidateQueries({
          queryKey: ["prthreads", project, String(p.args.repositoryId), Number(p.args.prId)],
        });
      }
      if (p.tool === "create_code_pr") {
        const pr = d as { prId?: number; branch?: string };
        toast(pr?.prId ? `PR !${pr.prId} opened from ${pr.branch}` : "PR opened");
        qc.invalidateQueries({ queryKey: ["prs", project] });
        return;
      }
      const created = d as { id?: number };
      toast(p.tool === "create_work_item" && created?.id ? `#${created.id} created` : "Applied");
    },
    onError: (e) => onOutcome(`failed: ${(e as Error).message}`),
  });

  const rows = Object.entries(p.args).filter(
    ([k]) =>
      !HIDDEN_ARGS.has(k) &&
      k !== "edits" && // file contents render as a compact list below, never inline
      (k !== "id" || p.tool === "update_work_item"),
  );
  const edits = Array.isArray(p.args.edits)
    ? (p.args.edits as { path: string; content: string }[])
    : [];

  return (
    <div className="rounded-[8px] border border-accent-border bg-accent-tint p-[12px_14px]">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-[12.5px] font-semibold text-accent-text">{proposalTitle(p)}</span>
        {status === "applied" && (
          <span className="rounded-[20px] bg-ok-bg px-[9px] py-[2px] text-[11px] font-semibold text-ok">applied</span>
        )}
        {status === "dismissed" && (
          <span className="rounded-[20px] bg-nbg px-[9px] py-[2px] text-[11px] font-semibold text-nfg">dismissed</span>
        )}
      </div>
      <table className="w-full text-[12px]">
        <tbody>
          {rows.map(([k, v]) => (
            <tr key={k}>
              <td className="w-[92px] py-[2px] pr-2 align-top font-semibold text-text-3">{FIELD_LABELS[k] ?? k}</td>
              <td className="whitespace-pre-wrap py-[2px] text-text-2">{String(v)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {edits.length > 0 && (
        <div className="mt-[6px]">
          <div className="text-[10.5px] font-semibold uppercase tracking-[0.5px] text-faint">Files</div>
          {edits.map((e) => (
            <FileEditRow key={e.path} edit={e} />
          ))}
        </div>
      )}
      {apply.isError && <div className="mt-2 text-[11.5px] text-danger">{(apply.error as Error).message}</div>}
      {status === "pending" && (
        <div className="mt-[10px] flex gap-[8px]">
          <button
            onClick={() => apply.mutate()}
            disabled={apply.isPending}
            className="rounded-[7px] bg-accent px-[14px] py-[6px] text-[12px] font-semibold text-white hover:bg-accent-hover disabled:opacity-50"
          >
            {apply.isPending ? "Applying…" : "Apply"}
          </button>
          <button
            onClick={() => onOutcome("dismissed")}
            className="rounded-[7px] border border-border bg-surface px-[12px] py-[6px] text-[12px] font-medium text-text-3 hover:bg-hover"
          >
            Dismiss
          </button>
        </div>
      )}
    </div>
  );
}
