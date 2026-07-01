import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { askGenie, fetchFreshness, fetchHealth, refreshAnalyticsData, type GenieAnswer } from "../api";
import { Card, H1 } from "../components/ui";
import { Spark } from "../components/icons";
import { useToast } from "../components/Toast";

const SUGGESTIONS = [
  "How many open work items are there by state?",
  "What was our daily open-item trend over the last 30 days?",
  "Which work item types have the most items in progress?",
  "How many items were completed this month?",
];

interface Turn {
  question: string;
  answer?: GenieAnswer;
  error?: string;
}

export default function Analytics() {
  const health = useQuery({ queryKey: ["health"], queryFn: fetchHealth });
  const [turns, setTurns] = useState<Turn[]>([]);
  const [q, setQ] = useState("");
  const conversationId = useRef<string | undefined>(undefined);

  const mut = useMutation({
    mutationFn: (question: string) => askGenie(question, conversationId.current),
    onSuccess: (answer) => {
      conversationId.current = answer.conversationId;
      setTurns((t) => [...t.slice(0, -1), { ...t[t.length - 1], answer }]);
    },
    onError: (e) => {
      setTurns((t) => [...t.slice(0, -1), { ...t[t.length - 1], error: (e as Error).message }]);
    },
  });

  const submit = (question: string) => {
    const text = question.trim();
    if (!text || mut.isPending) return;
    setTurns((t) => [...t, { question: text }]);
    setQ("");
    mut.mutate(text);
  };

  const configured = health.data?.genie_configured;

  return (
    <div className="mx-auto max-w-[840px]">
      <H1>Analytics</H1>
      <p className="m-0 mt-[5px] text-[12.5px] text-muted">
        Ask questions about your Azure DevOps data in plain language — answered by Databricks Genie
        over the ingested Delta tables.
      </p>
      <FreshnessBar />

      {configured === false && (
        <Card className="mt-5 p-[16px_18px]">
          <div className="text-[13px] font-semibold text-text">Genie isn’t set up yet</div>
          <p className="mt-1 text-[12.5px] text-muted">
            Run the <span className="font-mono">ado-analytics-ingest</span> job, create a Genie
            Space over the tables, then store its ID in the{" "}
            <span className="font-mono">ado/genie_space_id</span> secret. Full steps in{" "}
            <span className="font-mono">docs/GENIE.md</span>. No redeploy needed — the app picks it
            up at runtime.
          </p>
        </Card>
      )}

      {turns.length === 0 && configured !== false && (
        <div className="mt-5 flex flex-wrap gap-2">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              onClick={() => submit(s)}
              className="rounded-[7px] border border-border bg-surface px-[13px] py-[7px] text-left text-[12px] text-text-3 hover:border-faint"
            >
              {s}
            </button>
          ))}
        </div>
      )}

      <div className="mt-5 space-y-4">
        {turns.map((t, i) => (
          <TurnView key={i} turn={t} pending={i === turns.length - 1 && mut.isPending} />
        ))}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit(q);
        }}
        className="sticky bottom-4 mt-6 flex items-center gap-2 rounded-[10px] border border-border bg-surface p-2 shadow-[0_4px_16px_rgba(0,0,0,.06)]"
      >
        <span className="ml-2 text-accent">
          <Spark size={15} />
        </span>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={configured === false ? "Configure Genie to ask questions…" : "Ask about your work items…"}
          disabled={configured === false || mut.isPending}
          className="w-full border-none bg-transparent text-[13px] text-text outline-none placeholder:text-faint disabled:opacity-60"
        />
        <button
          type="submit"
          disabled={configured === false || mut.isPending || !q.trim()}
          className="rounded-[7px] bg-accent px-[16px] py-[8px] text-[12px] font-semibold text-white hover:bg-accent-hover disabled:opacity-50"
        >
          {mut.isPending ? "Thinking…" : "Ask"}
        </button>
      </form>
    </div>
  );
}

