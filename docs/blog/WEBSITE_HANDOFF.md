# Website handoff — publishing the "Building ADO Companion" blog series

> **Audience: the Claude session that maintains jpaladini/jpaladini** (Astro + Tailwind,
> deployed on Vercel at jpaladini.vercel.app). This brief is self-contained: the
> publishing instructions are up top; a **project-context appendix** (architecture,
> delivery pipeline, auth model, per-post fact sheet) follows so you can write accurate
> index blurbs, meta descriptions, and series copy without guessing. Written 2026-07-02,
> expanded 2026-07-03 and 2026-07-04 (Part 8 added; all drafts flipped to prod).

## The task

Add a **blog section** to the site (it currently has none — About / Experience /
Platforms & Tools / What I Do / Education / Contact) and publish an **eight-part** technical
series called **"Building ADO Companion."** The posts are finished and written in
Jason's voice; your job is presentation and plumbing, **not rewriting**.
**As of 2026-07-04 Jason has flipped every post to `draft: false` — all eight are
cleared for production publish** (screenshot slots stay hidden at render; see below). Format-level
edits only. You MAY write short *around-the-posts* copy (index blurbs, a one-paragraph
series intro, meta descriptions) — ground every claim in the appendix below, and keep
Jason's direct, results-oriented voice.

## The source files (8 posts + 2 images)

| File | Series part | Status |
|---|---|---|
| `part-1-building-ado-companion.md` | 1 — the app + CI/CD pipeline | complete, `draft: false` |
| `part-2-analytics-odata.md` | 2 — choosing OData for analytics | complete, `draft: false` |
| `part-3-ai-copilot-agent.md` | 3 — the AI copilot agent | complete, `draft: false` |
| `part-4-mlflow-tracing-agent.md` | 4 — MLflow tracing | complete, `draft: false` |
| `part-5-ai-in-the-flow-of-work.md` | 5 — in-place AI (enrichment, PR review, Explain) | complete, `draft: false` |
| `part-6-flow-metrics-business-days.md` | 6 — Reports tab, business days, Observable Plot | complete, `draft: false` |
| `part-7-search-artifacts-eval-harness.md` | 7 — global search, artifacts/exports, model eval harness | complete, `draft: false` |
| `part-8-pipeline-logs-board-as-todo.md` | 8 — CI logs in-app + the backlog moves onto the board | complete, `draft: false` |
| `analytics-overview-light.png`, `analytics-overview-30d.png` | used by Part 2 | final |

Canonical source of truth: the `docs/blog/` folder of Jason's `ado` repo (branch `dev`).
If you only have the attached copies, treat those as current.

## Frontmatter → content collection

Every post carries this schema — map it to an Astro content collection:

```yaml
title: string
description: string
date: YYYY-MM-DD
tags: [string]
author: Jason Paladini
draft: false         # Jason flipped all posts to false on 2026-07-04 — cleared to publish
series: "Building ADO Companion"   # parts 2-4 only; add to part 1 for consistency
part: number
```

