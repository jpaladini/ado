"""Thin async client for the Azure DevOps REST API.

This is the *operational* data plane — it talks to the live ADO API. No ADO data
is persisted locally. Auth is PAT-based (Basic auth with an empty username), which
mirrors the original mobile app; corporate will swap this for Entra OAuth.
"""
import base64
import difflib
import json as jsonlib
from typing import Any
from urllib.parse import quote

import httpx

from app.config import settings

API_VERSION = "7.1"

# Files larger than this are flagged truncated (UI) / tooLarge (diffs).
MAX_FILE_CHARS = 200_000


def unified_diff(old: str | None, new: str | None, path: str) -> dict[str, Any]:
    """Unified diff between two file versions; None on either side means the
    file was added/deleted. Returns the diff text plus +/- line counts."""
    lines = list(
        difflib.unified_diff(
            (old or "").splitlines(),
            (new or "").splitlines(),
            fromfile=f"a{path}",
            tofile=f"b{path}",
            lineterm="",
        )
    )
    added = sum(1 for l in lines if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in lines if l.startswith("-") and not l.startswith("---"))
    return {"diff": "\n".join(lines), "addedLines": added, "removedLines": removed}


class ADOConfigError(RuntimeError):
    """Raised when the ADO org URL / PAT are not configured."""


def _auth_header(pat: str) -> str:
    token = base64.b64encode(f":{pat}".encode()).decode()
    return f"Basic {token}"


def _user(obj: dict[str, Any] | None) -> str | None:
    """Extract a display name from an ADO identity ref."""
    if not obj:
        return None
    return obj.get("displayName") or obj.get("name")


