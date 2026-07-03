import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchFreshness, refreshAnalyticsData } from "../api";
import { useToast } from "./Toast";

function fmtUpdated(iso?: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  const mins = Math.floor((Date.now() - d.getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  if (mins < 60 * 24) return `${Math.floor(mins / 60)}h ago`;
  return d.toLocaleString();
}

/** Freshness + refresh control for the *batch* Delta tables (the AI's
 * query_analytics_history tool reads them). Lives on the AI tab since the
 * Reports tab is near-live OData and doesn't depend on the ingest. */
export default function FreshnessBar() {
  const qc = useQueryClient();
  const toast = useToast();
  // updatedAt at the moment a refresh was triggered; non-null = actively watching
  const [baseline, setBaseline] = useState<string | null>(null);
  const fresh = useQuery({
    queryKey: ["freshness"],
    queryFn: fetchFreshness,
    staleTime: 60_000,
    refetchInterval: baseline !== null ? 20_000 : false,
  });

  const updatedAt = fresh.data?.updatedAt ?? null;
  useEffect(() => {
    if (baseline !== null && updatedAt && updatedAt !== baseline) {
      setBaseline(null);
      toast("Data refreshed ✓");
    }
  }, [baseline, updatedAt, toast]);

  const refresh = useMutation({
    mutationFn: refreshAnalyticsData,
    onSuccess: (r) => {
      if (r.started) {
        toast("Data refresh started — takes ~2 minutes");
        setBaseline(updatedAt ?? "pending");
        setTimeout(() => setBaseline(null), 480_000);
        qc.invalidateQueries({ queryKey: ["freshness"] });
      } else {
        toast(r.reason ?? "Could not start refresh");
      }
    },
    onError: (e) => toast((e as Error).message),
  });

  if (!fresh.data?.available) return null;
  const updated = fmtUpdated(updatedAt);
  return (
    <div className="mt-2 flex items-center gap-2 text-[11.5px] text-faint">
      <span>
        Historical data as of <span className="font-mono text-text-3">{fresh.data.asOf ?? "—"}</span>
        {updated && (
          <>
            {" "}· updated{" "}
            <span className="font-mono text-text-3" title={updatedAt ?? undefined}>
              {updated}
            </span>
          </>
        )}{" "}
        · refreshed daily at 05:00 UTC
      </span>
      <button
        onClick={() => refresh.mutate()}
        disabled={refresh.isPending || baseline !== null}
        className="rounded-[6px] border border-border bg-surface px-2 py-[3px] text-[11px] font-semibold text-text-3 hover:border-faint disabled:opacity-50"
      >
        {baseline !== null ? "Refreshing…" : "Refresh now"}
      </button>
    </div>
  );
}
