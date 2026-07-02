// Lazily-loaded highlight.js core + common languages. The dynamic imports keep
// the highlighter out of the main bundle — Vite splits it into its own chunk
// that only loads when a file is first viewed.
import type { HLJSApi, LanguageFn } from "highlight.js";

let cached: Promise<HLJSApi> | null = null;

export function loadHljs(): Promise<HLJSApi> {
  cached ??= (async () => {
    const { default: hljs } = await import("highlight.js/lib/core");
    const langs: [string, () => Promise<{ default: LanguageFn }>][] = [
      ["typescript", () => import("highlight.js/lib/languages/typescript")],
      ["javascript", () => import("highlight.js/lib/languages/javascript")],
      ["python", () => import("highlight.js/lib/languages/python")],
      ["json", () => import("highlight.js/lib/languages/json")],
      ["yaml", () => import("highlight.js/lib/languages/yaml")],
      ["xml", () => import("highlight.js/lib/languages/xml")],
      ["css", () => import("highlight.js/lib/languages/css")],
      ["bash", () => import("highlight.js/lib/languages/bash")],
      ["markdown", () => import("highlight.js/lib/languages/markdown")],
      ["sql", () => import("highlight.js/lib/languages/sql")],
    ];
    for (const [name, load] of langs) hljs.registerLanguage(name, (await load()).default);
    return hljs;
  })();
  return cached;
}

const EXT_TO_LANG: Record<string, string> = {
  ts: "typescript",
  tsx: "typescript",
  js: "javascript",
  jsx: "javascript",
  mjs: "javascript",
  py: "python",
  json: "json",
  yml: "yaml",
  yaml: "yaml",
  html: "xml",
  xml: "xml",
  svg: "xml",
  css: "css",
  sh: "bash",
  bash: "bash",
  md: "markdown",
  sql: "sql",
};

export function langForPath(path: string): string | null {
  const ext = path.split(".").pop()?.toLowerCase() ?? "";
  return EXT_TO_LANG[ext] ?? null;
}
