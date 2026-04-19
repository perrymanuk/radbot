import type { CSSProperties } from "react";

type IconName =
  | "folder"
  | "flag"
  | "check"
  | "circle"
  | "half"
  | "flask"
  | "target"
  | "search"
  | "plus"
  | "chev"
  | "refresh"
  | "archive"
  | "star"
  | "link"
  | "clock"
  | "git"
  | "close";

interface Props {
  name: IconName;
  size?: number;
  style?: CSSProperties;
}

export default function PIcon({ name, size = 14, style }: Props) {
  const stroke = {
    stroke: "currentColor",
    strokeWidth: 1.4,
    fill: "none",
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
  };
  const common = { width: size, height: size, style };
  switch (name) {
    case "folder":
      return (
        <svg {...common} viewBox="0 0 16 16">
          <path
            d="M2 4.5A1.5 1.5 0 013.5 3h3l1.5 1.5h5A1.5 1.5 0 0114.5 6v6A1.5 1.5 0 0113 13.5H3A1.5 1.5 0 011.5 12V4.5z"
            {...stroke}
          />
        </svg>
      );
    case "flag":
      return (
        <svg {...common} viewBox="0 0 16 16">
          <path d="M3 14V2M3 3h9l-2 3 2 3H3" {...stroke} />
        </svg>
      );
    case "check":
      return (
        <svg {...common} viewBox="0 0 16 16">
          <circle cx="8" cy="8" r="5.5" {...stroke} />
          <path d="M5.5 8l2 2 3-4" {...stroke} />
        </svg>
      );
    case "circle":
      return (
        <svg {...common} viewBox="0 0 16 16">
          <circle cx="8" cy="8" r="5.5" {...stroke} />
        </svg>
      );
    case "half":
      return (
        <svg {...common} viewBox="0 0 16 16">
          <circle cx="8" cy="8" r="5.5" {...stroke} />
          <path d="M8 2.5a5.5 5.5 0 010 11z" fill="currentColor" />
        </svg>
      );
    case "flask":
      return (
        <svg {...common} viewBox="0 0 16 16">
          <path
            d="M6 2h4M6.5 2v4L3 12a1 1 0 00.9 1.5h8.2A1 1 0 0013 12L9.5 6V2"
            {...stroke}
          />
        </svg>
      );
    case "target":
      return (
        <svg {...common} viewBox="0 0 16 16">
          <circle cx="8" cy="8" r="5.5" {...stroke} />
          <circle cx="8" cy="8" r="2.5" {...stroke} />
          <circle cx="8" cy="8" r="0.5" fill="currentColor" />
        </svg>
      );
    case "search":
      return (
        <svg {...common} viewBox="0 0 16 16">
          <circle cx="7" cy="7" r="4.5" {...stroke} />
          <path d="M10.5 10.5l3 3" {...stroke} />
        </svg>
      );
    case "plus":
      return (
        <svg {...common} viewBox="0 0 16 16">
          <path d="M8 3v10M3 8h10" {...stroke} />
        </svg>
      );
    case "chev":
      return (
        <svg {...common} viewBox="0 0 16 16">
          <path d="M6 4l4 4-4 4" {...stroke} />
        </svg>
      );
    case "refresh":
      return (
        <svg {...common} viewBox="0 0 16 16">
          <path d="M13 3v4h-4M3 13v-4h4M13 7A5 5 0 003.5 6M3 9a5 5 0 009.5 1" {...stroke} />
        </svg>
      );
    case "archive":
      return (
        <svg {...common} viewBox="0 0 16 16">
          <rect x="2" y="3" width="12" height="3" {...stroke} />
          <path d="M3 6v7h10V6M6 9h4" {...stroke} />
        </svg>
      );
    case "star":
      return (
        <svg {...common} viewBox="0 0 16 16">
          <path
            d="M8 2l1.8 4 4.2.5-3.1 2.8.9 4.2L8 11.5 4.2 13.5l.9-4.2L2 6.5 6.2 6 8 2z"
            {...stroke}
          />
        </svg>
      );
    case "link":
      return (
        <svg {...common} viewBox="0 0 16 16">
          <path
            d="M7 10a3 3 0 004 0l2-2a3 3 0 10-4-4l-1 1M9 6a3 3 0 00-4 0L3 8a3 3 0 104 4l1-1"
            {...stroke}
          />
        </svg>
      );
    case "clock":
      return (
        <svg {...common} viewBox="0 0 16 16">
          <circle cx="8" cy="8" r="5.5" {...stroke} />
          <path d="M8 5v3l2 1.5" {...stroke} />
        </svg>
      );
    case "git":
      return (
        <svg {...common} viewBox="0 0 16 16">
          <circle cx="4" cy="4" r="1.5" {...stroke} />
          <circle cx="4" cy="12" r="1.5" {...stroke} />
          <circle cx="12" cy="8" r="1.5" {...stroke} />
          <path d="M4 5.5v5M10.5 8H8a3 3 0 01-3-3" {...stroke} />
        </svg>
      );
    case "close":
      return (
        <svg {...common} viewBox="0 0 16 16">
          <path d="M4 4l8 8M12 4l-8 8" {...stroke} strokeWidth={1.6} />
        </svg>
      );
    default:
      return null;
  }
}
