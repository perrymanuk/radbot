import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

// ─────────────────────────────────────────────────────────
// MOBILE SHELL
//
// Phone-frame wrapper used when the app is viewed on narrow
// screens (or the Tweaks `view=mobile` preview). Mirrors the
// design mock's iPhone bezel: status bar, rounded outer frame,
// home indicator.
//
// Pass the existing chat view as children. The shell sets its
// own height = 100dvh so the inner content can scroll.
// ─────────────────────────────────────────────────────────

interface Props {
  children: ReactNode;
  /** Whether to add the device chrome (false = fullscreen fallback) */
  chrome?: boolean;
}

function StatusBar() {
  const now = new Date();
  const time = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
  return (
    <div className="h-[38px] flex items-center justify-between px-6 bg-bg-primary text-txt-primary font-mono text-[0.7rem] flex-none">
      <span className="font-bold">{time}</span>
      <div className="flex items-center gap-1.5 text-txt-primary">
        {/* signal */}
        <svg width="14" height="10" viewBox="0 0 14 10" aria-hidden>
          <rect x="0"  y="7" width="2" height="3" fill="currentColor" />
          <rect x="4"  y="5" width="2" height="5" fill="currentColor" />
          <rect x="8"  y="3" width="2" height="7" fill="currentColor" />
          <rect x="12" y="1" width="2" height="9" fill="currentColor" />
        </svg>
        {/* wifi */}
        <svg width="12" height="10" viewBox="0 0 12 10" fill="none" stroke="currentColor" strokeWidth="1.2" aria-hidden>
          <path d="M1 4a8 8 0 0 1 10 0M3 6a5 5 0 0 1 6 0M5 8a2 2 0 0 1 2 0" />
        </svg>
        {/* battery */}
        <svg width="22" height="10" viewBox="0 0 22 10" aria-hidden>
          <rect x="0.5" y="0.5" width="19" height="9" rx="2" fill="none" stroke="currentColor" />
          <rect x="2" y="2" width="13" height="6" fill="currentColor" />
          <rect x="20" y="3.5" width="1.5" height="3" fill="currentColor" />
        </svg>
      </div>
    </div>
  );
}

function HomeIndicator() {
  return (
    <div className="h-[18px] flex items-center justify-center bg-bg-primary flex-none">
      <span className="w-[110px] h-[4px] rounded-full bg-txt-primary/80" />
    </div>
  );
}

export default function MobileShell({ children, chrome = true }: Props) {
  if (!chrome) return <div className="h-[100dvh]">{children}</div>;
  return (
    <div
      className={cn(
        "mx-auto my-0 w-full max-w-[420px] h-[100dvh]",
        "bg-bg-primary text-txt-primary",
        "flex flex-col overflow-hidden",
        "sm:my-4 sm:h-[calc(100dvh-2rem)] sm:rounded-[36px] sm:border sm:border-border",
        "sm:shadow-[0_30px_80px_-20px_rgba(0,0,0,0.8)]",
      )}
    >
      <StatusBar />
      <div className="flex-1 min-h-0 flex flex-col overflow-hidden">{children}</div>
      <HomeIndicator />
    </div>
  );
}
