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

const enc = encodeURIComponent;

export const fetchHealth = () => get<Health>("/api/health");
export const fetchProjects = () => get<{ value: Project[] }>("/api/projects");

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
