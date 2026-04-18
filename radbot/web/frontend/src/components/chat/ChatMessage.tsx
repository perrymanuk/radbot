import { useState, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Message } from "@/types";
import { cn } from "@/lib/utils";
import * as api from "@/lib/api";
import {
  MediaCard,
  SeasonBreakdownCard,
  HaDeviceCard,
  type MediaCardData,
  type SeasonBreakdownData,
  type HaDevice,
} from "@/components/chat/AgentCards";
import HandoffLine, { type HandoffInfo } from "@/components/chat/HandoffLine";
import InboxSummary, {
  type InboxSummaryData,
} from "@/components/chat/InboxSummary";
import { agentFor, type AgentIdentity } from "@/components/chat/agent-registry";

interface Props {
  message: Message;
}

// ── Agent identity ──────────────────────────────────────
// Agents come from the shared registry. User/system are local since they
// aren't real agents.
const USER: AgentIdentity = {
  id: "PERRY", name: "perry@radbox", glyph: "P", tint: "#3584e4",
  textClass: "text-accent-blue", bgClass: "bg-accent-blue/10 border-accent-blue/30",
};
const SYSTEM: AgentIdentity = {
  id: "SYSTEM", name: "system", glyph: "S", tint: "#CC0000",
  textClass: "text-terminal-red", bgClass: "bg-terminal-red/10 border-terminal-red/30",
};

function identityFor(message: Message): AgentIdentity {
  if (message.role === "user") return USER;
  if (message.role === "system") return SYSTEM;
  return agentFor(message.agent);
}

// ── AgentPill — left-column identity badge ──────────────
function AgentPill({ id }: { id: AgentIdentity }) {
  const label = id.id === "PERRY" || id.id === "SYSTEM" ? id.name : id.name.toLowerCase();
  return (
    <div className={cn(
      "inline-flex items-center gap-1.5 px-1 py-0.5 rounded-sm border select-none",
      id.bgClass,
    )}>
      <span
        className="inline-grid place-items-center w-[14px] h-[14px] rounded-[2px] font-mono text-[0.6rem] font-bold leading-none"
        style={{ background: id.tint, color: "#0e1419" }}
        aria-hidden
      >
        {id.glyph}
      </span>
      <span className={cn("font-mono text-[0.65rem] font-semibold tracking-[0.04em]", id.textClass)}>
        {label}
      </span>
    </div>
  );
}

// ── TTS button ──────────────────────────────────────────
function TTSButton({ text }: { text: string }) {
  const [state, setState] = useState<"idle" | "loading" | "playing">("idle");
  const [audioCtx] = useState(() => ({ ref: null as AudioContext | null }));
  const [source, setSource] = useState<AudioBufferSourceNode | null>(null);

  const play = async () => {
    if (state === "playing") {
      source?.stop();
      setSource(null);
      setState("idle");
      return;
    }
    setState("loading");
    try {
      const audioData = await api.synthesizeSpeech(text);
      if (!audioCtx.ref) audioCtx.ref = new AudioContext();
      const buffer = await audioCtx.ref.decodeAudioData(audioData);
      const src = audioCtx.ref.createBufferSource();
      src.buffer = buffer;
      src.connect(audioCtx.ref.destination);
      src.onended = () => { setState("idle"); setSource(null); };
      src.start();
      setSource(src);
      setState("playing");
    } catch (err) {
      console.error("[TTS] Error:", err);
      setState("idle");
    }
  };

  const label = state === "loading" ? "…" : state === "playing" ? "■" : "▶";
  return (
    <button
      onClick={play}
      aria-label={state === "playing" ? "Stop playback" : "Play text-to-speech"}
      className={cn(
        "w-6 h-6 grid place-items-center border border-border bg-bg-tertiary text-[0.7rem] font-mono",
        "cursor-pointer transition-all rounded-sm",
        "hover:bg-accent-blue hover:text-bg-primary",
        "focus:outline-none focus:ring-1 focus:ring-accent-blue",
        state === "playing" && "border-terminal-green text-terminal-green",
        state === "loading" && "border-terminal-amber text-terminal-amber cursor-wait",
      )}
      title={state === "playing" ? "Stop" : "Play TTS"}
    >
      {label}
    </button>
  );
}

// ── Copy button (block-level code) ──────────────────────
function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const ta = document.createElement("textarea");
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [text]);

  return (
    <button
      onClick={handleCopy}
      className={cn(
        "absolute top-0 right-16 text-[0.65rem] px-1.5 py-0.5 font-mono",
        "border border-border bg-black/70 cursor-pointer transition-all",
        "hover:bg-accent-blue hover:text-bg-primary",
        "focus:outline-none focus:ring-1 focus:ring-accent-blue",
        copied ? "text-terminal-green border-terminal-green/50" : "text-txt-secondary",
      )}
      title="Copy to clipboard"
    >
      {copied ? "COPIED" : "COPY"}
    </button>
  );
}

// ── Collapsible wrapper for long messages ───────────────
function CollapsibleContent({ children, lineCount }: { children: React.ReactNode; lineCount: number }) {
  const [collapsed, setCollapsed] = useState(lineCount > 20);
  if (lineCount <= 20) return <>{children}</>;
  return (
    <div className="relative">
      <div className={cn(collapsed && "max-h-[200px] overflow-hidden")}>{children}</div>
      {collapsed && (
        <div className="absolute bottom-0 left-0 right-0 h-12 bg-gradient-to-t from-bg-primary to-transparent pointer-events-none" />
      )}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className={cn(
          "relative z-10 text-[0.7rem] text-accent-blue font-mono mt-1 cursor-pointer",
          "hover:text-accent-blue/80 transition-colors",
          "focus:outline-none focus:ring-1 focus:ring-accent-blue",
          collapsed && "-mt-2",
        )}
      >
        {collapsed ? `▼ SHOW MORE (${lineCount} lines)` : "▲ SHOW LESS"}
      </button>
    </div>
  );
}

