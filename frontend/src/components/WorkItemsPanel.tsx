import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { addWorkItemComment, fetchWorkItems, setWorkItemState, type WorkItem } from "../api";
import { Empty, ErrorMsg, Loading, relTime, Badge } from "./ui";

// Common states across Agile/Scrum/Basic processes; the item's current state is
// always included so we never lose it even for custom processes.
const COMMON_STATES = ["New", "To Do", "Active", "Doing", "Resolved", "Done", "Closed", "Removed"];

export default function WorkItemsPanel({ project }: { project: string }) {
  const q = useQuery({
    queryKey: ["workitems", project],
    queryFn: () => fetchWorkItems(project),
  });

  if (q.isLoading) return <Loading />;
  if (q.isError) return <ErrorMsg error={q.error} />;
  const items = q.data?.value ?? [];
  if (!items.length) return <Empty>No work items.</Empty>;

  return (
    <ul className="divide-y divide-slate-100">
      {items.map((wi) => (
        <WorkItemRow key={wi.id} project={project} wi={wi} />
      ))}
    </ul>
  );
}

function WorkItemRow({ project, wi }: { project: string; wi: WorkItem }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const invalidate = () => qc.invalidateQueries({ queryKey: ["workitems", project] });

  const stateMut = useMutation({
    mutationFn: (state: string) => setWorkItemState(project, wi.id, state),
    onSuccess: invalidate,
  });

  const states = Array.from(new Set([wi.state, ...COMMON_STATES])).filter(Boolean);

  return (
    <li className="py-2.5">
      <div className="flex items-center gap-3">
        <span className="w-14 shrink-0 text-xs text-slate-400">#{wi.id}</span>
        <span className="w-24 shrink-0 text-xs text-slate-500">{wi.type}</span>
        <span className="flex-1 truncate text-sm text-slate-800" title={wi.title}>
          {wi.title}
        </span>

        <select
          value={wi.state}
          disabled={stateMut.isPending}
          onChange={(e) => stateMut.mutate(e.target.value)}
          className="rounded-md border border-slate-200 bg-white px-2 py-1 text-xs text-slate-700 disabled:opacity-50"
          title="Change state"
        >
          {states.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>

        <span className="w-28 shrink-0 truncate text-right text-xs text-slate-500">
          {wi.assignedTo ?? "Unassigned"}
        </span>
        <button
          onClick={() => setOpen((o) => !o)}
          className="shrink-0 rounded-md px-2 py-1 text-xs text-slate-500 hover:bg-slate-100"
          title="Add comment"
        >
          💬
        </button>
        <span className="w-16 shrink-0 text-right text-xs text-slate-400">
          {relTime(wi.changedDate)}
        </span>
      </div>

      {stateMut.isError && (
        <p className="ml-14 mt-1 text-xs text-rose-600">{(stateMut.error as Error).message}</p>
      )}

      {open && <CommentComposer project={project} workItemId={wi.id} onDone={() => setOpen(false)} />}
    </li>
  );
}

function CommentComposer({
  project,
  workItemId,
  onDone,
}: {
  project: string;
  workItemId: number;
  onDone: () => void;
}) {
  const [text, setText] = useState("");
  const mut = useMutation({
    mutationFn: (t: string) => addWorkItemComment(project, workItemId, t),
    onSuccess: () => {
      setText("");
      onDone();
    },
  });

  return (
    <div className="ml-14 mt-2 flex items-start gap-2">
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Add a comment…"
        rows={2}
        className="flex-1 rounded-md border border-slate-200 px-2.5 py-1.5 text-sm focus:border-indigo-400 focus:outline-none"
      />
      <div className="flex flex-col gap-1">
        <button
          onClick={() => text.trim() && mut.mutate(text.trim())}
          disabled={mut.isPending || !text.trim()}
          className="rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50"
        >
          {mut.isPending ? "…" : "Send"}
        </button>
        {mut.isError && <Badge tone="red">failed</Badge>}
      </div>
    </div>
  );
}
