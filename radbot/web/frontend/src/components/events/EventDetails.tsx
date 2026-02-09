import { useState } from "react";
import type { AgentEvent } from "@/types";
import { cn } from "@/lib/utils";

interface Props {
  event: AgentEvent;
}

export default function EventDetails({ event }: Props) {
  const [showRaw, setShowRaw] = useState(false);

  return (
    <div className="flex-1 overflow-y-auto p-2 text-[0.75rem] leading-tight bg-bg-tertiary">
      {/* Type + badge */}
      <div className="mb-2 pb-1 border-b border-accent-blue/10">
        <h4 className="text-[0.75rem] font-normal text-terminal-amber font-mono m-0 mb-0.5">
          Event Type:{" "}
          <TypeBadge category={event.category || "other"} type={event.type} />
        </h4>
        {event.timestamp && (
          <div className="text-[0.65rem] text-txt-secondary text-right -mt-4">
            {new Date(event.timestamp).toLocaleString()}
          </div>
        )}
      </div>

      {/* Summary / Text */}
      {(event.summary || event.text) && (
        <div className="mb-2 pb-1 border-b border-accent-blue/10">
          <h4 className="text-[0.75rem] font-normal text-terminal-amber font-mono mb-0.5">
            {event.type === "tool_call" ? "Tool Call" : "Content"}
          </h4>
          <div className="whitespace-pre-wrap font-mono text-[0.75rem] leading-relaxed bg-bg-secondary p-2 border-l-2 border-accent-blue text-txt-primary">
            {event.text || event.summary}
          </div>
        </div>
      )}

      {/* Tool details */}
      {event.tool_name && (
        <div className="mb-2 pb-1 border-b border-accent-blue/10">
          <h4 className="text-[0.75rem] font-normal text-terminal-amber font-mono mb-0.5">
            Tool
          </h4>
          <div className="text-[0.7rem]">
            <div>
              <strong className="text-terminal-amber mr-1">Name:</strong>
              <span className="text-accent-blue">{event.tool_name}</span>
            </div>
            {event.tool_args && (
              <div className="mt-1">
                <strong className="text-terminal-amber mr-1">Arguments:</strong>
                <pre className="mt-1 ml-4 p-1.5 bg-bg-secondary border border-border border-l-2 border-l-accent-blue text-[0.65rem] max-h-[150px] overflow-auto whitespace-pre-wrap font-mono text-txt-primary">
                  {JSON.stringify(event.tool_args, null, 2)}
                </pre>
              </div>
            )}
            {event.tool_response && (
              <div className="mt-1">
                <strong className="text-terminal-amber mr-1">Response:</strong>
                <pre className="mt-1 ml-4 p-1.5 bg-bg-secondary border border-border border-l-2 border-l-accent-blue text-[0.65rem] max-h-[150px] overflow-auto whitespace-pre-wrap font-mono text-txt-primary">
                  {event.tool_response}
                </pre>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Transfer details */}
      {(event.from_agent || event.to_agent) && (
        <div className="mb-2 pb-1 border-b border-accent-blue/10">
          <h4 className="text-[0.75rem] font-normal text-terminal-amber font-mono mb-0.5">
            Transfer
          </h4>
          <div className="flex flex-col gap-1 mt-1 p-1.5 bg-black/10 rounded-sm">
            {event.from_agent && (
              <div className="text-[0.7rem]">
                <strong className="text-terminal-amber mr-1">From:</strong>
                {event.from_agent}
              </div>
            )}
            {event.to_agent && (
              <div className="text-[0.7rem]">
                <strong className="text-terminal-amber mr-1">To:</strong>
                {event.to_agent}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Planner steps */}
      {event.steps && event.steps.length > 0 && (
        <div className="mb-2 pb-1 border-b border-accent-blue/10">
          <h4 className="text-[0.75rem] font-normal text-terminal-amber font-mono mb-0.5">
            Steps
          </h4>
          <ol className="ml-6 mt-1 pl-4 list-decimal">
            {event.steps.map((step, i) => (
              <li key={i} className="mb-1 text-[0.75rem]">
                {step}
              </li>
            ))}
          </ol>
        </div>
      )}

      {/* Agent name */}
      {event.agent_name && (
        <div className="text-[0.65rem] text-txt-secondary mt-2 border-t border-dashed border-border pt-1">
          Agent: <span className="font-mono opacity-70">{event.agent_name}</span>
        </div>
      )}

      {/* Raw JSON toggle */}
      <div className="mt-2 border-t border-dashed border-border pt-1">
        <div className="flex justify-between items-center mb-1">
          <h4 className="text-[0.75rem] text-terminal-amber font-mono m-0">
            Raw JSON
          </h4>
          <button
            onClick={() => setShowRaw(!showRaw)}
            className="bg-bg-tertiary border border-border text-txt-primary px-1.5 py-0.5 text-[0.65rem] cursor-pointer transition-all hover:bg-accent-blue hover:text-bg-primary"
          >
            {showRaw ? "HIDE" : "SHOW"}
          </button>
        </div>
        {showRaw && (
          <pre className="bg-bg-secondary border border-border border-l-2 border-l-terminal-amber p-2 font-mono text-[0.65rem] text-txt-primary max-h-[300px] overflow-y-auto whitespace-pre-wrap break-words">
            {JSON.stringify(event.raw ?? event, null, 2)}
          </pre>
        )}
      </div>
    </div>
  );
}

function TypeBadge({
  category,
  type,
}: {
  category: string;
  type?: string;
}) {
  const colors: Record<string, string> = {
    tool_call: "bg-accent-blue/20 text-accent-blue border-accent-blue",
    agent_transfer: "bg-terminal-amber/20 text-terminal-amber border-terminal-amber",
    planner: "bg-terminal-green/20 text-terminal-green border-terminal-green",
    model_response: "bg-terminal-amber/20 text-terminal-amber border-terminal-amber",
    system: "bg-txt-secondary/20 text-txt-secondary border-txt-secondary",
    other: "bg-txt-secondary/20 text-txt-secondary border-txt-secondary",
  };

  return (
    <span
      className={cn(
        "inline-block px-1.5 py-0.5 rounded-sm text-[0.65rem] font-bold ml-1 uppercase border",
        colors[category] ?? colors.other,
      )}
    >
      {type?.replace(/_/g, " ") ?? category}
    </span>
  );
}
