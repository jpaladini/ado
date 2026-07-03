"""BFF code search: an in-memory text index over the project's repos.

Why this exists: the org has no Code Search extension (`ms.vss-code-search`),
so `almsearch …/codesearchresults` returns nothing. Rather than requiring a
marketplace install (a human, org-level action) the BFF greps the repos itself:
it lists every file on each repo's default branch, bulk-fetches the text
contents, and holds them in memory with a TTL. Small-org scale by design —
capped files per repo, capped bytes per file, skip-lists for generated and
binary content. If the extension is installed later, swapping this module for
the search service is a contained change (the route contract stays the same).

Degrades gracefully: index build failures mark the plane unavailable with a
reason; work-item search is independent and unaffected.
"""
import asyncio
import logging
import time
from typing import Any

from app.ado.client import ADOClient

log = logging.getLogger(__name__)

TTL_SECS = 300.0
MAX_REPOS = 10
MAX_FILES_PER_REPO = 500
MAX_FILE_CHARS = 100_000
MAX_RESULT_FILES = 20
MAX_MATCHES_PER_FILE = 3
SNIPPET_CHARS = 240

# Directories that are dependency/build output — never source anyone searches for.
_SKIP_DIRS = {"node_modules", ".git", "dist", "build", "out", "vendor", "__pycache__"}
# Extensions that are binary or minified — no useful text matches.
_SKIP_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".pdf", ".zip", ".gz", ".jar",
    ".woff", ".woff2", ".ttf", ".eot", ".exe", ".dll", ".so", ".pyc", ".class",
    ".min.js", ".min.css", ".map", ".lock",
}
# Machine-written files with high term density and zero search value.
_SKIP_NAMES = {"package-lock.json", "pnpm-lock.yaml", "npm-shrinkwrap.json"}


def _indexable(path: str) -> bool:
    parts = path.lstrip("/").split("/")
    if any(p in _SKIP_DIRS for p in parts[:-1]):
        return False
    name = parts[-1].lower()
    if name in _SKIP_NAMES:
        return False
    return not any(name.endswith(ext) for ext in _SKIP_EXTS)


def _looks_minified(text: str) -> bool:
    """Bundled/minified output (e.g. committed Vite builds) — all noise, no signal."""
    head = text[:20_000]
    lines = head.splitlines() or [""]
    return max(len(l) for l in lines) > 2_000 or len(head) / len(lines) > 300


class CodeSearch:
    def __init__(self) -> None:
        self._cache: dict[str, dict[str, Any]] = {}  # project → {built_at, repos: [...]}
        self._locks: dict[str, asyncio.Lock] = {}

    async def _index(self, project: str, client: ADOClient) -> dict[str, Any]:
        entry = self._cache.get(project)
        if entry and time.monotonic() - entry["built_at"] < TTL_SECS:
            return entry
        lock = self._locks.setdefault(project, asyncio.Lock())
        async with lock:
            entry = self._cache.get(project)
            if entry and time.monotonic() - entry["built_at"] < TTL_SECS:
                return entry

            repos_out: list[dict[str, Any]] = []
            skipped_files = 0
            for repo in (await client.list_repos(project))[:MAX_REPOS]:
                branch = repo.get("defaultBranch")
                if not branch:
                    continue  # empty repo
                # Prefer the deploy trunk over a stale default branch: this org's
                # repos default to an old feature branch, but `dev` is the code.
                if branch != "dev":
                    try:
                        names = {b["name"] for b in await client.list_branches(project, repo["id"])}
                        if "dev" in names:
                            branch = "dev"
                    except Exception:
                        pass  # default branch is still a fine index
                try:
                    paths = await client.list_file_paths(project, repo["id"], branch)
                except Exception as e:
                    log.info("code index: listing %s failed: %s", repo["name"], e)
                    continue
                wanted = [p for p in paths if _indexable(p)]
                skipped_files += len(paths) - len(wanted)
                if len(wanted) > MAX_FILES_PER_REPO:
                    skipped_files += len(wanted) - MAX_FILES_PER_REPO
                    wanted = wanted[:MAX_FILES_PER_REPO]
                contents = await client.get_files_bulk(
                    project, repo["id"], branch, wanted, max_chars=MAX_FILE_CHARS
                )
                minified = [p for p, t in contents.items() if _looks_minified(t)]
                for p in minified:
                    del contents[p]
                skipped_files += len(minified)
                repos_out.append(
                    {
                        "id": repo["id"],
                        "name": repo["name"],
                        "branch": branch,
                        "files": contents,  # path → text
                    }
                )
            entry = {
                "built_at": time.monotonic(),
                "repos": repos_out,
                "indexedFiles": sum(len(r["files"]) for r in repos_out),
                "skippedFiles": skipped_files,
            }
            self._cache[project] = entry
            return entry

    async def search(self, project: str, query: str, client: ADOClient) -> dict[str, Any]:
        try:
            entry = await self._index(project, client)
        except Exception as e:
            log.warning("code index build failed: %s", e)
            return {"available": False, "reason": str(e)[:200], "results": []}

        q = query.lower()
        results: list[dict[str, Any]] = []
        for repo in entry["repos"]:
            for path, text in repo["files"].items():
                name_hit = q in path.lower()
                matches: list[dict[str, Any]] = []
                if q in text.lower():
                    for n, line in enumerate(text.splitlines(), start=1):
                        if q in line.lower():
                            matches.append({"line": n, "text": line.strip()[:SNIPPET_CHARS]})
                            if len(matches) >= MAX_MATCHES_PER_FILE:
                                break
                if not (name_hit or matches):
                    continue
                results.append(
                    {
                        "repo": repo["name"],
                        "repoId": repo["id"],
                        "branch": repo["branch"],
                        "path": path,
                        "nameHit": name_hit,
                        "matches": matches,
                    }
                )
        # filename hits first, then by match count — the cheap relevance that works
        results.sort(key=lambda r: (not r["nameHit"], -len(r["matches"]), r["path"]))
        truncated = len(results) > MAX_RESULT_FILES
        return {
            "available": True,
            "results": results[:MAX_RESULT_FILES],
            "truncated": truncated,
            "indexedFiles": entry["indexedFiles"],
        }


code_search = CodeSearch()
