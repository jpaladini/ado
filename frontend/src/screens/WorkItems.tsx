import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  addWorkItemComment,
  createWorkItem,
  fetchHealth,
  fetchIterations,
  fetchWorkItemComments,
  fetchWorkItemDetail,
  fetchWorkItems,
  fetchWorkItemTypes,
  searchIdentities,
  setWorkItemState,
  suggestWorkItem,
  updateWorkItem,
  type Identity,
  type WorkItem,
  type WorkItemSuggestion,
  type WorkItemUpdatePayload,
} from "../api";
import { Card, Empty, ErrorMsg, H1, Loading, relTime } from "../components/ui";
import { Drawer, Field, INPUT, Select } from "../components/Drawer";
import { IconChevron, IconSearch, IconX, Spark } from "../components/icons";
import { stateChip, tagChip, typeDot } from "../lib/tokens";
import { htmlToText, textToHtml } from "../lib/text";
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
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<number | null>(null);

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
          <button
            onClick={() => setCreating(true)}
            className="rounded-[7px] bg-accent px-[14px] py-[7px] text-[12px] font-semibold text-white hover:bg-accent-hover"
          >
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
              </tr>
            </thead>
            <tbody>
              {rows.map((wi) => (
                <Row key={wi.id} project={project} wi={wi} onOpen={() => setEditing(wi.id)} />
              ))}
            </tbody>
          </table>
          {rows.length === 0 && <Empty>No work items match this filter.</Empty>}
        </Card>
      )}

      {creating && <CreateDrawer project={project} onClose={() => setCreating(false)} />}
      {editing !== null && (
        <EditDrawer project={project} id={editing} onClose={() => setEditing(null)} />
      )}
    </div>
  );
}

function Th({ children, className = "" }: { children?: React.ReactNode; className?: string }) {
  return <th className={`px-[8px] py-[10px] text-left font-semibold ${className}`}>{children}</th>;
}

function Row({ project, wi, onOpen }: { project: string; wi: WorkItem; onOpen: () => void }) {
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
    <tr onClick={onOpen} className="cursor-pointer border-t border-line hover:bg-hover">
      <td className="px-[18px] py-[9px] font-mono text-faint">#{wi.id}</td>
      <td className="px-[8px] py-[9px]">
        <span className="inline-flex items-center gap-[6px] text-text-2">
          <span className={`h-2 w-2 rounded-[2px] ${typeDot(wi.type)}`} />
          {wi.type}
        </span>
      </td>
      <td className="px-[8px] py-[9px] font-medium text-text">{wi.title}</td>
      <td className="px-[8px] py-[9px]" onClick={(e) => e.stopPropagation()}>
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
      <td className="px-[8px] py-[9px]">
        <span className="flex flex-wrap gap-[4px]">
          {(wi.tags ?? []).slice(0, 3).map((t) => (
            <span key={t} className={`rounded-[4px] px-[6px] py-[1px] text-[10.5px] font-medium ${tagChip(t)}`}>
              {t}
            </span>
          ))}
        </span>
      </td>
      <td className="px-[18px] py-[9px] text-right font-mono text-faint">{relTime(wi.changedDate)}</td>
    </tr>
  );
}

// ---- AI suggestion button ---------------------------------------------------------

/** Renders next to a Field label; only shown when the copilot endpoint is configured. */
function AIButton({
  label,
  busy,
  disabled,
  onClick,
}: {
  label: string;
  busy: boolean;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={busy || disabled}
      className={`inline-flex items-center gap-[5px] rounded-[6px] border border-border bg-surface px-[8px] py-[3px] text-[11px] font-semibold text-text-3 hover:border-faint hover:text-accent-text disabled:opacity-50 ${busy ? "animate-pulse" : ""}`}
    >
      <span className="text-accent">
        <Spark size={11} />
      </span>
      {busy ? "Thinking…" : label}
    </button>
  );
}

function useCopilotConfigured(): boolean {
  const health = useQuery({ queryKey: ["health"], queryFn: fetchHealth, staleTime: 60_000 });
  return health.data?.copilot_configured === true;
}

/** Merge a suggestion's description + acceptance criteria into one textarea value. */
function suggestionText(s: WorkItemSuggestion): string | null {
  if (!s.description) return null;
  return s.acceptanceCriteria
    ? `${s.description}\n\nAcceptance criteria:\n${s.acceptanceCriteria}`
    : s.description;
}

// ---- assignee picker ------------------------------------------------------------