function FreshnessBar() {
  const qc = useQueryClient();
  const toast = useToast();
  const [refreshing, setRefreshing] = useState(false);
  const fresh = useQuery({ queryKey: ["freshness"], queryFn: fetchFreshness, staleTime: 60_000 });

  const refresh = useMutation({
    mutationFn: refreshAnalyticsData,
    onSuccess: (r) => {
      if (r.started) {
        toast("Data refresh started — takes ~2 minutes");
        setRefreshing(true);
        // the ingest takes a couple of minutes; re-check freshness afterwards
        setTimeout(() => {
          setRefreshing(false);
          qc.invalidateQueries({ queryKey: ["freshness"] });
        }, 150_000);
      } else {
        toast(r.reason ?? "Could not start refresh");
      }
    },
    onError: (e) => toast((e as Error).message),
  });

  if (!fresh.data?.available) return null;
  return (
    <div className="mt-2 flex items-center gap-2 text-[11.5px] text-faint">
      <span>
        Data as of <span className="font-mono text-text-3">{fresh.data.asOf ?? "—"}</span> · refreshed
        daily at 05:00 UTC
      </span>
      <button
        onClick={() => refresh.mutate()}
        disabled={refresh.isPending || refreshing}
        className="rounded-[6px] border border-border bg-surface px-2 py-[3px] text-[11px] font-semibold text-text-3 hover:border-faint disabled:opacity-50"
      >
        {refreshing ? "Refreshing…" : "Refresh now"}
      </button>
    </div>
  );
}

function TurnView({ turn, pending }: { turn: Turn; pending: boolean }) {
  return (
    <div>
      <div className="mb-2 flex justify-end">
        <span className="max-w-[80%] rounded-[10px] bg-ink-bg px-[14px] py-[8px] text-[13px] text-ink-fg">
          {turn.question}
        </span>
      </div>
      <Card className="p-[14px_16px]">
        {pending && <p className="m-0 animate-pulse text-[12.5px] text-faint">Genie is thinking…</p>}
        {turn.error && <p className="m-0 text-[12.5px] text-danger">{turn.error}</p>}
        {turn.answer && <AnswerView a={turn.answer} />}
      </Card>
    </div>
  );
}

function AnswerView({ a }: { a: GenieAnswer }) {
  const [showSql, setShowSql] = useState(false);
  return (
    <div className="space-y-3">
      {a.queryDescription && <p className="m-0 text-[13px] text-text">{a.queryDescription}</p>}
      {a.text.map((t, i) => (
        <p key={i} className="m-0 whitespace-pre-wrap text-[13px] text-text">
          {t}
        </p>
      ))}
      {a.error && <p className="m-0 text-[12.5px] text-danger">{a.error}</p>}

      {a.columns.length > 0 && (
        <div className="overflow-x-auto rounded-[8px] border border-border-2">
          <table className="w-full border-collapse text-[12.5px]">
            <thead>
              <tr className="bg-surface-2 text-[10.5px] uppercase tracking-[0.5px] text-faint">
                {a.columns.map((c) => (
                  <th key={c} className="px-3 py-2 text-left font-semibold">
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {a.rows.slice(0, 50).map((r, i) => (
                <tr key={i} className="border-t border-line">
                  {r.map((v, j) => (
                    <td key={j} className="px-3 py-[7px] font-mono text-[12px] text-text-2">
                      {v ?? "—"}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          {a.rows.length > 50 && (
            <div className="border-t border-line px-3 py-2 text-[11px] text-faint">
              Showing 50 of {a.rows.length} rows
            </div>
          )}
        </div>
      )}

      {a.sql && (
        <div>
          <button
            onClick={() => setShowSql((s) => !s)}
            className="text-[11.5px] font-semibold text-accent-text hover:underline"
          >
            {showSql ? "Hide SQL" : "Show SQL"}
          </button>
          {showSql && (
            <pre className="mt-2 overflow-x-auto rounded-[8px] bg-surface-2 p-3 font-mono text-[11.5px] leading-relaxed text-text-2">
              {a.sql}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}
