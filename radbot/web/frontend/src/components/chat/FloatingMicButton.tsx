import { cn } from "@/lib/utils";

type STTState = "idle" | "recording" | "processing";

interface Props {
  state: STTState;
  toggle: () => void;
}

export default function FloatingMicButton({ state, toggle }: Props) {
  return (
    <button
      onClick={toggle}
      disabled={state === "processing"}
      className={cn(
        "fixed bottom-20 right-4 z-40 w-14 h-14 rounded-full",
        "flex items-center justify-center transition-all",
        "shadow-lg active:scale-95",
        state === "idle" && "bg-accent-blue text-white hover:bg-accent-blue/80",
        state === "recording" &&
          "bg-terminal-red text-white animate-pulse shadow-[0_0_20px_rgba(255,0,0,0.4)]",
        state === "processing" &&
          "bg-terminal-amber text-bg-primary cursor-wait",
      )}
      aria-label={
        state === "recording"
          ? "Stop recording"
          : state === "processing"
            ? "Processing..."
            : "Start recording"
      }
    >
      {state === "recording" ? (
        /* Stop icon */
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 24 24"
          fill="currentColor"
          className="w-6 h-6"
        >
          <rect x="6" y="6" width="12" height="12" rx="2" />
        </svg>
      ) : state === "processing" ? (
        /* Spinner */
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          className="w-6 h-6 animate-spin"
        >
          <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
        </svg>
      ) : (
        /* Mic icon */
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 24 24"
          fill="currentColor"
          className="w-7 h-7"
        >
          <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z" />
          <path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z" />
        </svg>
      )}
    </button>
  );
}
