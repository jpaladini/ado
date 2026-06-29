// Token → literal Tailwind class strings. Literals (not interpolated) so the
// JIT compiler can see every class. All chip styles map to a `bg-*` + `text-*`.

// Shared state-chip map: work item state, PR status, overview pills.
const CHIP = {
  resolved: "bg-purple-bg text-purple",
  done: "bg-ok-bg text-ok",
  active: "bg-info-bg text-info",
  removed: "bg-danger-bg text-danger",
  neutral: "bg-nbg text-nfg",
} as const;

export function stateChip(state: string | null | undefined): string {
  const s = (state ?? "").toLowerCase();
  if (["resolved"].includes(s)) return CHIP.resolved;
  if (["done", "closed", "completed"].includes(s)) return CHIP.done;
  if (["active", "doing", "in progress", "committed"].includes(s)) return CHIP.active;
  if (["removed", "abandoned"].includes(s)) return CHIP.removed;
  return CHIP.neutral; // new / to do / proposed / unknown
}

// PR status pill (active/completed/abandoned/draft).
export function prChip(status: string, isDraft: boolean): string {
  if (isDraft) return CHIP.neutral;
  if (status === "completed") return CHIP.done;
  if (status === "abandoned") return CHIP.removed;
  return CHIP.active;
}

// Build/pipeline status pill.
export function buildChip(status: string | null, result: string | null): string {
  if (status && status !== "completed") return "bg-warn-bg text-warn"; // running / queued
  if (result === "succeeded") return CHIP.done;
  if (result === "failed") return CHIP.removed;
  if (result === "canceled" || result === "partiallySucceeded") return "bg-warn-bg text-warn";
  return CHIP.neutral;
}

// Work item type → dot color (literal bg-* classes).
export function typeDot(type: string | null | undefined): string {
  const t = (type ?? "").toLowerCase();
  if (t.includes("epic")) return "bg-purple";
  if (t.includes("feature")) return "bg-warn";
  if (t.includes("bug")) return "bg-danger";
  if (t.includes("task")) return "bg-ok";
  return "bg-info"; // story / user story / default
}

// Build result → chart dot color.
export function buildDot(status: string | null, result: string | null): string {
  if (status && status !== "completed") return "bg-c-amber";
  if (result === "succeeded") return "bg-c-green";
  if (result === "failed") return "bg-c-red";
  return "bg-c-amber";
}

// Tag chip.
export function tagChip(tag: string): string {
  const t = tag.toLowerCase();
  if (t === "p1") return "bg-danger-bg text-danger";
  if (t === "genie") return "bg-purple-bg text-purple";
  return "bg-nbg text-nfg";
}
