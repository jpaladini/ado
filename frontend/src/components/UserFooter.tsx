import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchSettings, fetchWhoami, putSetting, type Project } from "../api";
import { useTheme } from "../lib/theme";
import { useToast } from "./Toast";
import { IconChevron } from "./icons";

const RANGES = ["24h", "7d", "30d"];

export default function UserFooter({
  fallbackName,
  projects,
}: {
  fallbackName: string | null;
  projects: Project[];
}) {
  const qc = useQueryClient();
  const toast = useToast();
  const { theme, toggle } = useTheme();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const whoami = useQuery({ queryKey: ["whoami"], queryFn: fetchWhoami, staleTime: 300_000 });
  const settings = useQuery({ queryKey: ["settings"], queryFn: fetchSettings, staleTime: 60_000 });
  const s = settings.data?.settings ?? {};

  const save = useMutation({
    mutationFn: ({ key, value }: { key: string; value: string }) => putSetting(key, value),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["settings"] });
      toast("Setting saved");
    },
    onError: (e) => toast((e as Error).message),
  });

  // apply the server-side theme preference once on load
  const appliedTheme = useRef(false);
  useEffect(() => {
    if (!appliedTheme.current && s.theme && s.theme !== theme) {
      appliedTheme.current = true;
      toggle();
    } else if (s.theme) {
      appliedTheme.current = true;
    }
  }, [s.theme, theme, toggle]);

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const user = whoami.data && whoami.data.user !== "local" ? whoami.data.user : (fallbackName ?? "—");
  const auditOn = whoami.data?.store.available === true;

  return (
    <div ref={ref} className="relative border-t border-border-2 p-[12px]">
      {open && (
        <div className="absolute bottom-[64px] left-[12px] right-[12px] z-30 rounded-[10px] border border-border bg-surface p-[14px] shadow-[0_8px_24px_rgba(0,0,0,.18)]">
          <div className="mb-1 truncate text-[12px] font-semibold text-text" title={user}>
            {user}
          </div>
          <div className="mb-3 text-[10.5px] text-faint">
            activity log: <span className={auditOn ? "text-ok" : "text-warn"}>{auditOn ? "on" : "off"}</span>
          </div>

          <Label>Theme</Label>
          <div className="mb-3 flex gap-[6px]">
            {(["light", "dark"] as const).map((t) => (
              <button
                key={t}
                onClick={() => {
                  if (theme !== t) toggle();
                  save.mutate({ key: "theme", value: t });
                }}
                className={chip(theme === t)}
              >
                {t}
              </button>
            ))}
          </div>

          <Label>Default project</Label>
          <select
            value={s.default_project ?? ""}
            onChange={(e) => save.mutate({ key: "default_project", value: e.target.value })}
            className="mb-3 w-full rounded-[7px] border border-border bg-surface-2 px-2 py-[6px] text-[12px] text-text outline-none"
          >
            <option value="">(first available)</option>
            {projects.map((p) => (
              <option key={p.id} value={p.name}>
                {p.name}
              </option>
            ))}
          </select>

          <Label>Default date range</Label>
          <div className="flex gap-[6px]">
            {RANGES.map((r) => (
              <button
                key={r}
                onClick={() => save.mutate({ key: "default_range", value: r })}
                className={chip((s.default_range ?? "7d") === r)}
              >
                {r}
              </button>
            ))}
          </div>
        </div>
      )}

      <button onClick={() => setOpen((o) => !o)} className="flex w-full items-center gap-[10px] text-left">
        <div className="flex h-[30px] w-[30px] flex-none items-center justify-center rounded-full bg-ink-bg text-[11px] font-semibold text-ink-fg">
          {initials(user)}
        </div>
        <div className="min-w-0 flex-1">
          <div className="truncate text-[12px] font-semibold text-text">{user}</div>
          <div className="flex items-center gap-[4px] text-[10.5px] text-ok">
            <span className="h-[6px] w-[6px] rounded-full bg-c-green" />
            connected
          </div>
        </div>
        <span className={`text-muted transition-transform ${open ? "rotate-180" : ""}`}>
          <IconChevron size={12} />
        </span>
      </button>
    </div>
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-1 text-[10px] font-semibold uppercase tracking-[0.8px] text-faint">{children}</div>
  );
}

function chip(on: boolean): string {
  return `rounded-[7px] border px-[10px] py-[5px] text-[11.5px] capitalize ${
    on ? "border-ink-bg bg-ink-bg font-semibold text-ink-fg" : "border-border bg-surface font-medium text-text-3 hover:border-faint"
  }`;
}

function initials(name: string): string {
  const parts = name.replace(/@.*/, "").split(/[.\s_-]+/).filter(Boolean);
  return ((parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "")).toUpperCase() || name.slice(0, 2).toUpperCase();
}
