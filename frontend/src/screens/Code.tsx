import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { explainFile, fetchBranches, fetchCommits, fetchFile, fetchRepos, fetchTree } from "../api";
import { Card, Empty, ErrorMsg, H1, Loading, SectionLabel, relTime } from "../components/ui";
import { Select } from "../components/Drawer";
import { AIButton, useCopilotConfigured } from "../components/AIButton";
import { IconChevron, IconX } from "../components/icons";
import CodeBlock from "../components/CodeBlock";
import { renderMarkdown } from "../lib/markdown";

const DOTS = ["bg-accent", "bg-info", "bg-purple", "bg-ok", "bg-warn"];

export default function Code({
  project,
  fileTarget,
}: {
  project: string;
  fileTarget?: { repoId: string; branch: string; path: string } | null;
}) {
  const repos = useQuery({ queryKey: ["repos", project], queryFn: () => fetchRepos(project) });
  const [repoId, setRepoId] = useState<string | null>(null);
  const [branch, setBranch] = useState<string | null>(null);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);

  useEffect(() => {
    if (!repoId && repos.data?.value.length) setRepoId(repos.data.value[0].id);
  }, [repos.data, repoId]);

  // deep link from the header search — a fresh object per pick re-triggers this
  useEffect(() => {
    if (!fileTarget) return;
    setRepoId(fileTarget.repoId);
    setBranch(fileTarget.branch);
    setSelectedPath(fileTarget.path);
  }, [fileTarget]);

  const commits = useQuery({
    queryKey: ["commits", project, repoId],
    queryFn: () => fetchCommits(project, repoId!),
    enabled: !!repoId,
  });

  const branches = useQuery({
    queryKey: ["branches", project, repoId],
    queryFn: () => fetchBranches(project, repoId!),
    enabled: !!repoId,
    staleTime: 60_000,
  });

  const selected = repos.data?.value.find((r) => r.id === repoId);
  const effBranch = branch ?? selected?.defaultBranch ?? "";
  const branchNames = branches.data?.value.map((b) => b.name) ?? [];

  const pickRepo = (id: string) => {
    setRepoId(id);
    setBranch(null);
    setSelectedPath(null);
  };

  // panes collapse so the viewer can take the full width
  const [reposOpen, setReposOpen] = useState(true);
  const [treeOpen, setTreeOpen] = useState(true);
  const cols = `${reposOpen ? "220px" : "30px"} ${treeOpen ? "280px" : "30px"} minmax(0,1fr)`;

  return (
    <div>
      <H1>Code</H1>
      <div className="mt-4 grid gap-[16px]" style={{ gridTemplateColumns: cols }}>
        {/* pane 1: repos */}
        {!reposOpen ? (
          <CollapsedRail label="Repositories" onExpand={() => setReposOpen(true)} />
        ) : (
        <div>
          <PaneHeader label="Repositories" onCollapse={() => setReposOpen(false)} />
          {repos.isLoading && <Loading />}
          {repos.isError && <ErrorMsg error={repos.error} />}
          <div className="flex flex-col gap-[3px]">
            {repos.data?.value.map((r, i) => {
              const on = r.id === repoId;
              return (
                <button
                  key={r.id}
                  onClick={() => pickRepo(r.id)}
                  className={`flex w-full items-center justify-between rounded-[8px] border px-[11px] py-[9px] text-left ${
                    on ? "border-accent-border bg-accent-tint" : "border-border bg-surface"
                  }`}
                >
                  <span className={`flex items-center gap-2 text-[13px] ${on ? "font-semibold text-accent-text" : "font-medium text-text"}`}>
                    <span className={`h-2 w-2 rounded-[2px] ${DOTS[i % DOTS.length]}`} />
                    {r.name}
                  </span>
                </button>
              );
            })}
          </div>
          {selected && (
            <Card className="mt-4 p-[12px]">
              <div className="text-[11px] text-muted">Default branch</div>
              <div className="mt-[4px] font-mono text-[12px] text-text">{selected.defaultBranch || "—"}</div>
            </Card>
          )}
        </div>
        )}

        {/* pane 2: branch + tree */}
        {!treeOpen ? (
          <CollapsedRail label="Files" onExpand={() => setTreeOpen(true)} />
        ) : (
        <div className="min-w-0">
          <PaneHeader label="Branch" onCollapse={() => setTreeOpen(false)} />
          <Select
            value={effBranch}
            onChange={(b) => {
              setBranch(b);
              setSelectedPath(null);
            }}
            options={branchNames.length ? branchNames : [effBranch].filter(Boolean)}
          />
          <SectionLabel className="mb-2 mt-4">Files</SectionLabel>
          <Card className="max-h-[560px] overflow-y-auto py-[6px]">
            {repoId && effBranch ? (
              <TreeLevel
                project={project}
                repoId={repoId}
                branch={effBranch}
                path="/"
                depth={0}
                selectedPath={selectedPath}
                onSelect={setSelectedPath}
              />
            ) : (
              <Loading />
            )}
          </Card>
        </div>
        )}

        {/* pane 3: file viewer, or commits when nothing is selected */}
        {selectedPath && repoId ? (
          <FileViewer
            project={project}
            repoId={repoId}
            branch={effBranch}
            path={selectedPath}
            onClose={() => setSelectedPath(null)}
          />
        ) : (
          <Card className="overflow-hidden self-start">
            <div className="flex items-center justify-between border-b border-border-2 px-[18px] py-[13px]">
              <div className="text-[13px] font-semibold text-text">Recent commits</div>
              <div className="font-mono text-[11px] text-faint">{selected?.name}</div>
            </div>
            {commits.isLoading && <Loading />}
            {commits.isError && <ErrorMsg error={commits.error} />}
            {commits.data?.value.map((c) => (
              <div key={c.commitId} className="flex items-center gap-3 border-t border-line px-[18px] py-[11px] hover:bg-hover">
                <span className="flex-none rounded-[6px] bg-purple-bg px-[8px] py-[3px] font-mono text-[11px] font-semibold text-purple">
                  {c.shortId}
                </span>
                <span className="min-w-0 flex-1 truncate text-[13px] text-text">{c.comment}</span>
                <span className="w-[80px] flex-none text-right text-[12px] text-text-3">{c.author ?? "—"}</span>
                <span className="w-[44px] flex-none text-right font-mono text-[11px] text-faint">{relTime(c.date)}</span>
              </div>
            ))}
            {commits.data?.value.length === 0 && <Empty>No commits.</Empty>}
          </Card>
        )}
      </div>
    </div>
  );
}

