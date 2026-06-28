import { useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchHealth, fetchProjects, type Project } from "./api";

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
    <div className="mx-auto max-w-5xl px-6 py-10">
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
          <code>ado_pat</code> secret (see README), then redeploy.
        </Notice>
      )}

      {configured && (
        <section className="grid gap-6 md:grid-cols-[1fr_1.2fr]">
          <div>
            <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-slate-500">
              Projects
            </h2>
            {projects.isLoading && <p className="text-sm text-slate-400">Loading…</p>}
            {projects.isError && (
              <Notice>Couldn’t load projects: {(projects.error as Error).message}</Notice>
            )}
            <ul className="space-y-2">
              {projects.data?.value.map((p) => (
                <li key={p.id}>
                  <button
                    onClick={() => setSelected(p)}
                    className={`w-full rounded-lg border px-4 py-3 text-left transition ${
                      selected?.id === p.id
                        ? "border-indigo-400 bg-indigo-50"
                        : "border-slate-200 bg-white hover:border-slate-300"
                    }`}
                  >
                    <div className="font-medium">{p.name}</div>
                    {p.description && (
                      <div className="line-clamp-1 text-sm text-slate-500">{p.description}</div>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          </div>

          <div>
            <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-slate-500">
              Details
            </h2>
            {selected ? (
              <div className="rounded-lg border border-slate-200 bg-white p-5">
                <div className="text-lg font-semibold">{selected.name}</div>
                <dl className="mt-3 space-y-1 text-sm text-slate-600">
                  <Row label="State" value={selected.state ?? "—"} />
                  <Row
                    label="Last updated"
                    value={
                      selected.lastUpdateTime
                        ? new Date(selected.lastUpdateTime).toLocaleString()
                        : "—"
                    }
                  />
                  <Row label="ID" value={selected.id} />
                </dl>
                <p className="mt-4 text-xs text-slate-400">
                  Work items, PRs, and pipelines land here in Phase 1.
                </p>
              </div>
            ) : (
              <div className="rounded-lg border border-dashed border-slate-200 p-8 text-center text-sm text-slate-400">
                Select a project.
              </div>
            )}
          </div>
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

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4">
      <dt className="text-slate-400">{label}</dt>
      <dd className="font-medium text-slate-700">{value}</dd>
    </div>
  );
}
