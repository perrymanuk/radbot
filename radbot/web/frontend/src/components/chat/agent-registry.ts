// ─────────────────────────────────────────────────────────
// AGENT REGISTRY
//
// Single source of truth for sub-agent identity (display name,
// 1-char glyph, accent color token, Tailwind helpers).
//
// Consumed by:
//   - ChatMessage.tsx       (AgentPill)
//   - HandoffLine.tsx       (both ends of the arrow)
//   - AgentCards.tsx        (fallback color when structured
//                             payloads don't carry their own)
//
// ── Backend surfacing ────────────────────────────────────
// Ideally the backend returns this via /api/agent-info so new
// sub-agents don't require a frontend edit. Until then, extend
// this map whenever a new agent is registered in ADK.
// ─────────────────────────────────────────────────────────

export interface AgentIdentity {
  id: string;             // canonical id, uppercase
  name: string;           // display name
  glyph: string;          // 1-char badge glyph
  tint: string;           // CSS color value for pill/glow
  textClass: string;      // tailwind text color
  bgClass: string;        // tailwind bg+border tint for pill
  role?: string;          // short role tag (for TASKS / MEDIA headers)
}

export const AGENTS: Record<string, AgentIdentity> = {
  BETO:    { id: "BETO",    name: "BETO",    glyph: "B", tint: "#ff9966",
             textClass: "text-radbot-sunset",  bgClass: "bg-radbot-sunset/15 border-radbot-sunset/40",
             role: "host" },
  SCOUT:   { id: "SCOUT",   name: "SCOUT",   glyph: "S", tint: "#33FF33",
             textClass: "text-terminal-green", bgClass: "bg-terminal-green/15 border-terminal-green/40",
             role: "media" },
  AXEL:    { id: "AXEL",    name: "AXEL",    glyph: "A", tint: "#3584e4",
             textClass: "text-accent-blue",    bgClass: "bg-accent-blue/15 border-accent-blue/40",
             role: "code" },
  CASA:    { id: "CASA",    name: "CASA",    glyph: "C", tint: "#33FF33",
             textClass: "text-terminal-green", bgClass: "bg-terminal-green/15 border-terminal-green/40",
             role: "home" },
  PLANNER: { id: "PLANNER", name: "PLANNER", glyph: "P", tint: "#3584e4",
             textClass: "text-accent-blue",    bgClass: "bg-accent-blue/15 border-accent-blue/40",
             role: "planning" },
  TRACKER: { id: "TRACKER", name: "TRACKER", glyph: "T", tint: "#FFBF00",
             textClass: "text-terminal-amber", bgClass: "bg-terminal-amber/15 border-terminal-amber/40",
             role: "tasks" },
  COMMS:   { id: "COMMS",   name: "COMMS",   glyph: "C", tint: "#33FF33",
             textClass: "text-terminal-green", bgClass: "bg-terminal-green/15 border-terminal-green/40",
             role: "inbox" },
};

export function agentFor(id: string | undefined | null): AgentIdentity {
  if (!id) return AGENTS.BETO;
  const key = id.toUpperCase();
  return (
    AGENTS[key] ?? {
      id: key,
      name: key,
      glyph: key[0] ?? "?",
      tint: "#ff9966",
      textClass: "text-radbot-sunset",
      bgClass: "bg-radbot-sunset/15 border-radbot-sunset/40",
    }
  );
}
