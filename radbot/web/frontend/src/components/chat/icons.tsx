import type { ReactNode } from "react";

// ─────────────────────────────────────────────────────────
// ICON SET
//
// Monochrome, stroke-based SVG icons used throughout the
// chat/tasks/tweaks UI. All 14×14 by default, currentColor.
//
// Usage:  <Icon.check />  <Icon.plus />  etc.
// ─────────────────────────────────────────────────────────

type IconProps = { size?: number; className?: string };

function mk(path: ReactNode, viewBox = "0 0 14 14") {
  return function IconShell({ size = 14, className }: IconProps) {
    return (
      <svg
        width={size}
        height={size}
        viewBox={viewBox}
        fill="none"
        stroke="currentColor"
        strokeWidth={1.4}
        strokeLinecap="round"
        strokeLinejoin="round"
        className={className}
        aria-hidden
      >
        {path}
      </svg>
    );
  };
}

export const Icon = {
  check:    mk(<path d="M2 7.5l3 3 7-7" />),
  plus:     mk(<path d="M7 2v10M2 7h10" />),
  circle:   mk(<circle cx="7" cy="7" r="4.5" />),
  half:     mk(<><circle cx="7" cy="7" r="4.5" /><path d="M7 2.5a4.5 4.5 0 0 1 0 9z" fill="currentColor" stroke="none" /></>),
  sparkle:  mk(<path d="M7 1.5l1.2 3.3 3.3 1.2-3.3 1.2L7 10.5l-1.2-3.3L2.5 6l3.3-1.2z" />),
  download: mk(<path d="M7 2v7m-3-3l3 3 3-3M2.5 11.5h9" />),
  mic:      mk(<><rect x="5.25" y="1.75" width="3.5" height="7" rx="1.75" /><path d="M3 7.5a4 4 0 0 0 8 0M7 11v1.5" /></>),
  play:     mk(<path d="M4 3l7 4-7 4z" />),
  bolt:     mk(<path d="M8 1.5L3.5 8h3L6 12.5 10.5 6h-3z" />),
  calendar: mk(<><rect x="2" y="3" width="10" height="9" rx="1.5" /><path d="M5 1.5v3M9 1.5v3M2 6h10" /></>),
  home:     mk(<path d="M2 7L7 2l5 5v5H2z M5.5 12V8.5h3V12" />),
  bell:     mk(<path d="M3.5 9.5h7a3.5 3.5 0 0 1-7 0zM4.5 9.5V6a2.5 2.5 0 0 1 5 0v3.5M6 11.5a1 1 0 0 0 2 0" />),
  brain:    mk(<path d="M5 2.5a2 2 0 0 0-2 2 2 2 0 0 0-1 1.8c0 .7.4 1.3 1 1.6v1.1a2 2 0 0 0 2 2h1V2.5zm4 0a2 2 0 0 1 2 2 2 2 0 0 1 1 1.8c0 .7-.4 1.3-1 1.6v1.1a2 2 0 0 1-2 2H8V2.5z" />),
  film:     mk(<><rect x="2" y="2.5" width="10" height="9" rx="1" /><path d="M5 2.5v9M9 2.5v9M2 5.5h3M9 5.5h3M2 8.5h3M9 8.5h3" /></>),
  lightbulb: mk(<path d="M5 9.5V11h4V9.5M7 1.5a3.5 3.5 0 0 0-2 6.1V9.5h4V7.6A3.5 3.5 0 0 0 7 1.5z" />),
} as const;

export type IconName = keyof typeof Icon;
