import { useEffect } from "react";
import { IconChevron, IconX } from "./icons";

/** Right-side slide-over: backdrop click + Escape to close. */
export function Drawer({
  title,
  onClose,
  children,
  width = "w-[460px]",
}: {
  title: React.ReactNode;
  onClose: () => void;
  children: React.ReactNode;
  width?: string;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-40">
      <div className="absolute inset-0 bg-black/35" onClick={onClose} />
      <div
        className={`absolute right-0 top-0 flex h-full ${width} max-w-full flex-col border-l border-border bg-surface shadow-[-12px_0_32px_rgba(0,0,0,.18)]`}
      >
        <div className="flex items-center justify-between border-b border-line px-[20px] py-[14px]">
          <div className="text-[13px] font-semibold text-text">{title}</div>
          <button onClick={onClose} className="text-faint hover:text-text-3" title="Close">
            <IconX size={15} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-[20px]">{children}</div>
      </div>
    </div>
  );
}

export function Field({
  label,
  action,
  children,
}: {
  label: string;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <label className="mb-[14px] block">
      <div className="mb-[5px] flex items-center justify-between">
        <span className="text-[10.5px] font-semibold uppercase tracking-[0.5px] text-faint">{label}</span>
        {action}
      </div>
      {children}
    </label>
  );
}

export const INPUT =
  "w-full rounded-[7px] border border-border bg-bg px-[11px] py-[7px] text-[12.5px] text-text outline-none placeholder:text-faint focus:border-faint";

export function Select({
  value,
  onChange,
  options,
}: {
  value: string;
  onChange: (v: string) => void;
  options: string[];
}) {
  return (
    <span className="relative block">
      <select value={value} onChange={(e) => onChange(e.target.value)} className={`${INPUT} appearance-none pr-[26px]`}>
        {options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
      <span className="pointer-events-none absolute right-[9px] top-1/2 -translate-y-1/2 text-faint">
        <IconChevron size={10} />
      </span>
    </span>
  );
}
