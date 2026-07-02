import { useQuery } from "@tanstack/react-query";
import { fetchHealth } from "../api";
import { Spark } from "./icons";

/** Small "do it with AI" trigger; render only when useCopilotConfigured() is true. */
export function AIButton({
  label,
  busy,
  disabled,
  onClick,
}: {
  label: string;
  busy: boolean;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={busy || disabled}
      className={`inline-flex items-center gap-[5px] rounded-[6px] border border-border bg-surface px-[8px] py-[3px] text-[11px] font-semibold text-text-3 hover:border-faint hover:text-accent-text disabled:opacity-50 ${busy ? "animate-pulse" : ""}`}
    >
      <span className="text-accent">
        <Spark size={11} />
      </span>
      {busy ? "Thinking…" : label}
    </button>
  );
}

export function useCopilotConfigured(): boolean {
  const health = useQuery({ queryKey: ["health"], queryFn: fetchHealth, staleTime: 60_000 });
  return health.data?.copilot_configured === true;
}