function formatTime(ts: number): string {
  const d = new Date(ts);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export default function ChatMessage({ message }: Props) {
  const id = identityFor(message);
  const lineCount = message.content.split("\n").length;
  const isAssistant = message.role === "assistant";
  const isSystem = message.role === "system";

  return (
    <article
      className={cn(
        "group relative px-4 sm:px-5 py-3 border-b border-border/40",
        isSystem && "opacity-75",
      )}
      aria-label={`Message from ${id.name}`}
    >
      {/* Top row: pill · timestamp · actions */}
      <header className="flex items-center gap-2 mb-1.5">
        <AgentPill id={id} />
        <time
          dateTime={new Date(message.timestamp).toISOString()}
          className="font-mono text-[0.65rem] text-txt-secondary tracking-wider"
        >
          {formatTime(message.timestamp)}
        </time>
        <div className="flex-1" />
        {/* Right-side action cluster */}
        {isAssistant && (
          <div className="flex items-center gap-1 opacity-60 group-hover:opacity-100 transition-opacity">
            <TTSButton text={message.content} />
          </div>
        )}
      </header>

      {/* Body — flush to the pill column via the article's padding */}
      <div className="font-sans text-txt-primary text-[0.8125rem] sm:text-[0.875rem] leading-[1.55] [overflow-wrap:anywhere]">
        <CollapsibleContent lineCount={lineCount}>
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
              code: ({ className, children, ...props }) => {
                const isBlock = className?.includes("language-");
                if (isBlock) {
                  const codeText = String(children).replace(/\n$/, "");

                  // Agent-card render protocol: ```radbot:<kind>\n{json}\n```
                  const radbotKind = className?.match(/language-radbot:(\S+)/)?.[1];
                  if (radbotKind) {
                    try {
                      const data = JSON.parse(codeText);
                      switch (radbotKind) {
                        case "media":
                          return <MediaCard m={data as MediaCardData} />;
                        case "seasons":
                          return <SeasonBreakdownCard data={data as SeasonBreakdownData} />;
                        case "ha-device":
                          return <HaDeviceCard d={data as HaDevice} />;
                        case "handoff":
                          return <HandoffLine handoff={data as HandoffInfo} />;
                        case "inbox":
                          return <InboxSummary s={data as InboxSummaryData} />;
                        default:
                          // fall through to default code rendering
                      }
                    } catch {
                      // Invalid JSON — fall through to show raw block.
                    }
                  }

                  return (
                    <pre className="bg-black/70 p-3 my-3 border border-border overflow-x-auto relative group/code">
                      <span className="absolute top-0 right-0 text-terminal-amber text-[0.7rem] bg-black/70 px-1.5 py-0.5 tracking-wider">
                        {className?.replace("language-", "").toUpperCase() ?? "OUTPUT"}
                      </span>
                      <CopyButton text={codeText} />
                      <code
                        className={cn(
                          "bg-transparent p-0 border-none text-txt-primary text-[0.85rem] block leading-relaxed",
                          className,
                        )}
                        {...props}
                      >
                        {children}
                      </code>
                    </pre>
                  );
                }
                return (
                  <code
                    className="font-mono bg-black/30 px-1 py-0.5 text-[0.85em] text-accent-blue border-l border-accent-blue"
                    {...props}
                  >
                    {children}
                  </code>
                );
              },
              pre: ({ children }) => <>{children}</>,
              a: ({ href, children }) => (
                <a
                  href={href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-accent-blue underline hover:text-accent-blue/80 focus:outline-none focus:ring-1 focus:ring-accent-blue"
                >
                  {children}
                </a>
              ),
              ul: ({ children }) => <ul className="list-disc list-inside ml-3 my-2 space-y-1">{children}</ul>,
              ol: ({ children }) => <ol className="list-decimal list-inside ml-3 my-2 space-y-1">{children}</ol>,
              li: ({ children }) => <li className="leading-relaxed">{children}</li>,
              blockquote: ({ children }) => (
                <blockquote className="border-l-2 border-accent-blue pl-3 my-2 text-txt-secondary italic">
                  {children}
                </blockquote>
              ),
              h1: ({ children }) => <span className="text-lg font-bold text-accent-blue block mt-3 mb-1.5">{children}</span>,
              h2: ({ children }) => <span className="text-base font-bold text-accent-blue block mt-3 mb-1.5">{children}</span>,
              h3: ({ children }) => <span className="text-sm font-bold text-accent-blue block mt-2 mb-1">{children}</span>,
              table: ({ children }) => (
                <div className="overflow-x-auto my-2">
                  <table className="border-collapse border border-border text-sm w-full">{children}</table>
                </div>
              ),
              th: ({ children }) => (
                <th className="border border-border bg-bg-tertiary px-2 py-1.5 text-left text-accent-blue">{children}</th>
              ),
              td: ({ children }) => <td className="border border-border px-2 py-1.5">{children}</td>,
              strong: ({ children }) => <strong className="font-bold text-terminal-amber">{children}</strong>,
            }}
          >
            {message.content}
          </ReactMarkdown>
        </CollapsibleContent>
      </div>
    </article>
  );
}
