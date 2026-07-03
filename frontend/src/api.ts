export interface Project {
  id: string;
  name: string;
  description: string;
  lastUpdateTime?: string;
  state?: string;
}

export interface Health {
  status: string;
  ado_configured: boolean;
  genie_configured?: boolean;
  copilot_configured?: boolean;
}

export interface CopilotToolCall {
  name: string;
  args: Record<string, unknown>;
}

export interface CopilotProposal {
  id: string;
  tool: string; // create_work_item | update_work_item | add_work_item_comment
  args: Record<string, unknown>;
}

export interface CopilotTable {
  name: string;
  columns: string[];
  rows: (string | number | null)[][];
}

export interface CopilotReply {
  reply: string;
  toolCalls: CopilotToolCall[];
  proposals: CopilotProposal[];
  tables?: CopilotTable[];
  endpoint: string;
}

/** POST a table and hand the resulting .xlsx to the browser as a download. */
export async function downloadTableXlsx(t: CopilotTable): Promise<void> {
  const res = await fetch("/api/export/table", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(t),
  });
  if (!res.ok) {
    const b = await res.json().catch(() => ({}));
    throw new Error(b.detail ?? `Export failed (${res.status})`);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${t.name.replace(/[^\w\- ]+/g, "_").slice(0, 40) || "data"}.xlsx`;
  a.click();
  URL.revokeObjectURL(url);
}

export interface GenieAnswer {
  conversationId: string;
  messageId: string;
  status: string | null;
  text: string[];
  sql: string | null;
  queryDescription: string | null;
  columns: string[];
  rows: (string | null)[][];
  error?: string;
}

export interface Me {
  id: string | null;
  displayName: string | null;
}

export interface WorkItem {
  id: number;
  title: string;
  state: string;
  type: string;
  assignedTo: string | null;
  changedDate?: string;
  tags?: string[];
}

export interface WorkItemDetail {
  id: number;
  rev: number;
  title: string;
  state: string;
  type: string;
  reason?: string | null;
  assignedTo: string | null;
  assignedToUnique: string | null;
  description: string; // HTML as stored by ADO
  tags: string[];
  iterationPath: string | null;
  areaPath: string | null;
  createdBy: string | null;
  createdDate?: string;
  changedDate?: string;
}

export interface WorkItemComment {
  id: number;
  text: string; // HTML
  format?: string;
  createdBy: string | null;
  createdDate?: string;
}

export interface Identity {
  displayName: string | null;
  uniqueName: string;
  active: boolean;
}

export interface WorkItemType {
  name: string;
  states: { name: string; category: string }[];
}

export interface WorkItemCreatePayload {
  type: string;
  title: string;
  description?: string;
  assignedTo?: string;
  tags?: string; // "a; b"
  iterationPath?: string;
}

export interface WorkItemUpdatePayload {
  title?: string;
  description?: string;
  assignedTo?: string; // "" clears the assignment
  state?: string;
  tags?: string;
  iterationPath?: string;
}

export interface PullRequest {
  id: number;
  title: string;
  status: string;
  isDraft: boolean;
  createdBy: string | null;
  creationDate?: string;
  repository: string | null;
  repositoryId: string | null;
  sourceRef: string;
  targetRef: string;
}

export interface Build {
  id: number;
  buildNumber: string;
  definition: string | null;
  status: string | null;
  result: string | null;
  requestedFor: string | null;
  startTime?: string;
  finishTime?: string;
  sourceBranch: string;
}

export interface Repo {
  id: string;
  name: string;
  defaultBranch: string;
  webUrl?: string;
}

export interface Commit {
  commitId: string;
  shortId: string;
  comment: string;
  author: string | null;
  date?: string;
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `Request failed (${res.status})`);
  }
  return res.json() as Promise<T>;
}

async function send<T>(path: string, method: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    const b = await res.json().catch(() => ({}));
    throw new Error(b.detail ?? `Request failed (${res.status})`);
  }
  return res.json() as Promise<T>;
}

const enc = encodeURIComponent;

export interface Freshness {
  available: boolean;
  asOf?: string;
  updatedAt?: string | null;
  reason?: string;
}

export interface Whoami {
  user: string;
  source: string;
  store: { available: boolean | null; reason?: string | null };
}

export const fetchWhoami = () => get<Whoami>("/api/whoami");
export const fetchSettings = () => get<{ settings: Record<string, string> }>("/api/settings");
export const putSetting = (key: string, value: string) =>
  send<{ ok: boolean }>("/api/settings", "PUT", { key, value });

export const fetchHealth = () => get<Health>("/api/health");
export const askGenie = (question: string, conversationId?: string) =>
  send<GenieAnswer>("/api/genie/ask", "POST", { question, conversationId });
export interface WorkItemSuggestion {
  title?: string;
  description?: string;
  tags?: string;
  type?: string;
  acceptanceCriteria?: string;
}

export const suggestWorkItem = (body: {
  project: string;
  type?: string;
  title?: string;
  description?: string;
}) =>
  send<{ suggestion: WorkItemSuggestion; endpoint: string }>(
    "/api/ai/suggest-workitem", "POST", body);

export const askCopilot = (
  project: string,
  message: string,
  history: { role: "user" | "assistant"; content: string }[],
) => send<CopilotReply>("/api/copilot/chat", "POST", { project, message, history });
export const fetchFreshness = () => get<Freshness>("/api/analytics/freshness");
export const refreshAnalyticsData = () =>
  send<{ started: boolean; runId?: number; reason?: string }>("/api/analytics/refresh", "POST");
export const fetchMe = () => get<Me>("/api/me");
export const fetchProjects = () => get<{ value: Project[] }>("/api/projects");

export interface Analytics {
  byCategory: Record<string, number>;
  open: number;
  total: number;
  trend: { date: string; count: number }[];
  range: string;
  available: boolean;
}

export const fetchAnalytics = (p: string, range: string) =>
  get<Analytics>(`/api/projects/${enc(p)}/analytics?range=${range}`);

// -- 4C reports (all durations are 5-day-workweek business days) -------------------

export interface ReportKpis {
  throughput: number;
  created: number;
  netFlow: number;
  wip: number;
  cycleP50: number;
  cycleP85: number;
  oldestWipDays: number;
}

export interface CycleItem {
  id: number;
  title: string;
  type: string;
  cycleDays: number;
  leadDays: number;
  cycleBdays: number;
  leadBdays: number;
  closedDate: string;
}

export interface OpenItem {
  id: number;
  title: string;
  type: string;
  state: string;
  category: string;
  assignee: string | null;
  ageDays: number;
  ageBdays: number;
}

export interface ReportsPayload {
  range: string;
  days: number;
  durationUnit: string;
  kpis: ReportKpis;
  createdPerDay: { dateSK: number; count: number }[];
  completedPerDay: { dateSK: number; count: number }[];
  cycleItems: CycleItem[];
  cfd: { date: string; category: string; count: number }[];
  openItems: OpenItem[];
}

export const fetchReports = (p: string, range: string, types: string[], assignees: string[]) =>
  get<ReportsPayload>(
    `/api/projects/${enc(p)}/reports?range=${range}` +
      (types.length ? `&types=${enc(types.join(","))}` : "") +
      (assignees.length ? `&assignees=${enc(assignees.join(","))}` : ""),
  );

// -- code-change PRs (coding agent apply path) ---------------------------------------

export interface CodePrResult {
  prId: number;
  branch: string;
  title: string;
}

export const createCodePr = (
  p: string,
  repoId: string,
  body: {
    baseBranch: string;
    title: string;
    description?: string;
    edits: { path: string; content: string }[];
  },
) => send<CodePrResult>(`/api/projects/${enc(p)}/repos/${enc(repoId)}/code-pr`, "POST", body);

// -- copilot session history --------------------------------------------------------

export interface CopilotSessionMeta {
  id: string;
  title: string;
  updatedAt: string;
}

export interface CopilotSessionDetail {
  id: string;
  project: string;
  title: string;
  state: { turns?: unknown[]; outcomes?: Record<string, string> };
}

export const fetchCopilotSessions = (project: string) =>
  get<{ value: CopilotSessionMeta[] }>(`/api/copilot/sessions?project=${enc(project)}`);
export const fetchCopilotSession = (id: string) =>
  get<CopilotSessionDetail>(`/api/copilot/sessions/${enc(id)}`);
export const saveCopilotSession = (body: {
  id?: string;
  project: string;
  title?: string;
  state: { turns: unknown[]; outcomes: Record<string, string> };
}) => send<{ id: string; title: string }>("/api/copilot/sessions", "PUT", body);
export const deleteCopilotSession = (id: string) =>
  send<{ ok: boolean }>(`/api/copilot/sessions/${enc(id)}`, "DELETE");

// -- global search (work items + code) ---------------------------------------------

export interface SearchWorkItem {
  id: number;
  title: string;
  type: string;
  state: string;
  assignedTo: string | null;
  snippet: string | null;
}

export interface SearchCodeMatch {
  line: number;
  text: string;
}

export interface SearchCodeFile {
  repo: string;
  repoId: string;
  branch: string;
  path: string;
  nameHit: boolean;
  matches: SearchCodeMatch[];
}

export interface SearchResponse {
  query: string;
  workItems: { available: boolean; reason?: string; results: SearchWorkItem[] };
  pullRequests: { available: boolean; reason?: string; results: PullRequest[] };
  code: {
    available: boolean;
    reason?: string;
    results: SearchCodeFile[];
    truncated?: boolean;
    indexedFiles?: number;
  };
}

export const globalSearch = (p: string, q: string) =>
  get<SearchResponse>(`/api/projects/${enc(p)}/search?q=${enc(q)}`);

// -- report builder (4E: UC metric-view semantic layer) ---------------------------

export interface BuilderField {
  name: string;
  label: string;
  kind?: string; // dimensions: "category" | "date"
  format?: string; // measures: "int" | "days"
}

export interface BuilderMeta {
  available: boolean;
  reason?: string;
  dimensions: BuilderField[];
  measures: BuilderField[];
  view: string;
  source: string;
  durationUnit: string;
}

export interface BuilderDefinition {
  dimensions: string[];
  measures: string[];
  filters?: { dimension: string; values: string[] }[];
  limit?: number;
  chartType?: string; // presentation only — ignored by the run endpoint
}

export interface BuilderResult {
  columns: string[];
  rows: Record<string, string | number | null>[];
}

export interface SavedReport {
  id: string;
  name: string;
  definition: string; // JSON-encoded BuilderDefinition
  updatedAt: string;
}

export const fetchBuilderMeta = () => get<BuilderMeta>("/api/reports/builder/meta");
export const runBuilderReport = (definition: BuilderDefinition) =>
  send<BuilderResult>("/api/reports/builder/run", "POST", {
    dimensions: definition.dimensions,
    measures: definition.measures,
    filters: definition.filters ?? [],
    limit: definition.limit,
  });
export const fetchSavedReports = () =>
  get<{ value: SavedReport[] }>("/api/reports/saved");
export const saveReport = (name: string, definition: BuilderDefinition, id?: string) =>
  send<{ id: string; name: string }>("/api/reports/saved", "PUT", { id, name, definition });
export const deleteSavedReport = (id: string) =>
  send<{ ok: boolean }>(`/api/reports/saved/${enc(id)}`, "DELETE");

export const fetchWorkItems = (p: string) =>
  get<{ value: WorkItem[] }>(`/api/projects/${enc(p)}/workitems`);
export const fetchWorkItemDetail = (p: string, id: number) =>
  get<WorkItemDetail>(`/api/projects/${enc(p)}/workitems/${id}`);
export const fetchWorkItemComments = (p: string, id: number) =>
  get<{ value: WorkItemComment[] }>(`/api/projects/${enc(p)}/workitems/${id}/comments`);
export const fetchWorkItemTypes = (p: string) =>
  get<{ value: WorkItemType[] }>(`/api/projects/${enc(p)}/workitemtypes`);
export const fetchIterations = (p: string) =>
  get<{ value: string[] }>(`/api/projects/${enc(p)}/iterations`);
export const searchIdentities = (q: string) =>
  get<{ value: Identity[] }>(`/api/identities?q=${enc(q)}`);
export const fetchPullRequests = (p: string, status = "active") =>
  get<{ value: PullRequest[] }>(`/api/projects/${enc(p)}/pullrequests?status=${status}`);
export const fetchBuilds = (p: string) =>
  get<{ value: Build[] }>(`/api/projects/${enc(p)}/builds`);
export const fetchRepos = (p: string) =>
  get<{ value: Repo[] }>(`/api/projects/${enc(p)}/repos`);
export const fetchCommits = (p: string, repoId: string) =>
  get<{ value: Commit[] }>(`/api/projects/${enc(p)}/repos/${enc(repoId)}/commits`);

// -- code browsing & PR review ---------------------------------------------------

export interface Branch {
  name: string;
  objectId: string;
}

export interface TreeEntry {
  path: string;
  name: string;
  isFolder: boolean;
  size?: number;
}

export interface FileContent {
  path: string;
  content: string;
  binary: boolean;
  truncated: boolean;
  commitId?: string;
}

export interface PrFile {
  path: string;
  originalPath?: string | null;
  changeType: string;
}

export interface PrFiles {
  iteration: number | null;
  sourceCommit: string | null;
  targetCommit: string | null;
  files: PrFile[];
}

export interface PrDiff {
  path: string;
  diff: string;
  binary: boolean;
  tooLarge?: boolean;
  addedLines: number;
  removedLines: number;
  changeType?: string | null;
}

export interface PrThreadComment {
  id: number;
  author: string | null;
  content: string;
  publishedDate?: string;
}

export interface PrThread {
  id: number;
  status: string | null;
  filePath: string | null;
  line: number | null;
  comments: PrThreadComment[];
}

export const fetchBranches = (p: string, rid: string) =>
  get<{ value: Branch[] }>(`/api/projects/${enc(p)}/repos/${enc(rid)}/branches`);
export const fetchTree = (p: string, rid: string, branch: string, path = "/") =>
  get<{ value: TreeEntry[] }>(
    `/api/projects/${enc(p)}/repos/${enc(rid)}/tree?branch=${enc(branch)}&path=${enc(path)}`);
export const fetchFile = (p: string, rid: string, path: string, branch: string) =>
  get<FileContent>(
    `/api/projects/${enc(p)}/repos/${enc(rid)}/file?path=${enc(path)}&branch=${enc(branch)}`);
export const fetchPrFiles = (p: string, rid: string, prId: number) =>
  get<PrFiles>(`/api/projects/${enc(p)}/repos/${enc(rid)}/pullrequests/${prId}/files`);
export const fetchPrDiff = (p: string, rid: string, prId: number, path: string) =>
  get<PrDiff>(
    `/api/projects/${enc(p)}/repos/${enc(rid)}/pullrequests/${prId}/diff?path=${enc(path)}`);
export const fetchPrThreads = (p: string, rid: string, prId: number) =>
  get<{ value: PrThread[] }>(`/api/projects/${enc(p)}/repos/${enc(rid)}/pullrequests/${prId}/threads`);
export const createPrThread = (
  p: string,
  rid: string,
  prId: number,
  body: { comment: string; filePath?: string; line?: number },
) =>
  send<{ id: number }>(
    `/api/projects/${enc(p)}/repos/${enc(rid)}/pullrequests/${prId}/threads`, "POST", body);

export interface ReviewComment {
  path: string;
  line: number;
  comment: string;
  severity: "nit" | "suggestion" | "issue";
}

export interface PrReview {
  summary: string;
  comments: ReviewComment[];
  filesReviewed: number;
  skipped: string[];
  dropped: number;
  endpoint: string;
}

export const explainFile = (p: string, rid: string, path: string, branch: string) =>
  send<{ explanation: string; keyPoints: string; endpoint: string }>(
    "/api/ai/explain-file", "POST", { project: p, repositoryId: rid, path, branch });

export const reviewPr = (p: string, rid: string, prId: number, path?: string) =>
  send<PrReview>("/api/ai/review-pr", "POST", {
    project: p, repositoryId: rid, prId, ...(path ? { path } : {}),
  });

// -- writes -------------------------------------------------------------------

export const setWorkItemState = (p: string, id: number, state: string) =>
  send(`/api/projects/${enc(p)}/workitems/${id}/state`, "PATCH", { state });

export const createWorkItem = (p: string, body: WorkItemCreatePayload) =>
  send<{ id: number; title: string; state: string }>(
    `/api/projects/${enc(p)}/workitems`, "POST", body);

export const updateWorkItem = (p: string, id: number, body: WorkItemUpdatePayload) =>
  send<WorkItemDetail>(`/api/projects/${enc(p)}/workitems/${id}`, "PATCH", body);

export const addWorkItemComment = (p: string, id: number, text: string) =>
  send(`/api/projects/${enc(p)}/workitems/${id}/comments`, "POST", { text });

export const votePullRequest = (p: string, repoId: string, prId: number, vote: number) =>
  send(`/api/projects/${enc(p)}/repos/${enc(repoId)}/pullrequests/${prId}/vote`, "PUT", { vote });

export const setPullRequestStatus = (p: string, repoId: string, prId: number, status: string) =>
  send(`/api/projects/${enc(p)}/repos/${enc(repoId)}/pullrequests/${prId}`, "PATCH", { status });
