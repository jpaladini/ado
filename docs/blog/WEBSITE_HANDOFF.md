# Website handoff — publishing the "Building ADO Companion" blog series

> **Audience: the Claude session that maintains jpaladini/jpaladini** (Astro + Tailwind,
> deployed on Vercel at jpaladini.vercel.app). This brief is self-contained: everything
> you need is in the attached/accompanying files. Written 2026-07-02.

## The task

Add a **blog section** to the site (it currently has none — About / Experience /
Platforms & Tools / What I Do / Education / Contact) and publish a four-part technical
series called **"Building ADO Companion."** The posts are finished drafts written in
Jason's voice; your job is presentation and plumbing, **not rewriting**. Format-level
edits only.

## The source files (4 posts + 2 images)

| File | Series part | Status |
|---|---|---|
| `part-1-building-ado-companion.md` | 1 — the app + CI/CD pipeline | draft, complete |
| `part-2-analytics-odata.md` | 2 — choosing OData for analytics | draft, complete |
| `part-3-ai-copilot-agent.md` | 3 — the AI copilot agent | draft, complete |
| `part-4-mlflow-tracing-agent.md` | 4 — MLflow tracing | draft, complete |
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
draft: true          # KEEP true until Jason explicitly flips it
series: "Building ADO Companion"   # parts 2-4 only; add to part 1 for consistency
part: number
```

Suggested `src/content/config.ts` schema: title, description, `date` as `z.coerce.date()`,
tags as string array, `draft: z.boolean().default(true)`, optional `series` + `part`.
**Respect `draft: true`** — exclude drafts from production builds; Jason flips them when
he's reviewed the rendered result.

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
  needed for four posts.

## What NOT to do

- Don't rewrite, summarize, or "improve" the prose — voice is intentional.
- Don't publish with `draft: true` still set, and don't flip drafts yourself.
- Don't strip the screenshot-slot markers from the *source* — only from rendered output.
- Don't add an external comment system, analytics, or tracking as part of this task.

## Definition of done

1. `/blog` index lists the series; each post renders with diagrams as images/SVG,
   syntax-highlighted code, hidden screenshot slots, working Part 2 images.
2. Drafts are excluded from production; Jason can preview them (e.g. in dev mode or a
   preview deploy) to review before flipping `draft`.
3. Jason reviews rendered previews → captures the screenshots marked in the slots →
   flips `draft: false` per post → publish.