// ---- collapsible pane chrome -------------------------------------------------------

function PaneHeader({ label, onCollapse }: { label: string; onCollapse: () => void }) {
  return (
    <div className="mb-2 flex items-center justify-between">
      <SectionLabel>{label}</SectionLabel>
      <button
        onClick={onCollapse}
        title={`Collapse ${label.toLowerCase()}`}
        className="rounded-[5px] border border-border bg-surface px-[6px] py-[1px] font-mono text-[11px] text-faint hover:text-text-3"
      >
        «
      </button>
    </div>
  );
}

function CollapsedRail({ label, onExpand }: { label: string; onExpand: () => void }) {
  return (
    <button
      onClick={onExpand}
      title={`Expand ${label.toLowerCase()}`}
      className="flex h-full min-h-[220px] w-[30px] flex-col items-center gap-[8px] rounded-[8px] border border-border bg-surface pt-[10px] text-faint hover:border-faint hover:text-text-3"
    >
      <span className="font-mono text-[11px]">»</span>
      <span
        className="text-[10px] font-semibold uppercase tracking-[0.8px]"
        style={{ writingMode: "vertical-rl" }}
      >
        {label}
      </span>
    </button>
  );
}

// ---- file tree (lazy: one OneLevel query per expanded folder) ---------------------

function TreeLevel({
  project,
  repoId,
  branch,
  path,
  depth,
  selectedPath,
  onSelect,
}: {
  project: string;
  repoId: string;
  branch: string;
  path: string;
  depth: number;
  selectedPath: string | null;
  onSelect: (p: string) => void;
}) {
  const q = useQuery({
    queryKey: ["tree", project, repoId, branch, path],
    queryFn: () => fetchTree(project, repoId, branch, path),
    staleTime: 60_000,
  });
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  if (q.isLoading) return <div className="px-[14px] py-[6px] text-[12px] text-faint">Loading…</div>;
  if (q.isError) return <div className="px-[14px] py-[6px] text-[12px] text-danger">Couldn’t load tree</div>;
  if (!q.data?.value.length && depth === 0) return <Empty>Empty repository.</Empty>;

  const toggle = (p: string) =>
    setExpanded((s) => {
      const next = new Set(s);
      if (next.has(p)) next.delete(p);
      else next.add(p);
      return next;
    });

  return (
    <>
      {q.data?.value.map((e) => (
        <div key={e.path}>
          <button
            onClick={() => (e.isFolder ? toggle(e.path) : onSelect(e.path))}
            style={{ paddingLeft: 14 + depth * 14 }}
            className={`flex w-full items-center gap-[6px] py-[4px] pr-[10px] text-left text-[12.5px] hover:bg-hover ${
              e.path === selectedPath ? "bg-accent-tint font-semibold text-accent-text" : "text-text-2"
            }`}
          >
            {e.isFolder ? (
              <span className={`text-faint transition-transform ${expanded.has(e.path) ? "" : "-rotate-90"}`}>
                <IconChevron size={10} />
              </span>
            ) : (
              <span className="w-[10px]" />
            )}
            <span className={`truncate ${e.isFolder ? "font-medium text-text" : "font-mono text-[12px]"}`}>
              {e.name}
            </span>
          </button>
          {e.isFolder && expanded.has(e.path) && (
            <TreeLevel
              project={project}
              repoId={repoId}
              branch={branch}
              path={e.path}
              depth={depth + 1}
              selectedPath={selectedPath}
              onSelect={onSelect}
            />
          )}
        </div>
      ))}
    </>
  );
}

