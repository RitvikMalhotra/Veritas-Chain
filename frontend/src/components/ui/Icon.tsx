import type { SVGProps } from "react";

// One drawn set, 24px grid, 1.7px strokes. Decorative by default; pass a title to give an icon a name.
const PATHS = {
  mark: (
    <>
      <rect x="2.5" y="7.5" width="11" height="9" rx="4.5" fill="none" stroke="currentColor" strokeWidth="1.9" />
      <rect x="10.5" y="7.5" width="11" height="9" rx="4.5" fill="none" stroke="currentColor" strokeWidth="1.9" />
    </>
  ),
  shieldOk: (
    <>
      <path d="M12 2.8 4.5 5.6v5.9c0 4.7 3.1 8.4 7.5 9.7 4.4-1.3 7.5-5 7.5-9.7V5.6L12 2.8Z" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
      <path d="m8.6 12.1 2.4 2.4 4.6-4.8" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </>
  ),
  shieldBad: (
    <>
      <path d="M12 2.8 4.5 5.6v5.9c0 4.7 3.1 8.4 7.5 9.7 4.4-1.3 7.5-5 7.5-9.7V5.6L12 2.8Z" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
      <path d="M12 7.6v5.2" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" />
      <circle cx="12" cy="15.9" r="1.1" fill="currentColor" />
    </>
  ),
  shieldIdle: (
    <path d="M12 2.8 4.5 5.6v5.9c0 4.7 3.1 8.4 7.5 9.7 4.4-1.3 7.5-5 7.5-9.7V5.6L12 2.8Z" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" strokeDasharray="2.6 2.2" />
  ),
  warn: (
    <>
      <path d="M10.3 3.9 2.6 17.3A2 2 0 0 0 4.3 20.3h15.4a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
      <path d="M12 9.2v4.6" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" />
      <circle cx="12" cy="16.9" r="1.05" fill="currentColor" />
    </>
  ),
  anchor: (
    <>
      <circle cx="12" cy="5.2" r="2.2" fill="none" stroke="currentColor" strokeWidth="1.7" />
      <path d="M12 7.4v13.2M7.5 11h9M4.5 13.5c.6 4 3.6 7.1 7.5 7.1s6.9-3.1 7.5-7.1" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </>
  ),
  flask: (
    <>
      <path d="M9.5 3h5M10.2 3v5.6L4.8 18.2A1.9 1.9 0 0 0 6.5 21h11a1.9 1.9 0 0 0 1.7-2.8L13.8 8.6V3" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M7.6 14.5h8.8" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </>
  ),
  chevron: <path d="m6.5 9.5 5.5 5.5 5.5-5.5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />,
  arrow: <path d="M5 12h13M13 6.5l5.5 5.5-5.5 5.5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />,
  fit: (
    <>
      <path d="M4 9V5.5A1.5 1.5 0 0 1 5.5 4H9M15 4h3.5A1.5 1.5 0 0 1 20 5.5V9M20 15v3.5a1.5 1.5 0 0 1-1.5 1.5H15M9 20H5.5A1.5 1.5 0 0 1 4 18.5V15" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
      <circle cx="12" cy="12" r="2.4" fill="none" stroke="currentColor" strokeWidth="1.7" />
    </>
  ),
  reset: (
    <>
      <path d="M4.5 12a7.5 7.5 0 1 0 2.2-5.3" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
      <path d="M4.5 3.8v4.4h4.4" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </>
  ),
  plus: <path d="M12 5.5v13M5.5 12h13" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />,
  minus: <path d="M5.5 12h13" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />,
  info: (
    <>
      <circle cx="12" cy="12" r="8.5" fill="none" stroke="currentColor" strokeWidth="1.7" />
      <path d="M12 11v5.2" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      <circle cx="12" cy="7.9" r="1.05" fill="currentColor" />
    </>
  ),
  close: <path d="m6.5 6.5 11 11m0-11-11 11" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />,
  check: <path d="m5.5 12.5 4.2 4.2 8.8-9.4" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" />,
  copy: (
    <>
      <rect x="8.5" y="8.5" width="11" height="11" rx="2" fill="none" stroke="currentColor" strokeWidth="1.7" />
      <path d="M15.5 5.5v-.5a1.5 1.5 0 0 0-1.5-1.5H5A1.5 1.5 0 0 0 3.5 5v9A1.5 1.5 0 0 0 5 15.5h.5" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </>
  ),
  legend: (
    <>
      <circle cx="6" cy="7" r="2" fill="currentColor" />
      <rect x="4" y="15" width="4" height="4" rx="0.5" fill="currentColor" />
      <path d="M11 7h9M11 17h9" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </>
  ),
} as const;

export type IconName = keyof typeof PATHS;

export function Icon({ name, title, ...props }: { name: IconName; title?: string } & SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden={title ? undefined : true} role={title ? "img" : undefined} focusable="false" {...props}>
      {title ? <title>{title}</title> : null}
      {PATHS[name]}
    </svg>
  );
}