Suggested `src/content/config.ts` schema: title, description, `date` as `z.coerce.date()`,
tags as string array, `draft: z.boolean().default(true)`, optional `series` + `part`.
**Respect the `draft` flag** — exclude any `draft: true` post from production builds.
All eight posts currently ship `draft: false` (Jason's call, 2026-07-04); if a future
post arrives `draft: true`, keep it out of prod until he flips it.

## Special content blocks — handle these deliberately

The posts contain three kinds of non-prose blocks:

1. **Mermaid diagrams** (` ```mermaid ` fences). These must render as diagrams, not code.
   Prefer build-time rendering to SVG (e.g. `rehype-mermaid` with Playwright, or
   pre-render and inline) over shipping mermaid.js to the client — fits the site's
   minimalist, fast posture. Diagram color hints in the source assume a light background;
   if the site has a dark mode, verify contrast or restyle to the site's palette.

2. **`> 🖼️ Diagram reading (for image generation):` blockquotes.** Each follows a mermaid
   block and is a prose description of the same diagram. Two sanctioned uses — pick one:
   - Use it as **accessible alt text / figcaption source** for the rendered diagram
     (preferred), collapsing or visually hiding the verbose text; or
   - Feed it to an image generator to produce styled static diagrams matching the site,
     then use those instead of mermaid.
   Do **not** publish these blockquotes as visible body text.

3. **`> 📸 Screenshot slot:` blockquotes.** Placeholders for screenshots Jason hasn't
   taken yet. Hide them in production rendering (comment out or strip at build), but
   keep them in the source so Jason knows what to capture. Part 2's two PNGs are real
   and already referenced inline — ship those with correct relative paths.

## Design constraints

- Match the site's existing motif: **minimalist black-and-white, typography-first,
  no decoration for its own sake.** The posts are long-form technical writing — prioritize
  a comfortable measure (~70ch), clear heading hierarchy, and readable tables.
- Code blocks: Astro's built-in Shiki is fine; pick one light theme consistent with the
  B&W aesthetic (and a dark twin if the site has dark mode).
- Series navigation: each post should show "Part N of Building ADO Companion" and link
  to its siblings (prev/next at minimum). Publication order = part order.
- Tags can render as plain text chips; don't build tag pages unless it's trivial.
- A simple `/blog` index (title, description, date, part badge) is enough. No pagination
  needed for eight posts.

## What NOT to do

- Don't rewrite, summarize, or "improve" the prose — voice is intentional.
- Don't flip a `draft` flag in either direction yourself — the flags arrive as Jason
  set them (all `false` as of 2026-07-04).
- Don't strip the screenshot-slot markers from the *source* — only from rendered output.
- Don't add an external comment system, analytics, or tracking as part of this task.

## Definition of done

1. `/blog` index lists the series; each post renders with diagrams as images/SVG,
   syntax-highlighted code, hidden screenshot slots, working Part 2 images.
2. All eight posts are live in production (they ship `draft: false`); the draft-exclusion
   machinery still exists for future posts.
3. Screenshot slots stay hidden in rendered output; as Jason captures each set, the
   images land in the source and replace their slots — no draft round-trip needed.

---

# Appendix: project context (so your copy is accurate, not guessed)

Everything below is factual as of 2026-07-04. Use it for blurbs, meta descriptions,
alt text, and a series intro. Do not contradict it; when a post and this appendix seem
to disagree, the post wins (it's the reviewed artifact).

## A1. What ADO Companion is

A single **Databricks App** (one process: FastAPI backend serving a built React/Vite/
TypeScript/Tailwind SPA) that is a full companion to **Azure DevOps**: live read/write
over work items, pull requests, pipelines, and code; near-live delivery analytics; and
a Databricks-native AI layer that *acts* (with human approval) rather than just answers.
Built almost entirely by an AI coding agent pair-programming with Jason, shipping every
change through a human-gated CI/CD loop.

## A2. The components

| Component | What it does |
|---|---|
| **Operational plane** (`ado/client.py`) | Live Azure DevOps REST: work-item CRUD, PR files/diffs/threads, builds, repos/branches/file content. No ADO data stored. |
| **Analytical plane** (`ado/analytics.py`) | ADO **Analytics OData** with server-side `$apply` aggregation: flow metrics, daily snapshots for cumulative flow, cycle/lead dates. |
| **Batch plane** (ingest job → Delta) | Scheduled job lands ADO history into Unity Catalog Delta tables; **Genie** (NL-to-SQL) answers historical questions over them. |
| **AI copilot** (`copilot.py`) | Tool-calling agent on a Databricks **Foundation Model APIs** serving endpoint. Read tools execute; **write tools become proposals** a human applies through the normal REST routes (identical audit trail). Guessed-ID proposals are verified server-side and rejected. |
| **In-place AI** (`ai.py`) | Single-shot forced function calls behind buttons: work-item drafting/improving, PR review (line anchors validated against real diff hunks), plain-language file Explain. |
| **Observability** | Every model call traced to an **MLflow experiment** (spans per turn/tool/verification, token usage); every mutation and AI action in a Delta **audit log**. |
| **Reports tab** | Flow metrics drawn with **Observable Plot** (ISC-licensed d3 successor, lazy-loaded, themed on CSS design tokens): cycle-time scatter with p50/p85 bands, cumulative flow, aging WIP, workload. **All durations are 5-day-workweek business days** computed in the backend. |
| **App-state store** | Delta tables for per-user settings + audit; graceful degradation when grants are missing. |

Design invariants worth echoing in copy: two data planes (live vs batch, never
conflated); all environment-specific config in per-workspace secrets so promotion is a
pure code merge; graceful degradation everywhere; **no AI write ever executes without a
human click**.

## A3. The CI/CD method (the series' recurring backbone — Part 1 covers it in depth)

```
AI agent pushes → GitHub repo (feature branch)
  → GitHub Action mirrors the branch → Azure DevOps Repos (same name)
    → agent opens a PR into the protected `dev` branch via the ADO REST API
      → JASON merges (the human gate — the agent cannot merge, by design)
        → merge triggers Azure Pipelines: npm build → databricks bundle validate/deploy → bundle run
          → the live Databricks App updates (~3.5 min end to end)
```

Talking points that make this interesting: the *AI that writes the code cannot ship the
code* — a human merge gates every deploy; dev/stg/prod are protected branches deploying
to separate workspaces whose only difference is secret values; the built frontend is
committed, so deploys need no Node toolchain.

## A4. The auth model (describe the scheme — NEVER any token values)

- **Azure DevOps access**: a Personal Access Token (scopes: Work Items R/W, Code R/W,
  Build R+Execute) stored as a **Databricks secret** (scope `ado`), injected into the
  app at runtime via the Asset Bundle's secret resources. Never in code, files, or git.
- **CI/CD to Databricks**: the pipeline authenticates as a **service principal** (OAuth
  M2M via pipeline variables) — no human token in CI; the SP owns the deployed
  resources (a Part-1 war story covers the human-vs-SP ownership collision).
- **The app itself** runs as its own app service principal; Databricks Apps injects
  user identity via forwarded headers (that's how per-user settings + audit attribution
  work with zero login code).
- **GitHub→ADO mirror**: a second, Code-R/W-only PAT lives exclusively in GitHub Actions
  secrets (two war stories: PAT-in-URL auth, and sanitizing pasted whitespace).
- **Runtime AI config** (model endpoint name, Genie space id, MLflow experiment id) are
  also secrets — read at runtime, so swapping models needs no redeploy.
- **For you, the website agent**: you need none of these. Your input is markdown files.
  If any draft ever appears to contain a real token, STOP and tell Jason — that's a
  leak, not content. (House rule: tokens are rotated before anything goes public.)

## A5. Per-post fact sheet (for blurbs and meta descriptions)

| Part | One-line blurb material | Key concrete facts |
|---|---|---|
| 1 | Rebuilt a mobile ADO client as a web app on Databricks Apps, with the GitHub→ADO→Databricks pipeline | React+FastAPI single process; Asset Bundles; five debugging war stories; branch-based promotion |
| 2 | Three ways to get delivery analytics out of ADO; chose server-side OData `$apply` | WIQL vs OData vs Delta ingest; daily `WorkItemSnapshot` trends; "sequence them, don't pick one" |
| 3 | Gave the app a tool-calling agent that acts — safely | Propose-then-apply pattern; agent-as-client-of-the-app; FMAPI endpoint as config; Genie demoted to a tool |
| 4 | You can't operate an agent you can't see: MLflow Tracing from day one | Span tree = turn/llm/tool/verify; never-fatal telemetry rule; two ten-second production diagnoses |
| 5 | Chat proved the AI; buttons shipped it | Form-as-approval-UX; PR review line anchors validated server-side (hallucinated anchors structurally impossible); Explain for non-engineers |
| 6 | Flow metrics for a data team, in business days, drawn with d3's successor | p50/p85 over averages; aging-WIP-vs-p85; retired a custom Power BI semantic model with a 20-line tested function; Observable Plot (ISC, offline, token-themed); Databricks metric views verified as the future report-builder's semantic layer |
| 7 | The search box was a div; and an eval harness so the model swap isn't vibes | global search over 3 planes (BFF grep — org lacks the Code Search extension, API fails silently with infoCode 6); session history persists proposal outcomes; fpdf2 over weasyprint (deploy failure mode); mlflow.genai.evaluate + judges, deterministic scorers as hard gate, one pinned judge |
| 8 | CI logs land in-app (for humans AND the agent), and the backlog moves onto the board | build timeline + step logs in the Pipelines tab, failed step auto-opens; log truncation keeps the TAIL (tracebacks live at the end); `get_build_logs` copilot tool = the CI-feedback primitive; roadmap seeded as Epics/Issues (dogfooding); auto-close design: PR links work item + `transitionWorkItems` on human merge — outcome without granting the AI a close power |

## A6. Glossary (terms the posts assume)

- **ADO** — Azure DevOps (work items, repos, pipelines). **OData Analytics** — its
  aggregation API (`$apply=groupby/aggregate/filter`).
- **Databricks Apps** — hosts web apps inside a Databricks workspace. **Asset Bundle** —
  declarative deploy config (`databricks.yml`). **Unity Catalog / Delta** — governed
  tables. **Genie** — Databricks NL-to-SQL over curated tables. **FMAPI** — Foundation
  Model APIs, serving endpoints for LLMs (model name is config, e.g. a Llama or
  Databricks-hosted Claude endpoint). **Metric views** — YAML measures/dimensions in
  Unity Catalog, queried with `MEASURE()`.
- **BFF** — backend-for-frontend (the FastAPI layer). **Propose-then-apply** — the
  series' central safety pattern: AI writes become human-approved proposals that flow
  through the same routes and audit trail as manual actions.
- **Cycle time p50/p85** — median / 85th-percentile completion durations; **CFD** —
  cumulative flow diagram; **aging WIP** — open items' age plotted against those bands;
  **business days** — Mon–Fri only, the series' insisted-on unit.
