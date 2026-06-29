import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { addWorkItemComment, fetchWorkItems, setWorkItemState, type WorkItem } from "../api";
import { Card, Empty, ErrorMsg, H1, Loading, relTime } from "../components/ui";
import { IconChevron, IconComment, IconSearch } from "../components/icons";
import { stateChip, typeDot } from "../lib/tokens";
import { useToast } from "../components/Toast";

const STATES = ["New", "To Do", "Active", "Doing", "Resolved", "Done", "Closed", "Removed"];
const isActive = (s: string) => ["active", "doing"].includes((s ?? "").toLowerCase());
const isNew = (s: string) => ["new", "to do"].includes((s ?? "").toLowerCase());

type Filter = "All" | "Active" | "New" | "Mine";
const FILTERS: Filter[] = ["All", "Active", "New", "Mine"];

export default function WorkItems({ project, me }: { project: string; me: string | null }) {
  const q = useQuery({ queryKey: ["workitems", project], queryFn: () => fetchWorkItems(project) });
  const [filter, setFilter] = useState<Filter>("All");
  const [search, setSearch] = useState("");
  const [composerFor, setComposerFor] = useState<WorkItem | null>(null);

  const items = q.data?.value ?? [];
  const counts = useMemo(
    () => ({
      All: items.length,
      Active: items.filter((i) => isActive(i.state)).length,
      New: items.filter((i) => isNew(i.state)).length,
      Mine: items.filter((i) => i.assignedTo && i.assignedTo === me).length,
    }),
    [items, me],
  );

  const rows = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return items.filter((i) => {
      if (filter === "Active" && !isActive(i.state)) return false;
      if (filter === "New" && !isNew(i.state)) return false;
      if (filter === "Mine" && i.assignedTo !== me) return false;
      if (needle && !(i.title ?? "").toLowerCase().includes(needle)) return false;
      return true;
    });
  }, [items, filter, search, me]);

  return (
    <div>
      <H1>Work Items</H1>

      <div className="mb-[14px] mt-4 flex items-center justify-between gap-3">
        <div className="flex gap-[6px]">
          {FILTERS.map((f) => {
            const on = filter === f;
            return (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`rounded-[7px] border px-[13px] py-[6px] text-[12px] ${
                  on ? "border-ink-bg bg-ink-bg font-semibold text-ink-fg" : "border-border bg-surface font-medium text-text-3 hover:border-faint"
                }`}
              >
                {f} <span className="font-mono opacity-70">{counts[f]}</span>
              </button>
            );
          })}
        </div>
        <div className="flex items-center gap-2">
          <div className="flex h-[32px] w-[200px] items-center gap-2 rounded-[7px] border border-border bg-surface px-[11px]">
            <span className="text-faint">
              <IconSearch size={13} />
            </span>
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Filter by title…"
              className="w-full border-none bg-transparent text-[12.5px] text-text outline-none placeholder:text-faint"
            />
          </div>
          <button className="rounded-[7px] bg-accent px-[14px] py-[7px] text-[12px] font-semibold text-white hover:bg-accent-hover">
            + New item
          </button>
        </div>
      </div>

      {q.isLoading && <Loading />}
      {q.isError && <ErrorMsg error={q.error} />}

      {q.data && (
        <Card className="overflow-hidden">
          <table className="w-full border-collapse text-[12.5px]">
            <thead>
              <tr className="bg-surface-2 text-[10.5px] uppercase tracking-[0.5px] text-faint">
                <Th className="pl-[18px]">ID</Th>
                <Th>Type</Th>
                <Th>Title</Th>
                <Th className="w-[148px]">State</Th>
                <Th>Assignee</Th>
                <Th>Tags</Th>
                <Th className="pr-[18px] text-right">Updated</Th>
                <th className="w-[36px]" />
              </tr>
            </thead>
            <tbody>
              {rows.map((wi) => (
                <Row key={wi.id} project={project} wi={wi} onComment={() => setComposerFor(wi)} />
              ))}
            </tbody>
          </table>
          {rows.length === 0 && <Empty>No work items match this filter.</Empty>}
        </Card>
      )}

      {composerFor && (
        <Composer project={project} item={composerFor} onClose={() => setComposerFor(null)} />
      )}
    </div>
  );
}

function Th({ children, className = "" }: { children?: React.ReactNode; className?: string }) {
  return <th className={`px-[8px] py-[10px] text-left font-semibold ${className}`}>{children}</th>;
}

function Row({ project, wi, onComment }: { project: string; wi: WorkItem; onComment: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const mut = useMutation({
    mutationFn: (state: string) => setWorkItemState(project, wi.id, state),
    onSuccess: (_d, state) => {
      qc.invalidateQueries({ queryKey: ["workitems", project] });
      toast(`#${wi.id} → ${state}`);
    },
  });
  const states = Array.from(new Set([wi.state, ...STATES])).filter(Boolean) as string[];

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
        <span className="relative inline-flex items-center">
          <select
            value={wi.state}
            disabled={mut.isPending}
            onChange={(e) => mut.mutate(e.target.value)}
            className={`appearance-none rounded-[7px] border border-transparent py-[4px] pl-[9px] pr-[22px] text-[11.5px] font-semibold outline-none disabled:opacity-60 ${stateChip(wi.state)}`}
          >
            {states.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <span className="pointer-events-none absolute right-[7px]">
            <IconChevron size={10} />
          </span>
        </span>
      </td>
      <td className="px-[8px] py-[9px]">
        <span className={wi.assignedTo ? "text-text-3" : "text-faint"}>{wi.assignedTo ?? "Unassigned"}</span>
      </td>
      <td className="px-[8px] py-[9px]" />
      <td className="px-[18px] py-[9px] text-right font-mono text-faint">{relTime(wi.changedDate)}</td>
      <td className="px-[8px] py-[9px] text-center">
        <button onClick={onComment} title="Add comment" className="inline-flex text-faint hover:text-text-3">
          <IconComment size={15} />
        </button>
      </td>
    </tr>
  );
}

function Composer({ project, item, onClose }: { project: string; item: WorkItem; onClose: () => void }) {
  const toast = useToast();
  const [text, setText] = useState("");
  const mut = useMutation({
    mutationFn: (t: string) => addWorkItemComment(project, item.id, t),
    onSuccess: () => {
      toast("Comment added");
      onClose();
    },
  });

  return (
    <Card className="mt-[14px] p-[14px_16px]">
      <div className="mb-2 text-[12px] font-semibold text-text">
        Comment on #{item.id} · {item.title}
      </div>
      <div className="flex items-start gap-[10px]">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Add a comment…"
          rows={2}
          className="flex-1 resize-none rounded-[8px] border border-border bg-surface p-[8px_11px] text-[13px] text-text outline-none placeholder:text-faint"
        />
        <button
          onClick={() => text.trim() && mut.mutate(text.trim())}
          disabled={mut.isPending || !text.trim()}
          className="rounded-[7px] bg-accent px-[16px] py-[8px] text-[12px] font-semibold text-white hover:bg-accent-hover disabled:opacity-50"
        >
          Send
        </button>
        <button
          onClick={onClose}
          className="rounded-[7px] border border-border bg-surface px-[13px] py-[8px] text-[12px] font-medium text-text-3 hover:bg-hover"
        >
          Cancel
        </button>
      </div>
      {mut.isError && <div className="mt-2 text-[11px] text-danger">{(mut.error as Error).message}</div>}
    </Card>
  );
}
