// Inline line icons (stroke currentColor, 1.5) — paths lifted from the prototype.
import type { SVGProps } from "react";

type P = SVGProps<SVGSVGElement> & { size?: number };
const base = (size: number, p: P) => ({
  width: p.size ?? size,
  height: p.size ?? size,
  viewBox: "0 0 16 16",
  fill: "none" as const,
  ...p,
});

export const IconOverview = (p: P) => (
  <svg {...base(16, p)}>
    <rect x="1.5" y="1.5" width="5.5" height="5.5" rx="1.5" stroke="currentColor" strokeWidth="1.5" />
    <rect x="9" y="1.5" width="5.5" height="5.5" rx="1.5" stroke="currentColor" strokeWidth="1.5" />
    <rect x="1.5" y="9" width="5.5" height="5.5" rx="1.5" stroke="currentColor" strokeWidth="1.5" />
    <rect x="9" y="9" width="5.5" height="5.5" rx="1.5" stroke="currentColor" strokeWidth="1.5" />
  </svg>
);

export const IconWork = (p: P) => (
  <svg {...base(16, p)}>
    <rect x="2" y="2.5" width="12" height="11" rx="2" stroke="currentColor" strokeWidth="1.5" />
    <path d="M5 6.5l1.3 1.3L9 5.2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    <path d="M5 10.5h6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
  </svg>
);

export const IconPrs = (p: P) => (
  <svg {...base(16, p)}>
    <circle cx="4" cy="4" r="2.2" stroke="currentColor" strokeWidth="1.5" />
    <circle cx="4" cy="12" r="2.2" stroke="currentColor" strokeWidth="1.5" />
    <circle cx="12" cy="12" r="2.2" stroke="currentColor" strokeWidth="1.5" />
    <path d="M4 6.2v3.6M6 4h3a3 3 0 013 3v2.8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
  </svg>
);

export const IconPipe = (p: P) => (
  <svg {...base(16, p)}>
    <circle cx="3" cy="8" r="2" stroke="currentColor" strokeWidth="1.5" />
    <circle cx="13" cy="4" r="2" stroke="currentColor" strokeWidth="1.5" />
    <circle cx="13" cy="12" r="2" stroke="currentColor" strokeWidth="1.5" />
    <path d="M5 8h3l3-4M8 8l3 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
  </svg>
);

export const IconCode = (p: P) => (
  <svg {...base(16, p)}>
    <path d="M6 4L2.5 8 6 12M10 4l3.5 4L10 12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

export const IconAnalytics = (p: P) => (
  <svg {...base(16, p)}>
    <path d="M2 14V2M2 14h12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <rect x="4.5" y="8" width="2.4" height="4" fill="currentColor" />
    <rect x="8" y="5" width="2.4" height="7" fill="currentColor" />
    <rect x="11.5" y="9.5" width="2.4" height="2.5" fill="currentColor" />
  </svg>
);

export const IconActivity = (p: P) => (
  <svg {...base(16, p)}>
    <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.5" />
    <path d="M8 4.5V8l2.5 1.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

export const IconSearch = (p: P) => (
  <svg {...base(16, p)}>
    <circle cx="7" cy="7" r="4.5" stroke="currentColor" strokeWidth="1.5" />
    <path d="M10.5 10.5L14 14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
  </svg>
);

export const IconSun = (p: P) => (
  <svg {...base(16, p)}>
    <circle cx="8" cy="8" r="3.2" stroke="currentColor" strokeWidth="1.5" />
    <path
      d="M8 1v1.6M8 13.4V15M15 8h-1.6M2.6 8H1M12.95 3.05l-1.13 1.13M4.18 11.82l-1.13 1.13M12.95 12.95l-1.13-1.13M4.18 4.18L3.05 3.05"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
    />
  </svg>
);

export const IconMoon = (p: P) => (
  <svg {...base(16, p)}>
    <path d="M13.5 9.2A5.5 5.5 0 016.8 2.5 5.5 5.5 0 1013.5 9.2z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
  </svg>
);

export const IconChevron = (p: P) => (
  <svg {...base(12, { viewBox: "0 0 12 12", ...p })}>
    <path d="M3 5l3 3 3-3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

export const IconComment = (p: P) => (
  <svg {...base(16, p)}>
    <path d="M2 4a2 2 0 012-2h8a2 2 0 012 2v5a2 2 0 01-2 2H6l-3 3V4z" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
  </svg>
);

export const IconX = (p: P) => (
  <svg {...base(16, p)}>
    <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
  </svg>
);

export const IconCheck = (p: P) => (
  <svg {...base(16, p)}>
    <path d="M3 8.5l3 3 7-7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

export const Spark = (p: P) => (
  <svg {...base(16, p)}>
    <path d="M8 1 L10 6 L15 6 L11 9.5 L12.5 15 L8 11.5 L3.5 15 L5 9.5 L1 6 L6 6 Z" fill="currentColor" />
  </svg>
);
