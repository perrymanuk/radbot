import type { ReactNode } from "react";

export type AIconName =
  | "sparkle" | "cpu" | "server" | "list" | "chart" | "compass"
  | "mail" | "calendar" | "jira" | "play" | "music" | "home"
  | "cart" | "video" | "clap" | "folder" | "db" | "vec" | "nomad"
  | "speaker" | "mic" | "bell" | "clock" | "link" | "alert"
  | "git" | "anchor" | "shield" | "bridge" | "stack" | "key"
  | "code" | "search" | "chev" | "chev-d" | "plus" | "close"
  | "check" | "copy" | "ext" | "refresh" | "play-t" | "pause"
  | "edit" | "trash" | "eye";

interface AIconProps {
  name: AIconName;
  size?: number;
}

// 16x16 viewBox, consistent stroke. Ported from admin-shell.jsx handoff.
export function AIcon({ name, size = 14 }: AIconProps) {
  const p = {
    stroke: "currentColor",
    strokeWidth: 1.4,
    fill: "none",
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
  };
  const svg = (paths: ReactNode) => (
    <svg width={size} height={size} viewBox="0 0 16 16" aria-hidden>
      {paths}
    </svg>
  );
  switch (name) {
    case "sparkle":
      return svg(<path {...p} d="M8 2v4M8 10v4M2 8h4M10 8h4M4 4l2 2M10 10l2 2M12 4l-2 2M4 12l2-2" />);
    case "cpu":
      return svg(
        <>
          <rect {...p} x="3.5" y="3.5" width="9" height="9" rx="1" />
          <rect {...p} x="6" y="6" width="4" height="4" />
          <path {...p} d="M6 1.5V3.5M10 1.5V3.5M6 12.5V14.5M10 12.5V14.5M1.5 6H3.5M1.5 10H3.5M12.5 6H14.5M12.5 10H14.5" />
        </>,
      );
    case "server":
      return svg(
        <>
          <rect {...p} x="2.5" y="3" width="11" height="4" rx="0.5" />
          <rect {...p} x="2.5" y="9" width="11" height="4" rx="0.5" />
          <circle cx="4.5" cy="5" r="0.7" fill="currentColor" />
          <circle cx="4.5" cy="11" r="0.7" fill="currentColor" />
        </>,
      );
    case "list":
      return svg(
        <>
          <path {...p} d="M4 4h9M4 8h9M4 12h9" />
          <circle cx="2.5" cy="4" r="0.5" fill="currentColor" />
          <circle cx="2.5" cy="8" r="0.5" fill="currentColor" />
          <circle cx="2.5" cy="12" r="0.5" fill="currentColor" />
        </>,
      );
    case "chart":
      return svg(<path {...p} d="M2.5 13.5h11M4 12V8M7 12V4M10 12V9M13 12V6" />);
    case "compass":
      return svg(
        <>
          <circle {...p} cx="8" cy="8" r="5.5" />
          <path {...p} d="M6 10l1.5-3.5L10 6l-1.5 3.5z" fill="currentColor" />
        </>,
      );
    case "mail":
      return svg(
        <>
          <rect {...p} x="2" y="3.5" width="12" height="9" rx="1" />
          <path {...p} d="M2.5 4.5l5.5 4 5.5-4" />
        </>,
      );
    case "calendar":
      return svg(
        <>
          <rect {...p} x="2.5" y="3.5" width="11" height="10" rx="1" />
          <path {...p} d="M2.5 6.5h11M5 2v3M11 2v3" />
        </>,
      );
    case "jira":
      return svg(<path {...p} d="M4 4h3l5 5v3L7 7H4zM4 7v3h3" />);
    case "play":
      return svg(
        <>
          <circle {...p} cx="8" cy="8" r="5.5" />
          <path d="M6.8 5.8v4.4L10.4 8z" fill="currentColor" />
        </>,
      );
    case "music":
      return svg(
        <>
          <path {...p} d="M6 11V3.5l6-1.5v8" />
          <circle {...p} cx="5" cy="11" r="1.5" />
          <circle {...p} cx="11" cy="10" r="1.5" />
        </>,
      );
    case "home":
      return svg(<path {...p} d="M2.5 8L8 3l5.5 5M4 7.5V13h8V7.5" />);
    case "cart":
      return svg(
        <>
          <path {...p} d="M2 3h2l1.5 7.5h7L14 5.5H5" />
          <circle {...p} cx="6.5" cy="13" r="0.8" />
          <circle {...p} cx="11.5" cy="13" r="0.8" />
        </>,
      );
    case "video":
      return svg(
        <>
          <rect {...p} x="2" y="4.5" width="8" height="7" rx="1" />
          <path {...p} d="M10 7.5L14 5.5v5l-4-2z" />
        </>,
      );
    case "clap":
      return svg(
        <>
          <rect {...p} x="2" y="6.5" width="12" height="7" rx="0.8" />
          <path {...p} d="M2.4 6.5l1.5-2.5 2 1.5-1 2M5.4 6.5l1.2-2.5 2 1.5-1 2M8.6 6.5l1.2-2.5 2 1.5-1 2" />
        </>,
      );
    case "folder":
      return svg(
        <path
          {...p}
          d="M2 4.5A1.5 1.5 0 013.5 3h3l1.5 1.5h5A1.5 1.5 0 0114.5 6v6A1.5 1.5 0 0113 13.5H3A1.5 1.5 0 011.5 12V4.5z"
        />,
      );
    case "db":
      return svg(
        <>
          <ellipse {...p} cx="8" cy="4" rx="5" ry="1.8" />
          <path {...p} d="M3 4v8c0 1 2.2 1.8 5 1.8s5-.8 5-1.8V4M3 8c0 1 2.2 1.8 5 1.8s5-.8 5-1.8" />
        </>,
      );
    case "vec":
      return svg(<path {...p} d="M8 3v10M8 3l-3 3M8 3l3 3M8 13l-3-3M8 13l3-3M3 8h10" />);
    case "nomad":
      return svg(<path {...p} d="M8 2l5 3v6l-5 3-5-3V5l5-3zM8 2v5M8 13V8M3 5l5 3M13 5l-5 3" />);
    case "speaker":
      return svg(
        <path
          {...p}
          d="M3 6v4h2l3 2.5v-9L5 6H3M10 5.5a3.5 3.5 0 010 5M12 3.5a6 6 0 010 9"
        />,
      );
    case "mic":
      return svg(
        <>
          <rect {...p} x="6" y="2" width="4" height="7" rx="2" />
          <path {...p} d="M3.5 8a4.5 4.5 0 009 0M8 12.5V14" />
        </>,
      );
    case "bell":
      return svg(<path {...p} d="M4 11h8l-1-1.5V7a3 3 0 00-6 0v2.5L4 11zM6.5 12.5a1.5 1.5 0 003 0" />);
    case "clock":
      return svg(
        <>
          <circle {...p} cx="8" cy="8" r="5.5" />
          <path {...p} d="M8 5v3l2 1.5" />
        </>,
      );
    case "link":
      return svg(
        <path
          {...p}
          d="M7 10a3 3 0 004 0l2-2a3 3 0 10-4-4l-1 1M9 6a3 3 0 00-4 0L3 8a3 3 0 104 4l1-1"
        />,
      );
    case "alert":
      return svg(
        <>
          <path {...p} d="M8 2l6.5 11.5h-13z" />
          <path {...p} d="M8 6v3M8 11v0.5" />
        </>,
      );
    case "git":
      return svg(
        <>
          <circle {...p} cx="4" cy="4" r="1.5" />
          <circle {...p} cx="4" cy="12" r="1.5" />
          <circle {...p} cx="12" cy="8" r="1.5" />
          <path {...p} d="M4 5.5v5M10.5 8H8a3 3 0 01-3-3" />
        </>,
      );
    case "anchor":
      return svg(
        <>
          <circle {...p} cx="8" cy="3.5" r="1.2" />
          <path {...p} d="M8 4.7V13M5 8h6M4 10.5a4 4 0 004 3 4 4 0 004-3" />
        </>,
      );
    case "shield":
      return svg(
        <path {...p} d="M8 2l5 2v4.5c0 3-2.5 4.7-5 5.5-2.5-.8-5-2.5-5-5.5V4l5-2z" />,
      );
    case "bridge":
      return svg(<path {...p} d="M2.5 6.5h11M3 6.5v5M13 6.5v5M5.5 6.5L3 10M10.5 6.5L13 10M8 6.5v5" />);
    case "stack":
      return svg(<path {...p} d="M8 2.5l5.5 2.5L8 7.5 2.5 5 8 2.5zM2.5 8L8 10.5 13.5 8M2.5 11L8 13.5 13.5 11" />);
    case "key":
      return svg(
        <>
          <circle {...p} cx="5" cy="8" r="2.5" />
          <path {...p} d="M7.5 8h6l-1 1.5M11 8v2" />
        </>,
      );
    case "code":
      return svg(<path {...p} d="M5 4L2 8l3 4M11 4l3 4-3 4M9.5 3.5l-3 9" />);
    case "search":
      return svg(
        <>
          <circle {...p} cx="7" cy="7" r="4.5" />
          <path {...p} d="M10.5 10.5l3 3" />
        </>,
      );
    case "chev":
      return svg(<path {...p} d="M6 4l4 4-4 4" />);
    case "chev-d":
      return svg(<path {...p} d="M4 6l4 4 4-4" />);
    case "plus":
      return svg(<path {...p} d="M8 3v10M3 8h10" />);
    case "close":
      return svg(<path {...p} strokeWidth={1.6} d="M4 4l8 8M12 4l-8 8" />);
    case "check":
      return svg(<path {...p} strokeWidth={1.8} d="M3 8.5l3 3 7-7" />);
    case "copy":
      return svg(
        <>
          <rect {...p} x="5" y="5" width="8.5" height="8.5" rx="1" />
          <path {...p} d="M10 5V3a1 1 0 00-1-1H3a1 1 0 00-1 1v6a1 1 0 001 1h2" />
        </>,
      );
    case "ext":
      return svg(<path {...p} d="M7 3H3v10h10V9M9 3h4v4M13 3l-6 6" />);
    case "refresh":
      return svg(
        <path {...p} d="M13 3v4h-4M3 13v-4h4M13 7A5 5 0 003.5 6M3 9a5 5 0 009.5 1" />,
      );
    case "play-t":
      return svg(<path d="M4 3v10l9-5z" fill="currentColor" />);
    case "pause":
      return svg(
        <>
          <rect x="4" y="3" width="3" height="10" fill="currentColor" />
          <rect x="9" y="3" width="3" height="10" fill="currentColor" />
        </>,
      );
    case "edit":
      return svg(<path {...p} d="M11 3l2 2-7 7H4v-2l7-7zM9.5 4.5l2 2" />);
    case "trash":
      return svg(<path {...p} d="M3 5h10M6 5V3h4v2M4.5 5l1 8h5l1-8" />);
    case "eye":
      return svg(
        <>
          <path {...p} d="M1.5 8s2.5-5 6.5-5 6.5 5 6.5 5-2.5 5-6.5 5-6.5-5-6.5-5z" />
          <circle {...p} cx="8" cy="8" r="2" />
        </>,
      );
    default:
      return svg(<circle {...p} cx="8" cy="8" r="4" />);
  }
}
