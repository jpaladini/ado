import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchFreshness, refreshAnalyticsData } from "../api";
import { Card, H1 } from "../components/ui";
import { useToast } from "../components/Toast";

// The Genie chat that used to live here moved into the AI Copilot as the
// query_analytics_history tool (2026-07-02). This tab keeps the data-freshness
// controls and becomes the home of the 4C report widgets.

export default function Analytics() {
  return (
    <div className="mx-auto max-w-[840px]">
      <H1>Analytics</H1>
      <p className="m-0 mt-[5px] text-[12.5px] text-muted">
        Dashboards over the ingested Delta tables. For questions in plain language — live or
        historical — use the <span className="font-semibold text-text-3">AI Copilot</span> tab.
      </p>
      <FreshnessBar />

      <Card className="mt-5 p-[16px_18px]">
        <div className="text-[13px] font-semibold text-text">Report widgets are on the way</div>
        <p className="mt-1 text-[12.5px] text-muted">
          This tab is becoming filtered report widgets — state distribution, created vs completed,
          throughput, and per-assignee workload with shared assignee/type/date filters (PLAN.md
          §5a, 4C). Until then, the Overview tab has live aggregates, and the AI Copilot answers
          historical questions from the same data shown fresh here.
        </p>
      </Card>
    </div>
  );
}

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

function FreshnessBar() {
  const qc = useQueryClient();
  const toast = useToast();
  // updatedAt at the moment a refresh was triggered; non-null = actively watching
  const [baseline, setBaseline] = useState<string | null>(null);
  const fresh = useQuery({
    queryKey: ["freshness"],
    queryFn: fetchFreshness,
    staleTime: 60_000,
    // while a refresh is in flight, poll until the table's write-time changes
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
        // safety: stop watching after 8 minutes regardless
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
        Data as of <span className="font-mono text-text-3">{fresh.data.asOf ?? "—"}</span>
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
