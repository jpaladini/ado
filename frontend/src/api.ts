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
  reason?: string;
}

export const fetchHealth = () => get<Health>("/api/health");
export const askGenie = (question: string, conversationId?: string) =>
  send<GenieAnswer>("/api/genie/ask", "POST", { question, conversationId });
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
export const fetchPullRequests = (p: string, status = "active") =>
  get<{ value: PullRequest[] }>(`/api/projects/${enc(p)}/pullrequests?status=${status}`);
export const fetchBuilds = (p: string) =>
  get<{ value: Build[] }>(`/api/projects/${enc(p)}/builds`);
export const fetchRepos = (p: string) =>
  get<{ value: Repo[] }>(`/api/projects/${enc(p)}/repos`);
export const fetchCommits = (p: string, repoId: string) =>
  get<{ value: Commit[] }>(`/api/projects/${enc(p)}/repos/${enc(repoId)}/commits`);

// -- writes -------------------------------------------------------------------

export const setWorkItemState = (p: string, id: number, state: string) =>
  send(`/api/projects/${enc(p)}/workitems/${id}/state`, "PATCH", { state });

export const addWorkItemComment = (p: string, id: number, text: string) =>
  send(`/api/projects/${enc(p)}/workitems/${id}/comments`, "POST", { text });

export const votePullRequest = (p: string, repoId: string, prId: number, vote: number) =>
  send(`/api/projects/${enc(p)}/repos/${enc(repoId)}/pullrequests/${prId}/vote`, "PUT", { vote });

export const setPullRequestStatus = (p: string, repoId: string, prId: number, status: string) =>
  send(`/api/projects/${enc(p)}/repos/${enc(repoId)}/pullrequests/${prId}`, "PATCH", { status });
