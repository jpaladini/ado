import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type { Project, PullRequest } from "../api";
import { fetchPullRequests, fetchWorkItems } from "../api";
import { useTheme } from "../lib/theme";
import {
  IconActivity,
  IconAnalytics,
  IconChevron,
  IconCode,
  IconMoon,
  IconOverview,
  IconPipe,
  IconPrs,
  IconSun,
  IconWork,
  IconX,
  Spark,
} from "./icons";
import SearchBox from "./SearchBox";
import Overview from "../screens/Overview";
import WorkItems from "../screens/WorkItems";
import PullRequests from "../screens/PullRequests";
import Pipelines from "../screens/Pipelines";
import Code from "../screens/Code";
import Reports from "../screens/Reports";
import Copilot from "../screens/Copilot";
import UserFooter from "./UserFooter";

const TABS = ["Overview", "Work Items", "Pull Requests", "Pipelines", "Code"] as const;
type Tab = (typeof TABS)[number] | "Reports";

const ICONS: Record<(typeof TABS)[number] | "Reports", (p: { size?: number }) => JSX.Element> = {
  Overview: IconOverview,
  "Work Items": IconWork,
  "Pull Requests": IconPrs,
  Pipelines: IconPipe,
  Code: IconCode,
  Reports: IconAnalytics,
};

const NAV_PREF = "adoc.navCollapsed";

