import { useState } from "react";
import { useAppStore } from "@/stores/app-store";
import EventItem from "./EventItem";
import EventDetails from "./EventDetails";
import type { AgentEvent, EventCategory } from "@/types";

const FILTER_OPTIONS: { value: EventCategory | "all"; label: string }[] = [
  { value: "all", label: "All Events" },
  { value: "tool_call", label: "Tool Calls" },
  { value: "model_response", label: "Model Responses" },
  { value: "agent_transfer", label: "Agent Transfers" },
  { value: "planner", label: "Planner" },
  { value: "other", label: "Other" },
];

export default function EventsPanel() {
  const events = useAppStore((s) => s.events);
  const eventFilter = useAppStore((s) => s.eventFilter);
  const setEventFilter = useAppStore((s) => s.setEventFilter);
  const [selectedEvent, setSelectedEvent] = useState<AgentEvent | null>(null);

  const filtered =
    eventFilter === "all"
      ? events
      : events.filter((e) => e.category === eventFilter);

  if (selectedEvent) {
    return (
      <div className="flex flex-col h-full bg-bg-primary">
        <div className="px-2 py-1.5 bg-bg-tertiary border-b border-border flex items-center gap-2">
          <button
            onClick={() => setSelectedEvent(null)}
            className="px-2 py-0.5 border border-border bg-bg-tertiary text-txt-primary text-[0.7rem] font-mono uppercase tracking-wider hover:bg-accent-blue hover:text-bg-primary transition-all cursor-pointer"
          >
            BACK
          </button>
          <span className="text-accent-blue text-[0.9rem] font-mono">
            Event Details
          </span>
        </div>
        <EventDetails event={selectedEvent} />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-bg-primary">
      {/* Header */}
      <div className="px-2 py-1.5 bg-bg-tertiary border-b border-border">
        <span className="text-accent-blue text-[0.9rem] font-mono">
          Events
        </span>
      </div>

      {/* Filter */}
      <div className="p-1.5 border-b border-border">
        <select
          value={eventFilter}
          onChange={(e) =>
            setEventFilter(e.target.value as EventCategory | "all")
          }
          className="w-full bg-bg-secondary text-txt-primary border border-border px-2 py-0.5 font-mono text-[0.75rem] outline-none focus:border-accent-blue h-6"
        >
          {FILTER_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      {/* Event list */}
      <div className="flex-1 overflow-y-auto p-1">
        {filtered.length === 0 ? (
          <div className="p-4 text-center text-txt-secondary text-[0.75rem] italic">
            No events recorded
          </div>
        ) : (
          [...filtered].reverse().map((event, i) => (
            <EventItem
              key={event.id ?? i}
              event={event}
              onClick={() => setSelectedEvent(event)}
            />
          ))
        )}
      </div>
    </div>
  );
}
