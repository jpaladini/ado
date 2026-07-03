# Onboarding a repo + coding-agent end-to-end test

> Every step below was executed live on 2026-07-03 (repo: `streamlit-chess`,
> GitHub → ADO project `home`). Replay it verbatim for a corporate test —
> substitute org/project/repo and use the corporate PAT. `$APAT` = an ADO PAT
> with Code R/W. Nothing here needs classifier-blocked actions except where
> marked HUMAN.

## Part 1 — Move a repo into ADO

### 1. Create the empty target repo

```bash
curl -s -u ":$APAT" -X POST \
  "https://dev.azure.com/<org>/<project>/_apis/git/repositories?api-version=7.1" \
  -H "Content-Type: application/json" -d '{"name":"<repo-name>"}'
# → note the repo "id" (GUID) from the response — you need it in step 4
```

### 2. Import the source (one-time — see CORPORATE_BOOTSTRAP Phase 1)

Public Git source (no auth):

```bash
curl -s -u ":$APAT" -X POST \
  "https://dev.azure.com/<org>/<project>/_apis/git/repositories/<repo-name>/importRequests?api-version=7.1" \
  -H "Content-Type: application/json" \
  -d '{"parameters":{"gitSource":{"url":"https://github.com/<owner>/<repo>.git"}}}'
```

Poll until `status: completed` (takes seconds for small repos):

```bash
curl -s -u ":$APAT" "https://dev.azure.com/<org>/<project>/_apis/git/repositories/<repo-name>/importRequests/<id>?api-version=7.1"
```

**Corporate variants:** a *private* source needs a service connection
(`serviceEndpointId` in the import parameters — HUMAN sets that up), or skip
the importer entirely: `git clone --mirror` the source inside the network and
`git push --mirror` to the new ADO repo. Either way it's a ONE-TIME copy;
nothing syncs afterwards (see docs/CICD.md "Two development models").

### 3. Sanity-check the contents

```bash
curl -s -u ":$APAT" "https://dev.azure.com/<org>/<project>/_apis/git/repositories/<repo-name>/items?recursionLevel=Full&api-version=7.1"
```

### 4. Fix the default branch (bit us BOTH times — check every import)

The import preserves the source's default branch, which for us was a stale
`claude/...` working branch. The app's Code tab and the code-search index
follow `dev`-then-default, so a bad default degrades both.

```bash
# create main (or your trunk name) at the imported head:
SHA=<objectId of the current default ref>
curl -s -u ":$APAT" -X POST \
  "https://dev.azure.com/<org>/<project>/_apis/git/repositories/<repo-name>/refs?api-version=7.1" \
  -H "Content-Type: application/json" \
  -d "[{\"name\":\"refs/heads/main\",\"oldObjectId\":\"0000000000000000000000000000000000000000\",\"newObjectId\":\"$SHA\"}]"

# set it as default — GOTCHA: PATCH by repo NAME returns 400; use the repo GUID:
curl -s -u ":$APAT" -X PATCH \
  "https://dev.azure.com/<org>/<project>/_apis/git/repositories/<repo-GUID>?api-version=7.1" \
  -H "Content-Type: application/json" -d '{"defaultBranch":"refs/heads/main"}'
```

### 5. Verify in ADO Companion

- **Code tab**: the repo appears in the repositories pane; files open in the
  viewer (live ADO reads — no refresh needed).
- **Header search**: code results include the new repo after the search
  index's TTL rebuild (≤5 minutes, or immediately on the first search after
  an app restart). The index reads `dev` if the repo has one, else the
  default branch — which is why step 4 matters.

## Part 2 — Coding-agent end-to-end test

Prereq: the coding-agent build (`search_code` + `create_code_pr`, PR #30 in
dev) is merged and deployed; `copilot_endpoint` is set.

Run these in the copilot panel, in order — each step works even if the next
fails, which is also the recommended live-demo order:

1. **Search (zero risk):** header search for a term unique to the new repo
   → code hits with line numbers → click into the viewer.
2. **Comprehension (low risk):** ask the panel *"explain how <repo> does X"*
   — exercises `search_code` + `get_file` cross-repo, read-only.
3. **Small scripted change (the live write):** e.g. *"add a <section> to the
   README of <repo>, base it on main"* → verify the proposal card shows the
   right repo/branch/file → **Apply** → confirm the PR exists in ADO and the
   audit log has a `code.pr` row.
4. **The big change (do it BEFORE the demo, show the result):** a real
   refactor (for streamlit-chess: rewrite `db.py` from local DuckDB — which
   is ephemeral on Databricks Apps — to warehouse/Lakebase storage). Run it
   in advance, keep the PR open, present it as "it made this one too."

Cleanup after a test run: abandon the PR
(`PATCH .../pullrequests/<id>?api-version=7.1  {"status":"abandoned"}`) and
delete the `copilot/...` branch (update its ref to the zero objectId).

## Known limits to state honestly (roadshow + corporate review)

- **Onboarded repos have no CI** until someone adds a pipeline — agent PRs
  against them are review-gated only. Add a minimal validate pipeline per
  repo, or say the human review is the gate (it always is anyway).
- The agent writes **whole files, blind** (≤8 files, ≤150k chars each per
  proposal). Small precise asks succeed; big refactors deserve a stronger
  model (`copilot_endpoint` swap) and a pre-run, not a live stage run.
- Nothing the agent does can touch a protected branch — Apply creates a
  `copilot/<slug>-<hex>` branch and a PR; merging is human, always.