// ---- file viewer -------------------------------------------------------------------

function FileViewer({
  project,
  repoId,
  branch,
  path,
  onClose,
}: {
  project: string;
  repoId: string;
  branch: string;
  path: string;
  onClose: () => void;
}) {
  const q = useQuery({
    queryKey: ["file", project, repoId, branch, path],
    queryFn: () => fetchFile(project, repoId, path, branch),
    staleTime: 60_000,
  });

  const isMarkdown = path.toLowerCase().endsWith(".md");
  const [preview, setPreview] = useState(false);
  const aiOn = useCopilotConfigured();
  const explain = useMutation({
    mutationFn: () => explainFile(project, repoId, path, branch),
  });

  // new file = fresh state
  useEffect(() => {
    setPreview(false);
    explain.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, branch]);

  return (
    <Card className="min-w-0 self-start overflow-hidden">
      <div className="flex items-center justify-between gap-[10px] border-b border-border-2 px-[18px] py-[11px]">
        <span className="min-w-0 truncate font-mono text-[12px] text-text">{path}</span>
        <div className="flex flex-none items-center gap-[8px]">
          {isMarkdown && (
            <button
              onClick={() => setPreview((p) => !p)}
              className={`rounded-[6px] border px-[9px] py-[3px] text-[11px] font-semibold ${
                preview
                  ? "border-accent-border bg-accent-tint text-accent-text"
                  : "border-border bg-surface text-text-3 hover:bg-hover"
              }`}
            >
              {preview ? "Code" : "Preview"}
            </button>
          )}
          {aiOn && (
            <AIButton
              label="Explain"
              busy={explain.isPending}
              disabled={q.data?.binary}
              onClick={() => explain.mutate()}
            />
          )}
          <span className="font-mono text-[11px] text-faint">{branch}</span>
          <button
            onClick={onClose}
            className="rounded-[6px] border border-border bg-surface px-[8px] py-[3px] text-[11px] font-medium text-text-3 hover:bg-hover"
          >
            ← Commits
          </button>
        </div>
      </div>

      {explain.isError && (
        <div className="border-b border-line px-[18px] py-[8px]">
          <ErrorMsg error={explain.error} />
        </div>
      )}
      {explain.data && (
        <div className="border-b border-accent-border bg-accent-tint px-[18px] py-[10px]">
          <div className="mb-[4px] flex items-center justify-between">
            <span className="text-[11px] font-semibold uppercase tracking-[0.5px] text-accent-text">
              What this file is
            </span>
            <button onClick={() => explain.reset()} className="text-faint hover:text-text-3" title="Dismiss">
              <IconX size={12} />
            </button>
          </div>
          <p className="m-0 text-[12.5px] leading-[1.55] text-text">{explain.data.explanation}</p>
          {explain.data.keyPoints && (
            <ul className="mb-0 mt-[6px] list-disc pl-[18px] text-[12px] text-text-2">
              {explain.data.keyPoints
                .split("\n")
                .map((l) => l.replace(/^\s*-\s*/, "").trim())
                .filter(Boolean)
                .map((l, i) => (
                  <li key={i}>{l}</li>
                ))}
            </ul>
          )}
        </div>
      )}

      {q.isLoading && <Loading />}
      {q.isError && <ErrorMsg error={q.error} />}
      {q.data?.binary && <Empty>Binary file — no preview.</Empty>}
      {q.data && !q.data.binary && (
        <>
          {q.data.truncated && (
            <div className="border-b border-line bg-warn-bg px-[18px] py-[6px] text-[11.5px] text-warn">
              Large file — showing the first part only.
            </div>
          )}
          {isMarkdown && preview ? (
            <div
              className="md-preview p-[16px_20px]"
              dangerouslySetInnerHTML={{ __html: renderMarkdown(q.data.content) }}
            />
          ) : (
            <div className="overflow-x-auto p-[14px_0_14px_14px]">
              <CodeBlock content={q.data.content} path={path} />
            </div>
          )}
        </>
      )}
    </Card>
  );
}
