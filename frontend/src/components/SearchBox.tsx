import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { globalSearch, type PullRequest, type SearchCodeFile, type SearchWorkItem } from "../api";
import { IconSearch } from "./icons";
import { prChip, stateChip, typeDot } from "../lib/tokens";

/** Header search: work items (ADO search service) + code (BFF grep index) in one
 * round trip. Picking a result deep-links into the Work Items or Code tab. */
export default function SearchBox({
  project,
  onPickWorkItem,
  onPickPr,
  onPickCode,
}: {
  project: string;
  onPickWorkItem: (id: number) => void;
  onPickPr: (pr: PullRequest) => void;
  onPickCode: (f: { repoId: string; branch: string; path: string }) => void;
}) {
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  const [open, setOpen] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(q.trim()), 350);
    return () => clearTimeout(t);
  }, [q]);

  // close on click outside / Esc
  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, []);

  const enabled = debounced.length >= 2;
  const sq = useQuery({
    queryKey: ["global-search", project, debounced],
    queryFn: () => globalSearch(project, debounced),
    enabled,
    staleTime: 30_000,
  });
  const d = sq.data;

  const pickWi = (w: SearchWorkItem) => {
    setOpen(false);
    onPickWorkItem(w.id);
  };
  const pickCode = (f: SearchCodeFile) => {
    setOpen(false);
    onPickCode({ repoId: f.repoId, branch: f.branch, path: f.path });
  };
  const pickPr = (pr: PullRequest) => {
    setOpen(false);
    onPickPr(pr);
  };

  return (
    <div ref={boxRef} className="relative">
      <div className="flex h-[34px] w-[300px] items-center gap-2 rounded-[8px] border border-border bg-surface-2 px-[12px] focus-within:border-faint">
        <span className="text-faint">
          <IconSearch size={14} />
        </span>
        <input
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={(e) => {
            if (e.key !== "Enter" || !d) return;
            const w = d.workItems.results[0];
            const p = d.pullRequests?.results[0];
            const c = d.code.results[0];
            if (w) pickWi(w);
            else if (p) pickPr(p);
            else if (c) pickCode(c);
          }}
          placeholder="Search work items & code…"
          className="w-full bg-transparent text-[12.5px] text-text outline-none placeholder:text-faint"
        />
      </div>

      {open && enabled && (
        <div className="absolute right-0 top-[40px] z-30 max-h-[520px] w-[480px] overflow-auto rounded-[10px] border border-border bg-surface py-[6px] shadow-[0_10px_30px_rgba(0,0,0,.22)]">
          {sq.isLoading && <PanelNote>Searching…</PanelNote>}
          {sq.isError && <PanelNote>Search failed: {String((sq.error as Error).message)}</PanelNote>}

          {d && (
            <>
              <SectionLabel>Work items</SectionLabel>
              {!d.workItems.available && (
                <PanelNote>{d.workItems.reason ?? "Work-item search unavailable."}</PanelNote>
              )}
              {d.workItems.available && d.workItems.results.length === 0 && (
                <PanelNote>No matching work items.</PanelNote>
              )}
              {d.workItems.results.map((w) => (
                <button
                  key={w.id}
                  onClick={() => pickWi(w)}
                  className="flex w-full items-center gap-[8px] px-[14px] py-[7px] text-left hover:bg-hover"
                >
                  <span className="font-mono text-[11px] text-faint">#{w.id}</span>
                  <span className="flex items-center gap-[5px] text-[10.5px] font-medium text-text-3">
                    <span className={`h-[7px] w-[7px] rounded-full ${typeDot(w.type)}`} />
                    {w.type}
                  </span>
                  <span className="min-w-0 flex-1 truncate text-[12.5px] text-text">{w.title}</span>
                  <span className={`rounded-[7px] px-[7px] py-[2px] text-[10.5px] font-semibold ${stateChip(w.state)}`}>
                    {w.state}
                  </span>
                </button>
              ))}

              <SectionLabel>Pull requests</SectionLabel>
              {!d.pullRequests?.available && (
                <PanelNote>{d.pullRequests?.reason ?? "PR search unavailable."}</PanelNote>
              )}
              {d.pullRequests?.available && d.pullRequests.results.length === 0 && (
                <PanelNote>No matching pull requests.</PanelNote>
              )}
              {(d.pullRequests?.results ?? []).map((pr) => (
                <button
                  key={pr.id}
                  onClick={() => pickPr(pr)}
                  className="flex w-full items-center gap-[8px] px-[14px] py-[7px] text-left hover:bg-hover"
                >
                  <span className="font-mono text-[11px] text-faint">!{pr.id}</span>
                  <span className="min-w-0 flex-1 truncate text-[12.5px] text-text">{pr.title}</span>
                  <span className="max-w-[160px] truncate font-mono text-[10.5px] text-faint">
                    {pr.sourceRef} → {pr.targetRef}
                  </span>
                  <span className={`rounded-[7px] px-[7px] py-[2px] text-[10.5px] font-semibold ${prChip(pr.status, pr.isDraft)}`}>
                    {pr.isDraft ? "draft" : pr.status}
                  </span>
                </button>
              ))}

              <SectionLabel>Code</SectionLabel>
              {!d.code.available && (
                <PanelNote>{d.code.reason ?? "Code search unavailable."}</PanelNote>
              )}
              {d.code.available && d.code.results.length === 0 && (
                <PanelNote>No code matches.</PanelNote>
              )}
              {d.code.results.map((f) => (
                <button
                  key={`${f.repoId}${f.path}`}
                  onClick={() => pickCode(f)}
                  className="block w-full px-[14px] py-[7px] text-left hover:bg-hover"
                >
                  <div className="flex items-center gap-[8px]">
                    <span className="min-w-0 flex-1 truncate font-mono text-[12px] text-text">{f.path}</span>
                    <span className="rounded-[6px] bg-surface-2 px-[6px] py-[1px] text-[10px] font-medium text-text-3">
                      {f.repo} · {f.branch}
                    </span>
                  </div>
                  {f.matches.slice(0, 2).map((m) => (
                    <div key={m.line} className="mt-[3px] flex gap-[8px] overflow-hidden">
                      <span className="flex-none font-mono text-[10.5px] text-faint">{m.line}</span>
                      <span className="truncate font-mono text-[11px] text-text-3">{m.text}</span>
                    </div>
                  ))}
                </button>
              ))}
              {d.code.available && d.code.indexedFiles !== undefined && (
                <div className="px-[14px] pb-[4px] pt-[6px] text-[10.5px] text-faint">
                  {d.code.truncated ? "More matches exist — refine the query. " : ""}
                  Searched {d.code.indexedFiles} files across repos.
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="px-[14px] pb-[2px] pt-[8px] text-[10px] font-semibold uppercase tracking-[0.8px] text-faint">
      {children}
    </div>
  );
}

function PanelNote({ children }: { children: React.ReactNode }) {
  return <div className="px-[14px] py-[6px] text-[12px] text-faint">{children}</div>;
}
