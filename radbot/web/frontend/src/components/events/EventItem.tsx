import { cn } from "@/lib/utils";
import { formatTimestamp } from "@/lib/utils";
import type { AgentEvent, EventCategory } from "@/types";

interface Props {
  event: AgentEvent;
  onClick: () => void;
}

const borderColors: Record<string, string> = {
  tool_call: "border-l-accent-blue",
  model_response: "border-l-terminal-amber",
  agent_transfer: "border-l-terminal-amber",
  planner: "border-l-terminal-green",
  system: "border-l-txt-secondary",
  other: "border-l-txt-secondary",
};

export default function EventItem({ event, onClick }: Props) {
  const category = event.category || event.type || "other";

  return (
    <div
      onClick={onClick}
      className={cn(
        "px-2 py-1 mb-0.5 border border-border border-l-[3px] bg-bg-secondary",
        "text-[0.75rem] cursor-pointer transition-all relative overflow-hidden",
        "hover:border-accent-blue hover:bg-bg-tertiary hover:shadow-[0_2px_4px_rgba(0,0,0,0.3)] hover:-translate-y-px",
        borderColors[category] ?? "border-l-txt-secondary",
      )}
    >
      {/* Type badge */}
      <span className="font-bold text-terminal-amber text-[0.7rem] uppercase inline-block mb-0.5">
        {event.type?.replace(/_/g, " ") ?? category}
      </span>

      {/* Timestamp */}
      {event.timestamp && (
        <span className="absolute top-1 right-1.5 text-[0.65rem] text-txt-secondary">
          {formatTimestamp(event.timestamp)}
        </span>
      )}

      {/* Summary */}
      <div className="text-txt-primary text-[0.7rem] break-words leading-tight">
        {event.summary ??
          event.tool_name ??
          event.text?.slice(0, 100) ??
          "—"}
      </div>
    </div>
  );
}
