// ADO stores rich-text fields (description, comments) as HTML; we edit and
// render them as plain text. Shared by WorkItems and the AI copilot.

export function htmlToText(html: string): string {
  if (!html) return "";
  const withBreaks = html.replace(/<br\s*\/?>/gi, "\n").replace(/<\/(p|div|li)>/gi, "\n");
  const el = document.createElement("div");
  el.innerHTML = withBreaks;
  return (el.textContent ?? "").replace(/\n{3,}/g, "\n\n").trim();
}

export function textToHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .split("\n")
    .join("<br>");
}