function AssigneePicker({
  display,
  onPick,
  onClear,
}: {
  display: string | null;
  onPick: (i: Identity) => void;
  onClear: () => void;
}) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<Identity[]>([]);
  const [busy, setBusy] = useState(false);
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => {
    window.clearTimeout(timer.current);
    const needle = q.trim();
    if (needle.length < 2) {
      setResults([]);
      return;
    }
    timer.current = window.setTimeout(() => {
      setBusy(true);
      searchIdentities(needle)
        .then((r) => setResults(r.value))
        .catch(() => setResults([]))
        .finally(() => setBusy(false));
    }, 300);
    return () => window.clearTimeout(timer.current);
  }, [q]);

  if (display) {
    return (
      <span className="inline-flex items-center gap-[7px] rounded-[7px] border border-border bg-bg px-[11px] py-[6px] text-[12.5px] text-text">
        {display}
        <button onClick={onClear} className="text-faint hover:text-danger" title="Unassign" type="button">
          <IconX size={12} />
        </button>
      </span>
    );
  }

  return (
    <div className="relative">
      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Search people…"
        className={INPUT}
      />
      {(busy || results.length > 0) && q.trim().length >= 2 && (
        <div className="absolute left-0 right-0 top-full z-10 mt-[4px] overflow-hidden rounded-[7px] border border-border bg-surface shadow-[0_8px_24px_rgba(0,0,0,.18)]">
          {busy && <div className="px-[11px] py-[7px] text-[12px] text-faint">Searching…</div>}
          {!busy &&
            results.map((r) => (
              <button
                key={r.uniqueName}
                type="button"
                onClick={() => {
                  onPick(r);
                  setQ("");
                  setResults([]);
                }}
                className="block w-full px-[11px] py-[7px] text-left text-[12.5px] text-text hover:bg-hover"
              >
                {r.displayName ?? r.uniqueName}
                <span className="ml-[7px] text-[11px] text-faint">{r.uniqueName}</span>
              </button>
            ))}
        </div>
      )}
    </div>
  );
}

// ---- create ---------------------------------------------------------------------

