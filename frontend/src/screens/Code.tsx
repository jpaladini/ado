import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchCommits, fetchRepos } from "../api";
import { Card, Empty, ErrorMsg, H1, Loading, SectionLabel, relTime } from "../components/ui";

const DOTS = ["bg-accent", "bg-info", "bg-purple", "bg-ok", "bg-warn"];

export default function Code({ project }: { project: string }) {
  const repos = useQuery({ queryKey: ["repos", project], queryFn: () => fetchRepos(project) });
  const [repoId, setRepoId] = useState<string | null>(null);

  useEffect(() => {
    if (!repoId && repos.data?.value.length) setRepoId(repos.data.value[0].id);
  }, [repos.data, repoId]);

  const commits = useQuery({
    queryKey: ["commits", project, repoId],
    queryFn: () => fetchCommits(project, repoId!),
    enabled: !!repoId,
  });

  const selected = repos.data?.value.find((r) => r.id === repoId);

  return (
    <div>
      <H1>Code</H1>
      <div className="mt-4 grid grid-cols-[220px_1fr] gap-[16px]">
        <div>
          <SectionLabel className="mb-2">Repositories</SectionLabel>
          {repos.isLoading && <Loading />}
          {repos.isError && <ErrorMsg error={repos.error} />}
          <div className="flex flex-col gap-[3px]">
            {repos.data?.value.map((r, i) => {
              const on = r.id === repoId;
              return (
                <button
                  key={r.id}
                  onClick={() => setRepoId(r.id)}
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

        <Card className="overflow-hidden">
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
      </div>
    </div>
  );
}
