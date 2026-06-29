import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchHealth, fetchMe, fetchProjects, type Project } from "./api";
import Shell from "./components/Shell";
import { ToastProvider } from "./components/Toast";
import { Spark } from "./components/icons";

export default function App() {
  const health = useQuery({ queryKey: ["health"], queryFn: fetchHealth });
  const configured = health.data?.ado_configured === true;

  const projects = useQuery({ queryKey: ["projects"], queryFn: fetchProjects, enabled: configured });
  const me = useQuery({ queryKey: ["me"], queryFn: fetchMe, enabled: configured });

  // selected project, synced to ?project=<name>
  const [projectName, setProjectName] = useState<string | null>(
    () => new URLSearchParams(location.search).get("project"),
  );
  const list = projects.data?.value ?? [];
  const selected = useMemo(
    () => list.find((p) => p.name === projectName) ?? list[0] ?? null,
    [list, projectName],
  );

  useEffect(() => {
    if (!selected) return;
    const url = new URL(location.href);
    if (url.searchParams.get("project") !== selected.name) {
      url.searchParams.set("project", selected.name);
      history.replaceState(null, "", url);
    }
  }, [selected]);

  const onSelect = (p: Project) => setProjectName(p.name);

  if (configured === false) return <NotConnected />;
  if (!selected) return <Splash label={projects.isError ? "Couldn’t load projects." : "Loading…"} />;

  return (
    <ToastProvider>
      <Shell project={selected} projects={list} onSelectProject={onSelect} me={me.data?.displayName ?? null} />
    </ToastProvider>
  );
}

function Splash({ label }: { label: string }) {
  return (
    <div className="flex h-screen items-center justify-center bg-bg text-[13px] text-faint">{label}</div>
  );
}

function NotConnected() {
  return (
    <div className="flex h-screen items-center justify-center bg-bg">
      <div className="max-w-[420px] rounded-[10px] border border-border bg-surface p-7 text-center">
        <div className="mx-auto mb-3 flex h-[34px] w-[34px] items-center justify-center rounded-[8px] bg-accent text-white">
          <Spark size={18} />
        </div>
        <div className="text-[15px] font-semibold text-text">Not connected to Azure DevOps</div>
        <p className="mt-2 text-[12.5px] text-muted">
          Set <code className="font-mono">ADO_ORG_URL</code> and the <code className="font-mono">ado_pat</code> secret
          (see <code className="font-mono">SETUP_DATABRICKS.md</code>), then redeploy.
        </p>
      </div>
    </div>
  );
}