export default function Shell({
  project,
  projects,
  onSelectProject,
  me,
}: {
  project: Project;
  projects: Project[];
  onSelectProject: (p: Project) => void;
  me: string | null;
}) {
  const [tab, setTab] = useState<Tab>("Overview");
  const { theme, toggle } = useTheme();

  // the copilot lives in a right panel (Genie/Cortex style), available on every
  // tab; once opened it stays mounted so the chat survives closing the panel
  const [copilotOpen, setCopilotOpen] = useState(false);
  const [copilotMounted, setCopilotMounted] = useState(false);
  const openCopilot = () => {
    setCopilotMounted(true);
    setCopilotOpen((o) => !o);
  };

  // left nav collapses to an icon rail for more working room
  const [navCollapsed, setNavCollapsed] = useState(() => localStorage.getItem(NAV_PREF) === "1");
  const toggleNav = () =>
    setNavCollapsed((c) => {
      localStorage.setItem(NAV_PREF, c ? "0" : "1");
      return !c;
    });

  // search deep-links: fresh objects each pick, so screens re-open on repeat picks
  const [wiTarget, setWiTarget] = useState<{ id: number } | null>(null);
  const [prTarget, setPrTarget] = useState<PullRequest | null>(null);
  const [fileTarget, setFileTarget] = useState<{ repoId: string; branch: string; path: string } | null>(null);

  // nav badge counts (shared cache with the screens — deduped by key)
  const wi = useQuery({ queryKey: ["workitems", project.name], queryFn: () => fetchWorkItems(project.name) });
  const prs = useQuery({ queryKey: ["prs", project.name, "active"], queryFn: () => fetchPullRequests(project.name, "active") });
  const counts: Partial<Record<Tab, number>> = {
    "Work Items": wi.data?.value.length,
    "Pull Requests": prs.data?.value.length,
  };

  const navButton = (t: Tab) => {
    const Icon = ICONS[t];
    const on = tab === t;
    return (
      <button
        key={t}
        onClick={() => setTab(t)}
        title={t}
        className={`relative flex items-center rounded-[8px] px-[11px] py-[8px] text-[13px] ${
          navCollapsed ? "justify-center" : "justify-between"
        } ${on ? "bg-accent-tint font-semibold text-accent-text" : "font-medium text-text-2 hover:bg-hover"}`}
      >
        {on && <span className="absolute bottom-[8px] left-0 top-[8px] w-[3px] rounded-[2px] bg-accent" />}
        <span className="flex items-center gap-[10px]">
          <Icon size={16} />
          {!navCollapsed && t}
        </span>
        {!navCollapsed && counts[t] !== undefined && (
          <span className="font-mono text-[11px] text-faint">{counts[t]}</span>
        )}
      </button>
    );
  };

  return (
    <div className="flex h-screen min-w-[1100px] overflow-hidden bg-bg text-text">
      {/* SIDEBAR (collapsible to an icon rail) */}
      <aside
        className={`flex flex-none flex-col border-r border-border bg-surface ${
          navCollapsed ? "w-[58px]" : "w-[236px]"
        }`}
      >
        <div
          className={`flex items-center border-b border-border-2 ${
            navCollapsed ? "justify-center p-[16px_8px_14px]" : "gap-[10px] p-[16px_16px_14px]"
          }`}
        >
          <div className="flex h-[30px] w-[30px] flex-none items-center justify-center rounded-[8px] bg-accent text-white">
            <Spark size={16} />
          </div>
          {!navCollapsed && (
            <div>
              <div className="text-[14px] font-bold leading-none text-text">ADO Companion</div>
              <div className="mt-[3px] text-[10.5px] text-faint">on Databricks Apps</div>
            </div>
          )}
        </div>

        {!navCollapsed && (
          <div className="p-[12px_12px_0]">
            <ProjectSwitcher project={project} projects={projects} onSelect={onSelectProject} />
          </div>
        )}

        <nav className={`flex flex-1 flex-col gap-[2px] ${navCollapsed ? "p-[14px_8px]" : "p-[14px_12px]"}`}>
          {!navCollapsed && (
            <div className="px-[11px] pb-[4px] pt-[6px] text-[10px] font-semibold uppercase tracking-[0.8px] text-faint">
              Workspace
            </div>
          )}
          {TABS.map(navButton)}
          {!navCollapsed && (
            <div className="px-[11px] pb-[4px] pt-[14px] text-[10px] font-semibold uppercase tracking-[0.8px] text-faint">
              Insights
            </div>
          )}
          {navCollapsed && <div className="my-[6px] h-px bg-border-2" />}
          {navButton("Reports")}
          {!navCollapsed && (
            <span className="flex cursor-default items-center gap-[10px] rounded-[8px] px-[11px] py-[8px] text-[13px] font-medium text-text-2">
              <IconActivity size={16} />
              Activity
            </span>
          )}
        </nav>

        <button
          onClick={toggleNav}
          title={navCollapsed ? "Expand navigation" : "Collapse navigation"}
          className="flex items-center justify-center border-t border-border-2 py-[9px] text-faint hover:bg-hover hover:text-text-3"
        >
          <span className={`inline-block ${navCollapsed ? "-rotate-90" : "rotate-90"}`}>
            <IconChevron size={12} />
          </span>
        </button>

        {!navCollapsed && <UserFooter fallbackName={me} projects={projects} />}
      </aside>

      {/* MAIN */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-[54px] flex-none items-center justify-between border-b border-border bg-surface px-[22px]">
          <div className="flex items-center gap-2 text-[13px]">
            <span className="text-muted">{project.name}</span>
            <span className="text-dvf">/</span>
            <span className="font-semibold text-text">{tab}</span>
          </div>
          <div className="flex items-center gap-[10px]">
            <SearchBox
              project={project.name}
              onPickWorkItem={(id) => {
                setWiTarget({ id });
                setTab("Work Items");
              }}
              onPickPr={(pr) => {
                setPrTarget({ ...pr });
                setTab("Pull Requests");
              }}
              onPickCode={(f) => {
                setFileTarget(f);
                setTab("Code");
              }}
            />
            <button
              onClick={openCopilot}
              title="AI Copilot"
              className={`flex h-[34px] items-center gap-[7px] rounded-[8px] border px-[12px] text-[12px] font-semibold ${
                copilotOpen
                  ? "border-accent bg-accent-tint text-accent-text"
                  : "border-border bg-surface-2 text-text-3 hover:border-faint"
              }`}
            >
              <Spark size={14} />
              Copilot
            </button>
            <button
              onClick={toggle}
              title="Toggle theme"
              className="flex h-[34px] w-[34px] flex-none items-center justify-center rounded-[8px] border border-border bg-surface-2 text-text-3"
            >
              {theme === "dark" ? <IconSun size={16} /> : <IconMoon size={16} />}
            </button>
            <div className="h-[24px] w-px bg-border" />
            <span className="rounded-[20px] bg-ok-bg px-[10px] py-[5px] text-[11px] font-semibold text-ok">● connected</span>
          </div>
        </header>

        <div className="flex min-h-0 flex-1">
          <div className="min-w-0 flex-1 overflow-auto p-[22px_24px]">
            {tab === "Overview" && <Overview project={project.name} />}
            {tab === "Work Items" && <WorkItems project={project.name} me={me} openTarget={wiTarget} />}
            {tab === "Pull Requests" && <PullRequests project={project.name} openTarget={prTarget} />}
            {tab === "Pipelines" && <Pipelines project={project.name} />}
            {tab === "Code" && <Code project={project.name} fileTarget={fileTarget} />}
            {tab === "Reports" && <Reports project={project.name} />}
          </div>

          {/* COPILOT PANEL — mounted once, hidden on close so the chat survives */}
          {copilotMounted && (
            <aside
              className={`${
                copilotOpen ? "flex" : "hidden"
              } w-[420px] flex-none flex-col border-l border-border bg-surface`}
            >
              <div className="flex h-[42px] flex-none items-center justify-between border-b border-border-2 px-[14px]">
                <span className="flex items-center gap-[7px] text-[12.5px] font-semibold text-text">
                  <span className="text-accent">
                    <Spark size={14} />
                  </span>
                  AI Copilot
                </span>
                <button
                  onClick={() => setCopilotOpen(false)}
                  title="Close panel"
                  className="text-faint hover:text-text-3"
                >
                  <IconX size={14} />
                </button>
              </div>
              <div className="min-h-0 flex-1 overflow-auto p-[14px]">
                <Copilot project={project.name} panel />
              </div>
            </aside>
          )}
        </div>
      </div>
    </div>
  );
}

function ProjectSwitcher({
  project,
  projects,
  onSelect,
}: {
  project: Project;
  projects: Project[];
  onSelect: (p: Project) => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between rounded-[8px] border border-border bg-surface-2 px-[11px] py-[9px]"
      >
        <span className="flex items-center gap-2">
          <span className="flex h-[18px] w-[18px] items-center justify-center rounded-[5px] bg-ink-bg text-[10px] font-bold text-ink-fg">
            {project.name[0]?.toLowerCase()}
          </span>
          <span className="text-[13px] font-semibold text-text">{project.name}</span>
        </span>
        <span className="text-muted">
          <IconChevron size={12} />
        </span>
      </button>
      {open && (
        <div className="absolute left-0 right-0 top-[44px] z-20 max-h-[280px] overflow-auto rounded-[8px] border border-border bg-surface py-1 shadow-[0_8px_24px_rgba(0,0,0,.18)]">
          {projects.map((p) => (
            <button
              key={p.id}
              onClick={() => {
                onSelect(p);
                setOpen(false);
              }}
              className={`block w-full truncate px-[12px] py-[7px] text-left text-[13px] ${
                p.id === project.id ? "font-semibold text-accent-text" : "text-text-2 hover:bg-hover"
              }`}
            >
              {p.name}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
