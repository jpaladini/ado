import { useState } from "react";
import type { Project } from "../api";
import { relTime } from "./ui";
import WorkItemsPanel from "./WorkItemsPanel";
import PullRequestsPanel from "./PullRequestsPanel";
import PipelinesPanel from "./PipelinesPanel";
import ReposPanel from "./ReposPanel";

const TABS = ["Overview", "Work Items", "Pull Requests", "Pipelines", "Code"] as const;
type Tab = (typeof TABS)[number];

export default function ProjectDetail({ project }: { project: Project }) {
  const [tab, setTab] = useState<Tab>("Work Items");

  return (
    <div className="rounded-xl border border-slate-200 bg-white">
      <div className="border-b border-slate-100 px-5 pt-4">
        <h2 className="text-lg font-semibold text-slate-900">{project.name}</h2>
        <p className="mb-3 text-sm text-slate-500">
          {project.description || "No description"}
        </p>
        <nav className="flex gap-1">
          {TABS.map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium transition ${
                tab === t
                  ? "border-indigo-500 text-indigo-600"
                  : "border-transparent text-slate-500 hover:text-slate-800"
              }`}
            >
              {t}
            </button>
          ))}
        </nav>
      </div>

      <div className="p-5">
        {tab === "Overview" && (
          <dl className="grid max-w-md grid-cols-2 gap-y-2 text-sm">
            <dt className="text-slate-400">State</dt>
            <dd className="font-medium text-slate-700">{project.state ?? "—"}</dd>
            <dt className="text-slate-400">Last updated</dt>
            <dd className="font-medium text-slate-700">{relTime(project.lastUpdateTime)}</dd>
            <dt className="text-slate-400">ID</dt>
            <dd className="truncate font-mono text-xs text-slate-600">{project.id}</dd>
          </dl>
        )}
        {tab === "Work Items" && <WorkItemsPanel project={project.name} />}
        {tab === "Pull Requests" && <PullRequestsPanel project={project.name} />}
        {tab === "Pipelines" && <PipelinesPanel project={project.name} />}
        {tab === "Code" && <ReposPanel project={project.name} />}
      </div>
    </div>
  );
}
