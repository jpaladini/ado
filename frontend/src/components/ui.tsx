import type { ReactNode } from "react";

type Tone = "slate" | "green" | "amber" | "red" | "indigo" | "blue" | "purple";

const TONES: Record<Tone, string> = {
  slate: "bg-slate-100 text-slate-700",
  green: "bg-emerald-100 text-emerald-700",
  amber: "bg-amber-100 text-amber-700",
  red: "bg-rose-100 text-rose-700",
  indigo: "bg-indigo-100 text-indigo-700",
  blue: "bg-sky-100 text-sky-700",
  purple: "bg-violet-100 text-violet-700",
};

export function Badge({ children, tone = "slate" }: { children: ReactNode; tone?: Tone }) {
  return (
    <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${TONES[tone]}`}>
      {children}
    </span>
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return <p className="py-6 text-sm text-slate-400">{label}</p>;
}

export function ErrorMsg({ error }: { error: unknown }) {
  const msg = error instanceof Error ? error.message : String(error);
  return (
    <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
      {msg}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-slate-200 p-8 text-center text-sm text-slate-400">
      {children}
    </div>
  );
}

export function relTime(iso?: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  const diff = (Date.now() - d.getTime()) / 1000;
  const units: [number, string][] = [
    [60, "s"],
    [3600, "m"],
    [86400, "h"],
    [2592000, "d"],
  ];
  if (diff < 60) return "just now";
  for (let i = units.length - 1; i >= 0; i--) {
    const [secs, label] = units[i];
    if (diff >= secs) return `${Math.floor(diff / secs)}${label} ago`;
  }
  return d.toLocaleDateString();
}

// -- domain tone maps ---------------------------------------------------------

export function workItemTone(state: string): Tone {
  const s = state?.toLowerCase() ?? "";
  if (["done", "closed", "resolved", "completed"].includes(s)) return "green";
  if (["active", "committed", "in progress", "doing"].includes(s)) return "blue";
  if (["new", "to do", "proposed"].includes(s)) return "slate";
  if (["removed"].includes(s)) return "red";
  return "slate";
}

export function prTone(status: string, isDraft: boolean): Tone {
  if (isDraft) return "slate";
  if (status === "completed") return "green";
  if (status === "abandoned") return "red";
  return "blue"; // active
}

export function buildTone(status: string | null, result: string | null): Tone {
  if (status && status !== "completed") return "amber"; // inProgress / notStarted
  if (result === "succeeded") return "green";
  if (result === "failed") return "red";
  if (result === "canceled" || result === "partiallySucceeded") return "amber";
  return "slate";
}
