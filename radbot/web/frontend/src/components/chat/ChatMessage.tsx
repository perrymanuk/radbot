import { useState } from "react";
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
      // Stop
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
        state === "playing" && "border-terminal-green text-terminal-green",
        state === "loading" && "border-terminal-amber text-terminal-amber cursor-wait",
      )}
      title={state === "playing" ? "Stop" : "Play TTS"}
    >
      {label}
    </button>
  );
}

export default function ChatMessage({ message }: Props) {
  const prompt = getPrompt(message);

  return (
    <div
      className={cn(
        "w-full mb-1 relative",
        "after:content-[''] after:absolute after:bottom-0 after:left-0 after:right-0 after:h-px after:bg-accent-blue/10",
      )}
    >
      <div className="py-0.5 break-words whitespace-pre-wrap relative leading-[1.15]">
        <span
          className={cn(
            "font-normal tracking-[0.5px] text-sm sm:text-[0.85rem]",
            prompt.colorClass,
          )}
        >
          {prompt.text}
        </span>
        {/* TTS button for assistant messages */}
        {message.role === "assistant" && (
          <TTSButton text={message.content} />
        )}
        <span className="text-txt-primary">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              p: ({ children }) => (
                <span className="inline">{children}</span>
              ),
              code: ({ className, children, ...props }) => {
                const isBlock = className?.includes("language-");
                if (isBlock) {
                  return (
                    <pre className="bg-black/70 p-3 my-3 border border-border overflow-x-auto relative">
                      <span className="absolute top-0 right-0 text-terminal-amber text-[0.7rem] bg-black/70 px-1.5 py-0.5 tracking-wider">
                        {className?.replace("language-", "").toUpperCase() ??
                          "OUTPUT"}
                      </span>
                      <code
                        className={cn(
                          "bg-transparent p-0 border-none text-txt-primary text-[0.9rem] block leading-relaxed",
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
                    className="font-mono bg-black/30 px-1 py-0.5 text-[0.9em] text-accent-blue border-l border-accent-blue"
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
                  className="text-accent-blue underline hover:text-accent-blue/80"
                >
                  {children}
                </a>
              ),
              ul: ({ children }) => (
                <ul className="list-disc list-inside ml-2 my-1">{children}</ul>
              ),
              ol: ({ children }) => (
                <ol className="list-decimal list-inside ml-2 my-1">
                  {children}
                </ol>
              ),
              li: ({ children }) => (
                <li className="mb-0.5">{children}</li>
              ),
              blockquote: ({ children }) => (
                <blockquote className="border-l-2 border-accent-blue pl-3 my-2 text-txt-secondary italic">
                  {children}
                </blockquote>
              ),
              h1: ({ children }) => (
                <span className="text-lg font-bold text-accent-blue block mt-2 mb-1">
                  {children}
                </span>
              ),
              h2: ({ children }) => (
                <span className="text-base font-bold text-accent-blue block mt-2 mb-1">
                  {children}
                </span>
              ),
              h3: ({ children }) => (
                <span className="text-sm font-bold text-accent-blue block mt-1 mb-0.5">
                  {children}
                </span>
              ),
              table: ({ children }) => (
                <table className="border-collapse border border-border my-2 text-sm w-full">
                  {children}
                </table>
              ),
              th: ({ children }) => (
                <th className="border border-border bg-bg-tertiary px-2 py-1 text-left text-accent-blue">
                  {children}
                </th>
              ),
              td: ({ children }) => (
                <td className="border border-border px-2 py-1">
                  {children}
                </td>
              ),
            }}
          >
            {message.content}
          </ReactMarkdown>
        </span>
      </div>
    </div>
  );
}
