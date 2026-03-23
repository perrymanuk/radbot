import { useState, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Message } from "@/types";
import { cn } from "@/lib/utils";
import * as api from "@/lib/api";

interface Props {
  message: Message;
}

const agentColors: Record<string, string> = {
  BETO: "text-terminal-amber",
  SCOUT: "text-terminal-green",
  AXEL: "text-accent-blue",
  CASA: "text-terminal-green",
  PLANNER: "text-accent-blue",
  TRACKER: "text-terminal-amber",
  COMMS: "text-terminal-green",
};

const agentBadgeColors: Record<string, string> = {
  BETO: "bg-terminal-amber/15 text-terminal-amber border-terminal-amber/30",
  SCOUT: "bg-terminal-green/15 text-terminal-green border-terminal-green/30",
  AXEL: "bg-accent-blue/15 text-accent-blue border-accent-blue/30",
  CASA: "bg-terminal-green/15 text-terminal-green border-terminal-green/30",
  PLANNER: "bg-accent-blue/15 text-accent-blue border-accent-blue/30",
  TRACKER: "bg-terminal-amber/15 text-terminal-amber border-terminal-amber/30",
  COMMS: "bg-terminal-green/15 text-terminal-green border-terminal-green/30",
};

function getPrompt(message: Message): { text: string; colorClass: string } {
  if (message.role === "user") {
    return { text: "perry@radbox:~$ ", colorClass: "text-accent-blue" };
  }
  if (message.role === "system") {
    return { text: "system@radbox:~$ ", colorClass: "text-terminal-red" };
  }
  // assistant
  const agent = message.agent?.toUpperCase() ?? "BETO";
  const color = agentColors[agent] ?? "text-terminal-amber";
  return { text: `${agent.toLowerCase()}@radbox:~$ `, colorClass: color };
}

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
      src.onended = () => {
        setState("idle");
        setSource(null);
      };
      src.start();
      setSource(src);
      setState("playing");
    } catch (err) {
      console.error("[TTS] Error:", err);
      setState("idle");
    }
  };

  const label = state === "loading" ? "..." : state === "playing" ? "\u25A0" : "\u25B6";

  return (
    <button
      onClick={play}
      className={cn(
        "ml-2 px-1.5 py-0 border border-border bg-bg-tertiary text-[0.7rem] font-mono",
        "cursor-pointer transition-all inline-flex items-center",
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

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback for older browsers
      const ta = document.createElement("textarea");
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
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

function AgentBadge({ agent }: { agent: string }) {
  const name = agent.toUpperCase();
  if (name === "BETO") return null; // Don't badge the main agent
  const colors = agentBadgeColors[name] ?? "bg-txt-secondary/15 text-txt-secondary border-txt-secondary/30";
  return (
    <span className={cn(
      "inline-flex items-center px-1.5 py-0 text-[0.6rem] font-mono uppercase tracking-wider border rounded-sm ml-2",
      colors,
    )}>
      {name}
    </span>
  );
}

function CollapsibleContent({ children, lineCount }: { children: React.ReactNode; lineCount: number }) {
  const [collapsed, setCollapsed] = useState(lineCount > 20);
  const threshold = 20;

  if (lineCount <= threshold) {
    return <>{children}</>;
  }

  return (
    <div className="relative">
      <div className={cn(
        collapsed && "max-h-[200px] overflow-hidden",
      )}>
        {children}
      </div>
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
        {collapsed ? `\u25BC SHOW MORE (${lineCount} lines)` : "\u25B2 SHOW LESS"}
      </button>
    </div>
  );
}

function formatTimestamp(ts: number): string {
  const d = new Date(ts);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export default function ChatMessage({ message }: Props) {
  const prompt = getPrompt(message);
  const lineCount = message.content.split("\n").length;
  const isAssistant = message.role === "assistant";
  const agent = message.agent?.toUpperCase() ?? "BETO";

  return (
    <div
      className={cn(
        "w-full px-2",
        "mb-2 relative group",
        isAssistant && "bg-bg-secondary/30 py-1.5",
        message.role === "user" && "py-1",
        message.role === "system" && "py-1 opacity-80",
      )}
    >
      {/* Timestamp - visible on hover */}
      <span className="absolute top-1 right-2 text-[0.6rem] text-txt-secondary/50 opacity-0 group-hover:opacity-100 transition-opacity font-mono">
        {formatTimestamp(message.timestamp)}
      </span>

      <div className="break-words whitespace-pre-wrap relative leading-[1.45]">
        {/* Prompt line with agent badge */}
        <div className="flex items-center mb-0.5">
          <span
            className={cn(
              "font-normal tracking-[0.5px] text-[0.8125rem] sm:text-[0.85rem] leading-tight",
              prompt.colorClass,
            )}
          >
            {prompt.text}
          </span>
          {/* TTS button for assistant messages */}
          {isAssistant && <TTSButton text={message.content} />}
          {/* Agent badge for sub-agents */}
          {isAssistant && message.agent && <AgentBadge agent={agent} />}
        </div>

        {/* Message content */}
        <div className="text-txt-primary text-[0.8125rem] sm:text-[0.85rem] pl-1">
          <CollapsibleContent lineCount={lineCount}>
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                p: ({ children }) => (
                  <p className="mb-2 last:mb-0">{children}</p>
                ),
                code: ({ className, children, ...props }) => {
                  const isBlock = className?.includes("language-");
                  if (isBlock) {
                    const codeText = String(children).replace(/\n$/, "");
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
                ul: ({ children }) => (
                  <ul className="list-disc list-inside ml-3 my-2 space-y-1">{children}</ul>
                ),
                ol: ({ children }) => (
                  <ol className="list-decimal list-inside ml-3 my-2 space-y-1">
                    {children}
                  </ol>
                ),
                li: ({ children }) => (
                  <li className="leading-relaxed">{children}</li>
                ),
                blockquote: ({ children }) => (
                  <blockquote className="border-l-2 border-accent-blue pl-3 my-2 text-txt-secondary italic">
                    {children}
                  </blockquote>
                ),
                h1: ({ children }) => (
                  <span className="text-lg font-bold text-accent-blue block mt-3 mb-1.5">
                    {children}
                  </span>
                ),
                h2: ({ children }) => (
                  <span className="text-base font-bold text-accent-blue block mt-3 mb-1.5">
                    {children}
                  </span>
                ),
                h3: ({ children }) => (
                  <span className="text-sm font-bold text-accent-blue block mt-2 mb-1">
                    {children}
                  </span>
                ),
                table: ({ children }) => (
                  <div className="overflow-x-auto my-2">
                    <table className="border-collapse border border-border text-sm w-full">
                      {children}
                    </table>
                  </div>
                ),
                th: ({ children }) => (
                  <th className="border border-border bg-bg-tertiary px-2 py-1.5 text-left text-accent-blue">
                    {children}
                  </th>
                ),
                td: ({ children }) => (
                  <td className="border border-border px-2 py-1.5">
                    {children}
                  </td>
                ),
                strong: ({ children }) => (
                  <strong className="font-bold text-terminal-amber">{children}</strong>
                ),
              }}
            >
              {message.content}
            </ReactMarkdown>
          </CollapsibleContent>
        </div>
      </div>
    </div>
  );
}
