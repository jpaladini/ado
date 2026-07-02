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

export interface CopilotReply {
  reply: string;
  toolCalls: CopilotToolCall[];
  proposals: CopilotProposal[];
  endpoint: string;
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
