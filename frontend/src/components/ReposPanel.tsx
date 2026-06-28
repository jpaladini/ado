import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchCommits, fetchRepos } from "../api";
import { Badge, Empty, ErrorMsg, Loading, relTime } from "./ui";

export default function ReposPanel({ project }: { project: string }) {
  const repos = useQuery({
    queryKey: ["repos", project],
    queryFn: () => fetchRepos(project),
  });
  const [repoId, setRepoId] = useState<string | null>(null);

  // default to the first repo once loaded
  useEffect(() => {
    if (!repoId && repos.data?.value.length) setRepoId(repos.data.value[0].id);
  }, [repos.data, repoId]);

  const commits = useQuery({
    queryKey: ["commits", project, repoId],
    queryFn: () => fetchCommits(project, repoId!),
    enabled: !!repoId,
  });

  if (repos.isLoading) return <Loading />;
  if (repos.isError) return <ErrorMsg error={repos.error} />;
  if (!repos.data?.value.length) return <Empty>No repositories.</Empty>;

  return (
    <div className="grid gap-5 md:grid-cols-[200px_1fr]">
      <div>
        <div className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-400">
          Repositories
        </div>
        <ul className="space-y-1">
          {repos.data.value.map((r) => (
            <li key={r.id}>
              <button
                onClick={() => setRepoId(r.id)}
                className={`w-full truncate rounded-md px-2.5 py-1.5 text-left text-sm transition ${
                  repoId === r.id ? "bg-indigo-50 text-indigo-700" : "text-slate-700 hover:bg-slate-100"
                }`}
                title={r.name}
              >
                {r.name}
              </button>
            </li>
          ))}
        </ul>
      </div>

      <div>
        <div className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-400">
          Recent commits
        </div>
        {commits.isLoading && <Loading />}
        {commits.isError && <ErrorMsg error={commits.error} />}
        {commits.data?.value.length === 0 && <Empty>No commits.</Empty>}
        <ul className="divide-y divide-slate-100">
          {commits.data?.value.map((c) => (
            <li key={c.commitId} className="flex items-center gap-3 py-2.5">
              <Badge tone="purple">{c.shortId}</Badge>
              <span className="flex-1 truncate text-sm text-slate-800" title={c.comment}>
                {c.comment}
              </span>
              <span className="w-28 shrink-0 truncate text-right text-xs text-slate-500">
                {c.author ?? "—"}
              </span>
              <span className="w-20 shrink-0 text-right text-xs text-slate-400">
                {relTime(c.date)}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
