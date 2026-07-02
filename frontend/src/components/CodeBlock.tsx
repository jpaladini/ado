import { useEffect, useState } from "react";
import { langForPath, loadHljs } from "../lib/highlight";

function escapeHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

/** Syntax-highlighted file view with a line-number gutter. Renders plain
 * escaped text until the (lazily loaded) highlighter is ready. */
export default function CodeBlock({ content, path }: { content: string; path: string }) {
  const [html, setHtml] = useState<string>(() => escapeHtml(content));

  useEffect(() => {
    let alive = true;
    setHtml(escapeHtml(content));
    const language = langForPath(path);
    if (!language) return;
    loadHljs().then((hljs) => {
      if (!alive) return;
      try {
        setHtml(hljs.highlight(content, { language }).value);
      } catch {
        /* keep the escaped fallback */
      }
    });
    return () => {
      alive = false;
    };
  }, [content, path]);

  const lineCount = content === "" ? 1 : content.split("\n").length;
  const gutter = Array.from({ length: lineCount }, (_, i) => i + 1).join("\n");

  return (
    <div className="grid grid-cols-[auto_1fr] overflow-x-auto font-mono text-[12px] leading-[19px]">
      <pre className="m-0 select-none border-r border-line pr-[12px] text-right text-faint">{gutter}</pre>
      <pre className="m-0 overflow-x-auto pl-[14px]" dangerouslySetInnerHTML={{ __html: html }} />
    </div>
  );
}
