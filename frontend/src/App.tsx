import { useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchHealth, fetchProjects, type Project } from "./api";
import ProjectDetail from "./components/ProjectDetail";

export default function App() {
  const health = useQuery({ queryKey: ["health"], queryFn: fetchHealth });
  const projects = useQuery({
    queryKey: ["projects"],
    queryFn: fetchProjects,
    enabled: health.data?.ado_configured === true,
  });
  const [selected, setSelected] = useState<Project | null>(null);
  const configured = health.data?.ado_configured;

  return (
    <div className="mx-auto max-w-6xl px-6 py-10">
      <header className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">ADO Companion</h1>
          <p className="text-sm text-slate-500">Azure DevOps · on Databricks Apps</p>
        </div>
        <HealthBadge ok={health.data?.status === "ok"} configured={configured} />
      </header>

      {configured === false && (
        <Notice>
          Not connected to Azure DevOps yet. Set <code>ADO_ORG_URL</code> and the{" "}
          <code>ado_pat</code> secret (see <code>SETUP_DATABRICKS.md</code>), then redeploy.
        </Notice>
      )}

      {configured && (
        <section className="grid gap-6 md:grid-cols-[260px_1fr]">
          <aside>
            <h2 className="mb-3 text-xs font-medium uppercase tracking-wide text-slate-400">
              Projects
            </h2>
            {projects.isLoading && <p className="text-sm text-slate-400">Loading…</p>}
            {projects.isError && (
              <Notice>Couldn’t load projects: {(projects.error as Error).message}</Notice>
            )}
            <ul className="space-y-1">
              {projects.data?.value.map((p) => (
                <li key={p.id}>
                  <button
                    onClick={() => setSelected(p)}
                    className={`w-full truncate rounded-lg px-3 py-2 text-left text-sm transition ${
                      selected?.id === p.id
                        ? "bg-indigo-50 font-medium text-indigo-700"
                        : "text-slate-700 hover:bg-slate-100"
                    }`}
                    title={p.name}
                  >
                    {p.name}
                  </button>
                </li>
              ))}
            </ul>
          </aside>

          <main>
            {selected ? (
              <ProjectDetail project={selected} />
            ) : (
              <div className="rounded-xl border border-dashed border-slate-200 p-12 text-center text-sm text-slate-400">
                Select a project to see work items, PRs, pipelines, and code.
              </div>
            )}
          </main>
        </section>
      )}
    </div>
  );
}

function HealthBadge({ ok, configured }: { ok?: boolean; configured?: boolean }) {
  const label = !ok ? "offline" : configured ? "connected" : "not configured";
  const tone = !ok
    ? "bg-rose-100 text-rose-700"
    : configured
      ? "bg-emerald-100 text-emerald-700"
      : "bg-amber-100 text-amber-700";
  return <span className={`rounded-full px-3 py-1 text-xs font-medium ${tone}`}>{label}</span>;
}

function Notice({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
      {children}
    </div>
  );
}
