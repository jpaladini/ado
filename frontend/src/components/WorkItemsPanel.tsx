import { useQuery } from "@tanstack/react-query";
import { fetchWorkItems } from "../api";
import { Badge, Empty, ErrorMsg, Loading, relTime, workItemTone } from "./ui";

export default function WorkItemsPanel({ project }: { project: string }) {
  const q = useQuery({
    queryKey: ["workitems", project],
    queryFn: () => fetchWorkItems(project),
  });

  if (q.isLoading) return <Loading />;
  if (q.isError) return <ErrorMsg error={q.error} />;
  const items = q.data?.value ?? [];
  if (!items.length) return <Empty>No work items.</Empty>;

  return (
    <ul className="divide-y divide-slate-100">
      {items.map((wi) => (
        <li key={wi.id} className="flex items-center gap-3 py-2.5">
          <span className="w-14 shrink-0 text-xs text-slate-400">#{wi.id}</span>
          <span className="w-24 shrink-0 text-xs text-slate-500">{wi.type}</span>
          <span className="flex-1 truncate text-sm text-slate-800" title={wi.title}>
            {wi.title}
          </span>
          <Badge tone={workItemTone(wi.state)}>{wi.state}</Badge>
          <span className="w-32 shrink-0 truncate text-right text-xs text-slate-500">
            {wi.assignedTo ?? "Unassigned"}
          </span>
          <span className="w-20 shrink-0 text-right text-xs text-slate-400">
            {relTime(wi.changedDate)}
          </span>
        </li>
      ))}
    </ul>
  );
}