class ADOClient:
    def __init__(self, org_url: str | None = None, pat: str | None = None) -> None:
        self.org_url = (org_url or settings.ado_org_url).rstrip("/")
        self.pat = pat or settings.ado_pat
        if not self.org_url or not self.pat:
            raise ADOConfigError("ADO_ORG_URL and ADO_PAT must be set")

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.org_url,
            headers={"Authorization": _auth_header(self.pat), "Accept": "application/json"},
            timeout=30.0,
        )

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = {"api-version": API_VERSION, **(params or {})}
        async with self._client() as client:
            resp = await client.get(path, params=params)
            resp.raise_for_status()
            return resp.json()

    async def _get_text(self, path: str, params: dict[str, Any] | None = None) -> str:
        """GET an endpoint that answers plaintext (build logs), not JSON."""
        params = {"api-version": API_VERSION, **(params or {})}
        async with self._client() as client:
            resp = await client.get(path, params=params, headers={"Accept": "text/plain"})
            resp.raise_for_status()
            return resp.text

    async def _post(self, path: str, body: dict[str, Any], params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = {"api-version": API_VERSION, **(params or {})}
        async with self._client() as client:
            resp = await client.post(path, params=params, json=body)
            resp.raise_for_status()
            return resp.json()

    async def _send(
        self,
        method: str,
        path: str,
        *,
        body: Any = None,
        params: dict[str, Any] | None = None,
        content_type: str | None = None,
    ) -> dict[str, Any]:
        """Generic write request. Use content_type to send a non-default media
        type (e.g. application/json-patch+json for work-item updates)."""
        params = {"api-version": API_VERSION, **(params or {})}
        async with self._client() as client:
            if content_type:
                resp = await client.request(
                    method, path, params=params,
                    content=jsonlib.dumps(body),
                    headers={"Content-Type": content_type},
                )
            else:
                resp = await client.request(method, path, params=params, json=body)
            resp.raise_for_status()
            return resp.json() if resp.content else {}

    # -- identity & projects --------------------------------------------------

    async def connection_data(self) -> dict[str, Any]:
        # connectionData is unversioned — sending api-version=7.1 gets a 400,
        # which silently broke everything that resolves the current user
        # (PR approve resolves the reviewer id through here).
        async with self._client() as client:
            resp = await client.get("/_apis/connectionData")
            resp.raise_for_status()
            data = resp.json()
        user = data.get("authenticatedUser", {})
        return {
            "id": user.get("id"),
            "displayName": user.get("providerDisplayName") or user.get("customDisplayName"),
        }

    async def list_projects(self) -> list[dict[str, Any]]:
        data = await self._get("/_apis/projects")
        return [
            {
                "id": p["id"],
                "name": p["name"],
                "description": p.get("description", ""),
                "lastUpdateTime": p.get("lastUpdateTime"),
                "state": p.get("state"),
            }
            for p in data.get("value", [])
        ]

    # -- work items -----------------------------------------------------------

    async def get_work_item(self, work_item_id: int) -> dict[str, Any]:
        """Full detail for one work item (all fields come back by default)."""
        data = await self._get(f"/_apis/wit/workitems/{work_item_id}")
        f = data.get("fields", {})
        return {
            "id": data.get("id"),
            "rev": data.get("rev"),
            "title": f.get("System.Title"),
            "state": f.get("System.State"),
            "type": f.get("System.WorkItemType"),
            "reason": f.get("System.Reason"),
            "assignedTo": _user(f.get("System.AssignedTo")),
            "assignedToUnique": (f.get("System.AssignedTo") or {}).get("uniqueName"),
            "description": f.get("System.Description") or "",
            "tags": [t.strip() for t in (f.get("System.Tags") or "").split(";") if t.strip()],
            "iterationPath": f.get("System.IterationPath"),
            "areaPath": f.get("System.AreaPath"),
            "createdBy": _user(f.get("System.CreatedBy")),
            "createdDate": f.get("System.CreatedDate"),
            "changedDate": f.get("System.ChangedDate"),
        }

    async def list_work_items(self, project: str, top: int = 100) -> list[dict[str, Any]]:
        """Run a WIQL query for the project's most-recently-changed items, then
        batch-fetch their fields."""
        proj = quote(project, safe="")
        wiql = {
            "query": (
                "SELECT [System.Id] FROM WorkItems "
                "WHERE [System.TeamProject] = @project "
                "ORDER BY [System.ChangedDate] DESC"
            )
        }
        result = await self._post(f"/{proj}/_apis/wit/wiql", wiql, params={"$top": top})
        ids = [w["id"] for w in result.get("workItems", [])][:top]
        if not ids:
            return []
        fields = [
            "System.Id",
            "System.Title",
            "System.State",
            "System.WorkItemType",
            "System.AssignedTo",
            "System.ChangedDate",
            "System.Tags",
        ]
        batch = await self._post(
            "/_apis/wit/workitemsbatch", {"ids": ids, "fields": fields}
        )
        out = []
        for item in batch.get("value", []):
            f = item.get("fields", {})
            out.append(
                {
                    "id": item.get("id"),
                    "title": f.get("System.Title"),
                    "state": f.get("System.State"),
                    "type": f.get("System.WorkItemType"),
                    "assignedTo": _user(f.get("System.AssignedTo")),
                    "changedDate": f.get("System.ChangedDate"),
                    "tags": [t.strip() for t in (f.get("System.Tags") or "").split(";") if t.strip()],
                }
            )
        return out

    async def list_work_item_types(self, project: str) -> list[dict[str, Any]]:
        """Creatable work item types (hidden category filtered out) with their states."""
        proj = quote(project, safe="")
        types = await self._get(f"/{proj}/_apis/wit/workitemtypes")
        try:
            hidden_cat = await self._get(f"/{proj}/_apis/wit/workitemtypecategories/Microsoft.HiddenCategory")
            hidden = {t.get("name") for t in hidden_cat.get("workItemTypes", [])}
        except httpx.HTTPStatusError:
            hidden = set()
        out = []
        for t in types.get("value", []):
            if t["name"] in hidden:
                continue
            out.append(
                {
                    "name": t["name"],
                    "states": [
                        {"name": s.get("name"), "category": s.get("category")}
                        for s in t.get("states", [])
                    ],
                }
            )
        return out

    async def list_iterations(self, project: str) -> list[str]:
        """Iteration paths usable in System.IterationPath (root first)."""
        proj = quote(project, safe="")
        data = await self._get(
            f"/{proj}/_apis/wit/classificationnodes/Iterations", params={"$depth": 10}
        )

        def walk(node: dict[str, Any], prefix: str) -> list[str]:
            path = f"{prefix}\\{node['name']}" if prefix else node["name"]
            paths = [path]
            for child in node.get("children") or []:
                paths.extend(walk(child, path))
            return paths

        return walk(data, "")

    async def search_identities(self, query: str, max_results: int = 10) -> list[dict[str, Any]]:
        """User search for the assignee picker (Identity Picker API — same one the
        ADO web UI uses; requires both MinResults and MaxResults)."""
        body = {
            "query": query,
            "identityTypes": ["user"],
            "operationScopes": ["ims", "source"],
            "options": {"MinResults": min(5, max_results), "MaxResults": max_results},
            "properties": ["DisplayName", "Mail", "SamAccountName", "Active"],
        }
        data = await self._send(
            "POST",
            "/_apis/IdentityPicker/Identities",
            body=body,
            params={"api-version": "7.1-preview.1"},
        )
        out = []
        for result in data.get("results", []):
            for ident in result.get("identities", []):
                unique = ident.get("mail") or ident.get("samAccountName") or ident.get("signInAddress")
                if not unique:
                    continue
                out.append(
                    {
                        "displayName": ident.get("displayName"),
                        "uniqueName": unique,
                        "active": ident.get("active", True),
                    }
                )
        return out

    async def list_work_item_comments(self, project: str, work_item_id: int) -> list[dict[str, Any]]:
        proj = quote(project, safe="")
        data = await self._get(
            f"/{proj}/_apis/wit/workItems/{work_item_id}/comments",
            params={"api-version": "7.1-preview.3", "order": "desc"},
        )
        return [
            {
                "id": c.get("id"),
                "text": c.get("text") or "",
                "format": c.get("format"),
                "createdBy": _user(c.get("createdBy")),
                "createdDate": c.get("createdDate"),
            }
            for c in data.get("comments", [])
        ]

    # -- pull requests --------------------------------------------------------

    async def list_pull_requests(
        self, project: str, status: str = "active", top: int = 50
    ) -> list[dict[str, Any]]:
        proj = quote(project, safe="")
        data = await self._get(
            f"/{proj}/_apis/git/pullrequests",
            params={"searchCriteria.status": status, "$top": top},
        )
        out = []
        for pr in data.get("value", []):
            votes = [int(r.get("vote") or 0) for r in (pr.get("reviewers") or [])]
            out.append(
                {
                    "id": pr.get("pullRequestId"),
                    "title": pr.get("title"),
                    "description": (pr.get("description") or "")[:4000],
                    "status": pr.get("status"),
                    "isDraft": pr.get("isDraft", False),
                    "createdBy": _user(pr.get("createdBy")),
                    "creationDate": pr.get("creationDate"),
                    "repository": (pr.get("repository") or {}).get("name"),
                    "repositoryId": (pr.get("repository") or {}).get("id"),
                    "sourceRef": (pr.get("sourceRefName") or "").replace("refs/heads/", ""),
                    "targetRef": (pr.get("targetRefName") or "").replace("refs/heads/", ""),
                    # ADO's approval state, not just ours: at least one approve
                    # (10) or approve-with-suggestions (5), and nobody waiting/
                    # rejecting. Branch policies still gate the actual completion.
                    "isApproved": any(v >= 5 for v in votes) and all(v >= 0 for v in votes),
                    "mergeStatus": pr.get("mergeStatus"),  # e.g. succeeded | conflicts
                }
            )
        return out

    async def complete_pull_request(
        self, project: str, repo_id: str, pr_id: int, delete_source_branch: bool = True
    ) -> dict[str, Any]:
        """Complete (merge) a PR — a HUMAN-initiated action from the UI, never
        the copilot's. ADO enforces branch policies at completion; failures
        (required build, min reviewers) surface as errors, not silent skips."""
        proj, rid = quote(project, safe=""), quote(repo_id, safe="")
        pr = await self._get(f"/{proj}/_apis/git/repositories/{rid}/pullRequests/{pr_id}")
        last_merge_source = (pr.get("lastMergeSourceCommit") or {}).get("commitId")
        if not last_merge_source:
            raise ValueError("PR has no merge source commit (still merging or conflicted)")
        done = await self._send(
            "PATCH",
            f"/{proj}/_apis/git/repositories/{rid}/pullRequests/{pr_id}",
            body={
                "status": "completed",
                "lastMergeSourceCommit": {"commitId": last_merge_source},
                "completionOptions": {"deleteSourceBranch": delete_source_branch},
            },
        )
        return {"id": done.get("pullRequestId"), "status": done.get("status")}

    # -- pipelines (builds) ---------------------------------------------------

    async def list_builds(self, project: str, top: int = 25) -> list[dict[str, Any]]:
        proj = quote(project, safe="")
        data = await self._get(
            f"/{proj}/_apis/build/builds",
            params={"$top": top, "queryOrder": "queueTimeDescending"},
        )
        out = []
        for b in data.get("value", []):
            out.append(
                {
                    "id": b.get("id"),
                    "buildNumber": b.get("buildNumber"),
                    "definition": (b.get("definition") or {}).get("name"),
                    "status": b.get("status"),
                    "result": b.get("result"),
                    "requestedFor": _user(b.get("requestedFor")),
                    "startTime": b.get("startTime"),
                    "finishTime": b.get("finishTime"),
                    "sourceBranch": (b.get("sourceBranch") or "").replace("refs/heads/", ""),
                }
            )
        return out

    async def get_build_timeline(self, project: str, build_id: int) -> list[dict[str, Any]]:
        """Stage/job/step tree for one build. Flat records with parentId links;
        each may carry a log id and per-step issues (error/warning messages)."""
        proj = quote(project, safe="")
        data = await self._get(f"/{proj}/_apis/build/builds/{build_id}/timeline")
        out = []
        for r in data.get("records", []):
            out.append(
                {
                    "id": r.get("id"),
                    "parentId": r.get("parentId"),
                    "type": r.get("type"),  # Stage | Phase | Job | Task | Checkpoint
                    "name": r.get("name"),
                    "state": r.get("state"),
                    "result": r.get("result"),
                    "order": r.get("order"),
                    "startTime": r.get("startTime"),
                    "finishTime": r.get("finishTime"),
                    "errorCount": r.get("errorCount") or 0,
                    "warningCount": r.get("warningCount") or 0,
                    "logId": (r.get("log") or {}).get("id"),
                    "issues": [
                        {"type": i.get("type"), "message": i.get("message")}
                        for i in (r.get("issues") or [])
                        if i.get("message")
                    ],
                }
            )
        return sorted(out, key=lambda r: (r["order"] is None, r["order"] or 0))

    async def get_build_log(
        self, project: str, build_id: int, log_id: int, max_chars: int = MAX_FILE_CHARS
    ) -> dict[str, Any]:
        """Plaintext content of one build log. Long logs keep the TAIL — that's
        where a failed step's traceback lives."""
        proj = quote(project, safe="")
        text = await self._get_text(f"/{proj}/_apis/build/builds/{build_id}/logs/{log_id}")
        truncated = len(text) > max_chars
        return {
            "logId": log_id,
            "truncated": truncated,
            "content": text[-max_chars:] if truncated else text,
        }

    # -- repos & commits ------------------------------------------------------

    async def list_repos(self, project: str) -> list[dict[str, Any]]:
        proj = quote(project, safe="")
        data = await self._get(f"/{proj}/_apis/git/repositories")
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "defaultBranch": (r.get("defaultBranch") or "").replace("refs/heads/", ""),
                "webUrl": r.get("webUrl"),
            }
            for r in data.get("value", [])
        ]

    # -- code browsing ----------------------------------------------------------

    async def list_branches(self, project: str, repo_id: str) -> list[dict[str, Any]]:
        proj, rid = quote(project, safe=""), quote(repo_id, safe="")
        data = await self._get(
            f"/{proj}/_apis/git/repositories/{rid}/refs", params={"filter": "heads/"}
        )
        return [
            {"name": r["name"].removeprefix("refs/heads/"), "objectId": r.get("objectId")}
            for r in data.get("value", [])
        ]

    async def get_tree(
        self, project: str, repo_id: str, branch: str, scope_path: str = "/"
    ) -> list[dict[str, Any]]:
        """One level of a repo tree at scope_path (lazy expansion — never Full)."""
        proj, rid = quote(project, safe=""), quote(repo_id, safe="")
        data = await self._get(
            f"/{proj}/_apis/git/repositories/{rid}/items",
            params={
                "recursionLevel": "OneLevel",
                "scopePath": scope_path,
                "versionDescriptor.version": branch,
                "versionDescriptor.versionType": "branch",
            },
        )
        entries = []
        for i in data.get("value", []):
            path = i.get("path") or ""
            if path.rstrip("/") == scope_path.rstrip("/"):
                continue  # ADO echoes the scoped folder itself
            entries.append(
                {
                    "path": path,
                    "name": path.rsplit("/", 1)[-1],
                    "isFolder": bool(i.get("isFolder")),
                    "size": i.get("size"),
                }
            )
        return sorted(entries, key=lambda e: (not e["isFolder"], e["name"].lower()))

    async def get_file(
        self,
        project: str,
        repo_id: str,
        path: str,
        version: str | None = None,
        version_type: str = "branch",
    ) -> dict[str, Any]:
        proj, rid = quote(project, safe=""), quote(repo_id, safe="")
        params: dict[str, Any] = {"path": path, "includeContent": "true", "$format": "json"}
        if version:
            params["versionDescriptor.version"] = version
            params["versionDescriptor.versionType"] = version_type
        data = await self._get(f"/{proj}/_apis/git/repositories/{rid}/items", params=params)
        content = data.get("content")
        return {
            "path": data.get("path") or path,
            "objectId": data.get("objectId"),
            "commitId": data.get("commitId"),
            "binary": content is None,
            "truncated": len(content or "") > MAX_FILE_CHARS,
            "content": (content or "")[:MAX_FILE_CHARS],
        }

    async def list_file_paths(self, project: str, repo_id: str, branch: str) -> list[str]:
        """Every file path in a branch (recursionLevel=Full, folders excluded).
        Used by the BFF code-search index — the org has no Code Search extension."""
        proj, rid = quote(project, safe=""), quote(repo_id, safe="")
        data = await self._get(
            f"/{proj}/_apis/git/repositories/{rid}/items",
            params={
                "recursionLevel": "Full",
                "versionDescriptor.version": branch,
                "versionDescriptor.versionType": "branch",
            },
        )
        return [
            i["path"] for i in data.get("value", [])
            if i.get("path") and not i.get("isFolder")
        ]

    async def get_files_bulk(
        self, project: str, repo_id: str, branch: str, paths: list[str],
        max_chars: int = 100_000, concurrency: int = 10,
    ) -> dict[str, str]:
        """Fetch many files' text content over one connection pool. Binary files
        (no JSON content) and failures are skipped — search treats them as absent."""
        import asyncio

        proj, rid = quote(project, safe=""), quote(repo_id, safe="")
        sem = asyncio.Semaphore(concurrency)
        out: dict[str, str] = {}

        async with self._client() as client:
            async def fetch(path: str) -> None:
                async with sem:
                    try:
                        resp = await client.get(
                            f"/{proj}/_apis/git/repositories/{rid}/items",
                            params={
                                "api-version": API_VERSION,
                                "path": path,
                                "includeContent": "true",
                                "$format": "json",
                                "versionDescriptor.version": branch,
                                "versionDescriptor.versionType": "branch",
                            },
                        )
                        resp.raise_for_status()
                        content = resp.json().get("content")
                        if content is not None:
                            out[path] = content[:max_chars]
                    except (httpx.HTTPError, ValueError):
                        pass  # unreadable file ≠ failed search

            await asyncio.gather(*(fetch(p) for p in paths))
        return out

    # -- code changes (branch + PR — the coding agent's write path) ---------------

    async def push_branch_with_edits(
        self,
        project: str,
        repo_id: str,
        base_branch: str,
        new_branch: str,
        message: str,
        edits: list[dict[str, str]],  # [{path, content}] — full-file replacements
    ) -> dict[str, Any]:
        """Create `new_branch` off `base_branch` with one commit containing the
        edits (adds or full-file updates), via the Git pushes API. Never touches
        the base branch — the change ships as a PR a human merges."""
        proj, rid = quote(project, safe=""), quote(repo_id, safe="")
        refs = await self._get(
            f"/{proj}/_apis/git/repositories/{rid}/refs",
            params={"filter": f"heads/{base_branch}"},
        )
        matches = [r for r in refs.get("value", []) if r["name"] == f"refs/heads/{base_branch}"]
        if not matches:
            raise ValueError(f"base branch '{base_branch}' not found")
        base_sha = matches[0]["objectId"]

        changes = []
        for e in edits:
            path = e["path"]
            # changeType must match reality: edit for existing files, add for new
            try:
                await self._get(
                    f"/{proj}/_apis/git/repositories/{rid}/items",
                    params={
                        "path": path,
                        "versionDescriptor.version": base_branch,
                        "versionDescriptor.versionType": "branch",
                    },
                )
                change_type = "edit"
            except httpx.HTTPStatusError as ex:
                if ex.response.status_code != 404:
                    raise
                change_type = "add"
            changes.append({
                "changeType": change_type,
                "item": {"path": path},
                "newContent": {"content": e["content"], "contentType": "rawtext"},
            })

        return await self._post(
            f"/{proj}/_apis/git/repositories/{rid}/pushes",
            {
                "refUpdates": [{"name": f"refs/heads/{new_branch}", "oldObjectId": base_sha}],
                "commits": [{"comment": message, "changes": changes}],
            },
        )

    async def create_pull_request(
        self, project: str, repo_id: str, source_branch: str, target_branch: str,
        title: str, description: str = "",
    ) -> dict[str, Any]:
        proj, rid = quote(project, safe=""), quote(repo_id, safe="")
        pr = await self._post(
            f"/{proj}/_apis/git/repositories/{rid}/pullrequests",
            {
                "sourceRefName": f"refs/heads/{source_branch}",
                "targetRefName": f"refs/heads/{target_branch}",
                "title": title,
                "description": description,
            },
        )
        return {"id": pr.get("pullRequestId"), "title": pr.get("title"), "status": pr.get("status")}

    # -- search -----------------------------------------------------------------

    async def search_pull_requests(self, project: str, query: str, top: int = 10) -> list[dict[str, Any]]:
        """Substring search over recent PRs (active + completed). ADO's search
        service doesn't cover PRs, and the org's PR volume is list-then-filter
        scale — the result rows are the same shape the PR tab renders, so the
        UI can deep-link into the existing drawer."""
        import asyncio

        active, completed = await asyncio.gather(
            self.list_pull_requests(project, status="active", top=50),
            self.list_pull_requests(project, status="completed", top=25),
        )
        q = query.lower()
        seen: set[int] = set()
        out = []
        for pr in [*active, *completed]:
            if pr["id"] in seen:
                continue
            hay = " ".join(
                str(pr.get(k) or "")
                for k in ("title", "sourceRef", "targetRef", "createdBy", "repository")
            ).lower()
            if f"!{pr['id']}" == q or str(pr["id"]) == q or q in hay:
                seen.add(pr["id"])
                out.append(pr)
                if len(out) >= top:
                    break
        return out

    def _almsearch_root(self) -> str:
        return self.org_url.replace("https://dev.azure.com", "https://almsearch.dev.azure.com")

    async def search_work_items(self, project: str, query: str, top: int = 20) -> list[dict[str, Any]]:
        """Work-item search via the ADO Search service (built into ADO Services),
        falling back to WIQL CONTAINS when the search service is unreachable."""
        try:
            return await self._search_work_items_alm(project, query, top)
        except httpx.HTTPError:
            return await self._search_work_items_wiql(project, query, top)

    async def _search_work_items_alm(self, project: str, query: str, top: int) -> list[dict[str, Any]]:
        proj = quote(project, safe="")
        async with httpx.AsyncClient(
            base_url=self._almsearch_root(),
            headers={"Authorization": _auth_header(self.pat), "Accept": "application/json"},
            timeout=15.0,
        ) as client:
            resp = await client.post(
                f"/{proj}/_apis/search/workitemsearchresults",
                params={"api-version": API_VERSION},
                json={"searchText": query, "$top": top},
            )
            resp.raise_for_status()
            data = resp.json()
        out = []
        for r in data.get("results", []):
            f = r.get("fields", {})
            # highlight hits: prefer a non-title field so the snippet adds context
            snippet = None
            for h in r.get("hits", []):
                if h.get("fieldReferenceName") != "system.title" and h.get("highlights"):
                    snippet = h["highlights"][0]
                    break
            if snippet is None:
                for h in r.get("hits", []):
                    if h.get("highlights"):
                        snippet = h["highlights"][0]
                        break
            out.append(
                {
                    "id": int(f.get("system.id", 0)),
                    "title": f.get("system.title", ""),
                    "type": f.get("system.workitemtype", ""),
                    "state": f.get("system.state", ""),
                    "assignedTo": f.get("system.assignedto") or None,
                    "snippet": (snippet or "").replace("<highlighthit>", "").replace(
                        "</highlighthit>", ""
                    ) or None,
                }
            )
        return out

    async def _search_work_items_wiql(self, project: str, query: str, top: int) -> list[dict[str, Any]]:
        proj = quote(project, safe="")
        q = query.replace("'", "''")
        wiql = (
            "SELECT [System.Id] FROM WorkItems WHERE "
            f"([System.Title] CONTAINS '{q}' OR [System.Description] CONTAINS WORDS '{q}') "
            "ORDER BY [System.ChangedDate] DESC"
        )
        data = await self._post(f"/{proj}/_apis/wit/wiql", {"query": wiql}, params={"$top": top})
        ids = [w["id"] for w in data.get("workItems", [])][:top]
        if not ids:
            return []
        fields = "System.Id,System.Title,System.WorkItemType,System.State,System.AssignedTo"
        batch = await self._get(
            "/_apis/wit/workitems",
            params={"ids": ",".join(str(i) for i in ids), "fields": fields},
        )
        return [
            {
                "id": w["id"],
                "title": w.get("fields", {}).get("System.Title", ""),
                "type": w.get("fields", {}).get("System.WorkItemType", ""),
                "state": w.get("fields", {}).get("System.State", ""),
                "assignedTo": _user(w.get("fields", {}).get("System.AssignedTo")),
                "snippet": None,
            }
            for w in batch.get("value", [])
        ]

    # -- pull request review ------------------------------------------------------

    async def get_pull_request(self, project: str, repo_id: str, pr_id: int) -> dict[str, Any]:
        proj, rid = quote(project, safe=""), quote(repo_id, safe="")
        pr = await self._get(f"/{proj}/_apis/git/repositories/{rid}/pullRequests/{pr_id}")
        return {
            "id": pr.get("pullRequestId"),
            "title": pr.get("title"),
            "status": pr.get("status"),
            "sourceRef": (pr.get("sourceRefName") or "").replace("refs/heads/", ""),
            "targetRef": (pr.get("targetRefName") or "").replace("refs/heads/", ""),
            "sourceCommit": (pr.get("lastMergeSourceCommit") or {}).get("commitId"),
            "targetCommit": (pr.get("lastMergeTargetCommit") or {}).get("commitId"),
        }

    async def pr_files(self, project: str, repo_id: str, pr_id: int) -> dict[str, Any]:
        """Changed files in the PR's latest iteration, plus the iteration's own
        source/target commits (kept together so diffs always match this list)."""
        proj, rid = quote(project, safe=""), quote(repo_id, safe="")
        base = f"/{proj}/_apis/git/repositories/{rid}/pullRequests/{pr_id}"
        iterations = (await self._get(f"{base}/iterations")).get("value", [])
        if not iterations:
            return {"iteration": None, "sourceCommit": None, "targetCommit": None, "files": []}
        latest = max(iterations, key=lambda i: i.get("id") or 0)
        changes = await self._get(f"{base}/iterations/{latest['id']}/changes")
        files = []
        for e in changes.get("changeEntries", []):
            item = e.get("item") or {}
            if item.get("gitObjectType") == "tree":
                continue
            files.append(
                {
                    "path": item.get("path") or e.get("originalPath"),
                    "originalPath": e.get("originalPath"),
                    "changeType": e.get("changeType"),
                }
            )
        return {
            "iteration": latest.get("id"),
            "sourceCommit": (latest.get("sourceRefCommit") or {}).get("commitId"),
            "targetCommit": (latest.get("targetRefCommit") or {}).get("commitId"),
            "files": files,
        }

    async def _file_side(self, project: str, repo_id: str, path: str, commit: str | None) -> dict[str, Any] | None:
        """One side of a diff, or None when the file doesn't exist there (add/delete)."""
        if not commit:
            return None
        try:
            return await self.get_file(project, repo_id, path, version=commit, version_type="commit")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    async def pr_file_diff(self, project: str, repo_id: str, pr_id: int, path: str) -> dict[str, Any]:
        info = await self.pr_files(project, repo_id, pr_id)
        entry = next((f for f in info["files"] if f["path"] == path), None)
        old_path = (entry or {}).get("originalPath") or path
        old = await self._file_side(project, repo_id, old_path, info["targetCommit"])
        new = await self._file_side(project, repo_id, path, info["sourceCommit"])
        meta = {"path": path, "changeType": (entry or {}).get("changeType")}
        if (old and old["binary"]) or (new and new["binary"]):
            return {**meta, "binary": True, "diff": "", "addedLines": 0, "removedLines": 0}
        if (old and old["truncated"]) or (new and new["truncated"]):
            return {**meta, "binary": False, "tooLarge": True, "diff": "", "addedLines": 0, "removedLines": 0}
        return {
            **meta,
            "binary": False,
            **unified_diff(old["content"] if old else None, new["content"] if new else None, path),
        }

    async def list_pr_threads(self, project: str, repo_id: str, pr_id: int) -> list[dict[str, Any]]:
        """Human comment threads (system events and deleted comments filtered out)."""
        proj, rid = quote(project, safe=""), quote(repo_id, safe="")
        data = await self._get(f"/{proj}/_apis/git/repositories/{rid}/pullRequests/{pr_id}/threads")
        out = []
        for t in data.get("value", []):
            if t.get("isDeleted"):
                continue
            comments = [
                {
                    "id": c.get("id"),
                    "author": _user(c.get("author")),
                    "content": c.get("content") or "",
                    "publishedDate": c.get("publishedDate"),
                }
                for c in t.get("comments", [])
                if c.get("commentType") == "text" and not c.get("isDeleted")
            ]
            if not comments:
                continue
            ctx = t.get("threadContext") or {}
            out.append(
                {
                    "id": t.get("id"),
                    "status": t.get("status"),
                    "filePath": ctx.get("filePath"),
                    "line": (ctx.get("rightFileStart") or {}).get("line"),
                    "comments": comments,
                }
            )
        return out

    # -- writes ---------------------------------------------------------------

    @staticmethod
    def _patch_ops(fields: dict[str, Any]) -> list[dict[str, Any]]:
        """JSON-Patch ops for a field dict; a None value clears the field (e.g. unassign)."""
        return [
            {"op": "remove", "path": f"/fields/{k}"}
            if v is None
            else {"op": "add", "path": f"/fields/{k}", "value": v}
            for k, v in fields.items()
        ]

    async def create_work_item(
        self, project: str, wi_type: str, fields: dict[str, Any]
    ) -> dict[str, Any]:
        """POST a new work item via JSON Patch. The type is a URL segment prefixed
        with a literal '$' (e.g. /wit/workitems/$Task)."""
        proj = quote(project, safe="")
        type_seg = quote(wi_type, safe="")
        data = await self._send(
            "POST",
            f"/{proj}/_apis/wit/workitems/${type_seg}",
            body=self._patch_ops(fields),
            content_type="application/json-patch+json",
        )
        f = data.get("fields", {})
        return {"id": data.get("id"), "title": f.get("System.Title"), "state": f.get("System.State")}

    async def update_work_item(self, work_item_id: int, fields: dict[str, Any]) -> dict[str, Any]:
        """PATCH work item fields via JSON Patch (e.g. {'System.State': 'Active'})."""
        return await self._send(
            "PATCH",
            f"/_apis/wit/workitems/{work_item_id}",
            body=self._patch_ops(fields),
            content_type="application/json-patch+json",
        )

    async def add_work_item_comment(self, project: str, work_item_id: int, text: str) -> dict[str, Any]:
        proj = quote(project, safe="")
        return await self._send(
            "POST",
            f"/{proj}/_apis/wit/workItems/{work_item_id}/comments",
            body={"text": text},
            params={"api-version": "7.1-preview.3"},
        )

    async def set_pr_vote(
        self, project: str, repo_id: str, pr_id: int, reviewer_id: str, vote: int
    ) -> dict[str, Any]:
        """vote: 10 approve, 5 approve w/ suggestions, 0 reset, -5 waiting, -10 reject."""
        proj, rid = quote(project, safe=""), quote(repo_id, safe="")
        return await self._send(
            "PUT",
            f"/{proj}/_apis/git/repositories/{rid}/pullRequests/{pr_id}/reviewers/{reviewer_id}",
            body={"vote": vote},
        )

    async def create_pr_thread(
        self,
        project: str,
        repo_id: str,
        pr_id: int,
        comment: str,
        file_path: str | None = None,
        line: int | None = None,
    ) -> dict[str, Any]:
        """Post a comment thread on a PR — general, or anchored to a file+line
        (line numbers refer to the right/new side of the diff)."""
        proj, rid = quote(project, safe=""), quote(repo_id, safe="")
        body: dict[str, Any] = {
            "comments": [{"parentCommentId": 0, "content": comment, "commentType": 1}],
            "status": "active",
        }
        if file_path:
            fp = file_path if file_path.startswith("/") else f"/{file_path}"
            anchor = {"line": int(line or 1), "offset": 1}
            body["threadContext"] = {"filePath": fp, "rightFileStart": anchor, "rightFileEnd": anchor}
        data = await self._send(
            "POST",
            f"/{proj}/_apis/git/repositories/{rid}/pullRequests/{pr_id}/threads",
            body=body,
        )
        return {"id": data.get("id"), "status": data.get("status")}

    async def set_pr_status(self, project: str, repo_id: str, pr_id: int, status: str) -> dict[str, Any]:
        """status: 'abandoned' or 'active' (reactivate)."""
        proj, rid = quote(project, safe=""), quote(repo_id, safe="")
        return await self._send(
            "PATCH",
            f"/{proj}/_apis/git/repositories/{rid}/pullRequests/{pr_id}",
            body={"status": status},
        )

    async def list_commits(self, project: str, repo_id: str, top: int = 25) -> list[dict[str, Any]]:
        proj = quote(project, safe="")
        rid = quote(repo_id, safe="")
        data = await self._get(
            f"/{proj}/_apis/git/repositories/{rid}/commits",
            params={"searchCriteria.$top": top},
        )
        out = []
        for c in data.get("value", []):
            author = c.get("author") or {}
            out.append(
                {
                    "commitId": c.get("commitId"),
                    "shortId": (c.get("commitId") or "")[:8],
                    "comment": c.get("comment"),
                    "author": author.get("name"),
                    "date": author.get("date"),
                }
            )
        return out