function CreateDrawer({ project, onClose }: { project: string; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const typesQ = useQuery({
    queryKey: ["witypes", project],
    queryFn: () => fetchWorkItemTypes(project),
    staleTime: 5 * 60_000,
  });
  const iterQ = useQuery({
    queryKey: ["iterations", project],
    queryFn: () => fetchIterations(project),
    staleTime: 5 * 60_000,
  });

  const typeNames = (typesQ.data?.value ?? []).map((t) => t.name);
  const [type, setType] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [assignee, setAssignee] = useState<Identity | null>(null);
  const [tags, setTags] = useState("");
  const [iteration, setIteration] = useState("");
  const effType = type || typeNames[0] || "";
  const aiOn = useCopilotConfigured();

  const suggest = useMutation({
    mutationFn: () => suggestWorkItem({ project, type: effType, title, description }),
    onSuccess: ({ suggestion: s }) => {
      if (s.title) setTitle(s.title);
      const desc = suggestionText(s);
      if (desc) setDescription(desc);
      if (s.tags) setTags(s.tags);
      if (s.type && typeNames.includes(s.type)) setType(s.type);
    },
  });

  const mut = useMutation({
    mutationFn: () =>
      createWorkItem(project, {
        type: effType,
        title: title.trim(),
        ...(description.trim() ? { description: textToHtml(description.trim()) } : {}),
        ...(assignee ? { assignedTo: assignee.uniqueName } : {}),
        ...(tags.trim() ? { tags: tags.split(/[,;]/).map((t) => t.trim()).filter(Boolean).join("; ") } : {}),
        ...(iteration ? { iterationPath: iteration } : {}),
      }),
    onSuccess: (d) => {
      qc.invalidateQueries({ queryKey: ["workitems", project] });
      toast(`#${d.id} created`);
      onClose();
    },
  });

  return (
    <Drawer title="New work item" onClose={onClose}>
      <Field label="Type">
        <Select value={effType} onChange={setType} options={typeNames.length ? typeNames : ["…"]} />
      </Field>
      <Field label="Title">
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="What needs doing?" className={INPUT} autoFocus />
      </Field>
      <Field
        label="Description"
        action={
          aiOn ? (
            <AIButton
              label="Draft with AI"
              busy={suggest.isPending}
              disabled={!title.trim() && !description.trim()}
              onClick={() => suggest.mutate()}
            />
          ) : undefined
        }
      >
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={5}
          placeholder="Details, steps, context…"
          className={`${INPUT} resize-y`}
        />
      </Field>
      {suggest.isError && <ErrorMsg error={suggest.error} />}
      <Field label="Assignee">
        <AssigneePicker
          display={assignee ? assignee.displayName ?? assignee.uniqueName : null}
          onPick={setAssignee}
          onClear={() => setAssignee(null)}
        />
      </Field>
      <Field label="Tags">
        <input value={tags} onChange={(e) => setTags(e.target.value)} placeholder="tag1; tag2" className={INPUT} />
      </Field>
      <Field label="Iteration">
        <Select
          value={iteration || (iterQ.data?.value?.[0] ?? "")}
          onChange={setIteration}
          options={iterQ.data?.value ?? [""]}
        />
      </Field>

      {mut.isError && <ErrorMsg error={mut.error} />}
      <div className="mt-[18px] flex gap-[8px]">
        <button
          onClick={() => mut.mutate()}
          disabled={mut.isPending || !title.trim() || !effType}
          className="rounded-[7px] bg-accent px-[16px] py-[8px] text-[12px] font-semibold text-white hover:bg-accent-hover disabled:opacity-50"
        >
          {mut.isPending ? "Creating…" : "Create"}
        </button>
        <button
          onClick={onClose}
          className="rounded-[7px] border border-border bg-surface px-[13px] py-[8px] text-[12px] font-medium text-text-3 hover:bg-hover"
        >
          Cancel
        </button>
      </div>
    </Drawer>
  );
}

// ---- edit -----------------------------------------------------------------------

function EditDrawer({ project, id, onClose }: { project: string; id: number; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const detailQ = useQuery({
    queryKey: ["workitem", project, id],
    queryFn: () => fetchWorkItemDetail(project, id),
  });
  const commentsQ = useQuery({
    queryKey: ["wicomments", project, id],
    queryFn: () => fetchWorkItemComments(project, id),
  });
  const typesQ = useQuery({
    queryKey: ["witypes", project],
    queryFn: () => fetchWorkItemTypes(project),
    staleTime: 5 * 60_000,
  });
  const iterQ = useQuery({
    queryKey: ["iterations", project],
    queryFn: () => fetchIterations(project),
    staleTime: 5 * 60_000,
  });

  const d = detailQ.data;
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [state, setState] = useState("");
  const [tags, setTags] = useState("");
  const [iteration, setIteration] = useState("");
  // Assignee is tri-state: untouched (keep) / picked / cleared.
  const [assignee, setAssignee] = useState<{ display: string | null; unique: string } | null | "keep">("keep");
  const [loadedRev, setLoadedRev] = useState<number | null>(null);

  useEffect(() => {
    if (d && d.rev !== loadedRev) {
      setTitle(d.title ?? "");
      setDescription(htmlToText(d.description));
      setState(d.state ?? "");
      setTags(d.tags.join("; "));
      setIteration(d.iterationPath ?? "");
      setAssignee("keep");
      setLoadedRev(d.rev);
    }
  }, [d, loadedRev]);

  const aiOn = useCopilotConfigured();
  const suggest = useMutation({
    mutationFn: () => suggestWorkItem({ project, type: d?.type, title, description }),
    onSuccess: ({ suggestion: s }) => {
      const desc = suggestionText(s);
      if (desc) setDescription(desc);
      if (s.tags) setTags(s.tags);
    },
  });

  const typeStates =
    (typesQ.data?.value ?? []).find((t) => t.name === d?.type)?.states.map((s) => s.name) ?? [];
  const stateOptions = Array.from(new Set([d?.state ?? "", ...(typeStates.length ? typeStates : STATES)])).filter(Boolean);

  const save = useMutation({
    mutationFn: () => {
      if (!d) throw new Error("not loaded");
      const patch: WorkItemUpdatePayload = {};
      if (title.trim() && title.trim() !== d.title) patch.title = title.trim();
      if (description.trim() !== htmlToText(d.description)) patch.description = textToHtml(description.trim());
      if (state && state !== d.state) patch.state = state;
      const normTags = tags.split(/[,;]/).map((t) => t.trim()).filter(Boolean).join("; ");
      if (normTags !== d.tags.join("; ")) patch.tags = normTags;
      if (iteration && iteration !== d.iterationPath) patch.iterationPath = iteration;
      if (assignee !== "keep") patch.assignedTo = assignee ? assignee.unique : "";
      if (Object.keys(patch).length === 0) return Promise.resolve(d);
      return updateWorkItem(project, id, patch);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["workitems", project] });
      qc.invalidateQueries({ queryKey: ["workitem", project, id] });
      toast(`#${id} saved`);
    },
  });

  const [comment, setComment] = useState("");
  const commentMut = useMutation({
    mutationFn: (t: string) => addWorkItemComment(project, id, t),
    onSuccess: () => {
      setComment("");
      qc.invalidateQueries({ queryKey: ["wicomments", project, id] });
      toast("Comment added");
    },
  });

  const assigneeDisplay =
    assignee === "keep" ? d?.assignedTo ?? null : assignee ? assignee.display ?? assignee.unique : null;

  return (
    <Drawer
      title={
        <span className="inline-flex items-center gap-[8px]">
          <span className="font-mono text-faint">#{id}</span>
          {d && (
            <span className="inline-flex items-center gap-[6px] text-text-2">
              <span className={`h-2 w-2 rounded-[2px] ${typeDot(d.type)}`} />
              {d.type}
            </span>
          )}
        </span>
      }
      onClose={onClose}
    >
      {detailQ.isLoading && <Loading />}
      {detailQ.isError && <ErrorMsg error={detailQ.error} />}
      {d && (
        <>
          <Field label="Title">
            <input value={title} onChange={(e) => setTitle(e.target.value)} className={INPUT} />
          </Field>
          <Field
            label="Description"
            action={
              aiOn ? (
                <AIButton
                  label="Improve with AI"
                  busy={suggest.isPending}
                  disabled={!title.trim() && !description.trim()}
                  onClick={() => suggest.mutate()}
                />
              ) : undefined
            }
          >
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={5}
              placeholder="No description"
              className={`${INPUT} resize-y`}
            />
          </Field>
          {suggest.isError && <ErrorMsg error={suggest.error} />}
          <div className="grid grid-cols-2 gap-[12px]">
            <Field label="State">
              <Select value={state} onChange={setState} options={stateOptions} />
            </Field>
            <Field label="Iteration">
              <Select value={iteration} onChange={setIteration} options={iterQ.data?.value ?? [iteration]} />
            </Field>
          </div>
          <Field label="Assignee">
            <AssigneePicker
              display={assigneeDisplay}
              onPick={(i) => setAssignee({ display: i.displayName, unique: i.uniqueName })}
              onClear={() => setAssignee(null)}
            />
          </Field>
          <Field label="Tags">
            <input value={tags} onChange={(e) => setTags(e.target.value)} placeholder="tag1; tag2" className={INPUT} />
          </Field>

          <div className="mb-[6px] text-[11px] text-faint">
            Created by {d.createdBy ?? "—"} · {relTime(d.createdDate)} ago · updated {relTime(d.changedDate)} ago
          </div>

          {save.isError && <ErrorMsg error={save.error} />}
          <div className="mt-[10px] flex gap-[8px]">
            <button
              onClick={() => save.mutate()}
              disabled={save.isPending}
              className="rounded-[7px] bg-accent px-[16px] py-[8px] text-[12px] font-semibold text-white hover:bg-accent-hover disabled:opacity-50"
            >
              {save.isPending ? "Saving…" : "Save changes"}
            </button>
            <button
              onClick={onClose}
              className="rounded-[7px] border border-border bg-surface px-[13px] py-[8px] text-[12px] font-medium text-text-3 hover:bg-hover"
            >
              Close
            </button>
          </div>

          <div className="mt-[22px] border-t border-line pt-[14px]">
            <div className="mb-[10px] text-[10.5px] font-semibold uppercase tracking-[0.5px] text-faint">
              Comments {commentsQ.data ? `(${commentsQ.data.value.length})` : ""}
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
            {commentsQ.isLoading && <Loading label="Loading comments…" />}
            {(commentsQ.data?.value ?? []).map((c) => (
              <div key={c.id} className="mb-[10px] rounded-[8px] border border-line bg-bg p-[10px_12px]">
                <div className="mb-[4px] flex items-center justify-between text-[11px]">
                  <span className="font-semibold text-text-2">{c.createdBy ?? "—"}</span>
                  <span className="font-mono text-faint">{relTime(c.createdDate)}</span>
                </div>
                <div className="whitespace-pre-wrap text-[12.5px] text-text-2">{htmlToText(c.text)}</div>
              </div>
            ))}
            {commentsQ.data && commentsQ.data.value.length === 0 && (
              <div className="text-[12px] text-faint">No comments yet.</div>
            )}
          </div>
        </>
      )}
    </Drawer>
  );
}
