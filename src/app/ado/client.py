"""Thin async client for the Azure DevOps REST API.

This is the *operational* data plane — it talks to the live ADO API. No ADO data
is persisted locally. Auth is PAT-based (Basic auth with an empty username), which
mirrors the original mobile app; corporate will swap this for Entra OAuth.
"""
import base64
import json as jsonlib
from typing import Any
from urllib.parse import quote

import httpx

from app.config import settings

API_VERSION = "7.1"


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
        data = await self._get("/_apis/connectionData")
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
            out.append(
                {
                    "id": pr.get("pullRequestId"),
                    "title": pr.get("title"),
                    "status": pr.get("status"),
                    "isDraft": pr.get("isDraft", False),
                    "createdBy": _user(pr.get("createdBy")),
                    "creationDate": pr.get("creationDate"),
                    "repository": (pr.get("repository") or {}).get("name"),
                    "repositoryId": (pr.get("repository") or {}).get("id"),
                    "sourceRef": (pr.get("sourceRefName") or "").replace("refs/heads/", ""),
                    "targetRef": (pr.get("targetRefName") or "").replace("refs/heads/", ""),
                }
            )
        return out

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
