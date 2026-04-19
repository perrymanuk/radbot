import { useState, useRef, useCallback, useEffect } from "react";
import { useAppStore } from "@/stores/app-store";
import { wsSend } from "@/hooks/use-websocket";
import { useSTT } from "@/hooks/use-stt";
import CommandSuggestions from "./CommandSuggestions";
import EmojiSuggestions from "./EmojiSuggestions";
import { Icon } from "./icons";
import { cn, uuid } from "@/lib/utils";

const COMMANDS = [
  { name: "/sessions", description: "Toggle sessions panel" },
  { name: "/events", description: "Toggle events panel" },
  { name: "/clear", description: "Clear conversation history" },
  { name: "/help", description: "Show available commands" },
];

export default function ChatInput() {
  const [text, setText] = useState("");
  const [commandFilter, setCommandFilter] = useState<string | null>(null);
  const [emojiFilter, setEmojiFilter] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const connectionStatus = useAppStore((s) => s.connectionStatus);
  const addMessage = useAppStore((s) => s.addMessage);
  const addToInputHistory = useAppStore((s) => s.addToInputHistory);
  const navigateHistory = useAppStore((s) => s.navigateHistory);
  const togglePanel = useAppStore((s) => s.togglePanel);
  const clearMessages = useAppStore((s) => s.clearMessages);
  const memoryMode = useAppStore((s) => s.memoryMode);
  const setMemoryMode = useAppStore((s) => s.setMemoryMode);

  const handleTranscript = useCallback((transcript: string) => {
    setText((prev) => (prev ? prev + " " + transcript : transcript));
  }, []);
  const stt = useSTT(handleTranscript);

  const isDisabled =
    connectionStatus === "disconnected" || connectionStatus === "error";
  const isThinking = connectionStatus === "thinking";

  // Auto-resize textarea (1–~8 rows, capped)
  const resize = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "0px";
    el.style.height = Math.min(160, el.scrollHeight) + "px";
  }, []);
  useEffect(() => {
    resize();
  }, [text, resize]);

  // ⌘K / Ctrl+K focuses the composer
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        textareaRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const send = useCallback(() => {
    const trimmed = text.trim();
    if (!trimmed) return;

    if (trimmed.startsWith("/")) {
      const parts = trimmed.slice(1).split(" ");
      const cmd = parts[0].toLowerCase();
      switch (cmd) {
        case "sessions":
          togglePanel("sessions");
          addMessage({ id: uuid(), role: "system", content: "Sessions panel toggled", timestamp: Date.now() });
          break;
        case "events":
          togglePanel("events");
          addMessage({ id: uuid(), role: "system", content: "Events panel toggled", timestamp: Date.now() });
          break;
        case "clear":
          clearMessages();
          break;
        case "help": {
          let msg = "**Available Commands:**\n\n";
          COMMANDS.forEach((c) => {
            msg += `- \`${c.name}\` - ${c.description}\n`;
          });
          msg += "\n**Controls:** Enter=send, Shift+Enter=newline, Up/Down=history, ⌘K=focus";
          addMessage({ id: uuid(), role: "system", content: msg, timestamp: Date.now() });
          break;
        }
        default:
          wsSend(trimmed);
      }
    } else {
      addMessage({ id: uuid(), role: "user", content: trimmed, timestamp: Date.now() });
      wsSend(trimmed);
    }

    addToInputHistory(trimmed);
    setText("");
    setMemoryMode(false);
  }, [text, togglePanel, addMessage, clearMessages, addToInputHistory, setMemoryMode]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (commandFilter !== null || emojiFilter !== null) return;
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
    if (e.key === "ArrowUp" && text === "") {
      e.preventDefault();
      setText(navigateHistory("up"));
    }
    if (e.key === "ArrowDown" && text === "") {
      e.preventDefault();
      setText(navigateHistory("down"));
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const val = e.target.value;
    setText(val);

    if (val.startsWith("#") && !memoryMode) setMemoryMode(true);
    else if (!val.startsWith("#") && memoryMode) setMemoryMode(false);

    if (val.startsWith("/")) {
      setCommandFilter(val.split(" ")[0]);
    } else {
      setCommandFilter(null);
    }

    const cursorPos = e.target.selectionStart;
    const colonIdx = val.lastIndexOf(":", cursorPos);
    if (
      colonIdx !== -1 &&
      !val.slice(colonIdx, cursorPos).includes(" ") &&
      !(val.indexOf(":", colonIdx + 1) !== -1 &&
        val.indexOf(":", colonIdx + 1) < cursorPos)
    ) {
      setEmojiFilter(val.slice(colonIdx + 1, cursorPos));
    } else {
      setEmojiFilter(null);
    }
  };

  const selectCommand = (name: string) => {
    setText(name + " ");
    setCommandFilter(null);
    textareaRef.current?.focus();
  };

  const selectEmoji = (shortcode: string) => {
    const cursorPos = textareaRef.current?.selectionStart ?? text.length;
    const colonIdx = text.lastIndexOf(":", cursorPos);
    if (colonIdx !== -1) {
      setText(text.slice(0, colonIdx) + shortcode + text.slice(cursorPos));
    }
    setEmojiFilter(null);
    textareaRef.current?.focus();
  };

  const hasText = text.trim().length > 0;
  const accentClass = memoryMode ? "text-radbot-magenta" : "text-radbot-sunset";
  const ringClass = memoryMode
    ? "ring-radbot-magenta/20 border-radbot-magenta/50"
    : "ring-radbot-sunset/10 border-border";

  const placeholder = isThinking
    ? "agent is thinking…"
    : memoryMode
      ? "remember this…"
      : "type a message, / for commands, # to save to memory";

  return (
    <div className="relative px-3 pt-2 pb-1 bg-bg-primary border-t border-border flex-shrink-0 z-10">
      {/* Command suggestions (slash) */}
      {commandFilter !== null && (
        <CommandSuggestions
          filter={commandFilter}
          commands={COMMANDS}
          onSelect={selectCommand}
          onClose={() => setCommandFilter(null)}
        />
      )}

      {/* Emoji suggestions (colon) */}
      {emojiFilter !== null && (
        <EmojiSuggestions
          filter={emojiFilter}
          onSelect={selectEmoji}
          onClose={() => setEmojiFilter(null)}
        />
      )}

      {/* Input shell */}
      <div
        className={cn(
          "flex items-end gap-2.5 px-3 py-2 bg-bg-secondary rounded border ring-[3px] transition-all",
          ringClass,
        )}
      >
        <span
          className={cn(
            "font-mono text-[0.85rem] font-bold leading-[22px] select-none",
            accentClass,
          )}
          aria-hidden
        >
          {memoryMode ? "#" : "$"}
        </span>
        <textarea
          ref={textareaRef}
          value={text}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          disabled={isDisabled}
          rows={1}
          placeholder={placeholder}
          aria-label="Message composer"
          data-test="chat-input"
          className={cn(
            "flex-1 resize-none bg-transparent outline-none",
            "font-sans text-[0.875rem] leading-[1.55] text-txt-primary",
            "placeholder:text-txt-secondary/60",
            "min-h-[22px] max-h-[160px]",
            "disabled:opacity-50",
          )}
        />
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={stt.toggle}
            disabled={stt.state === "processing"}
            aria-label={
              stt.state === "recording" ? "Stop recording" : "Start voice input"
            }
            className={cn(
              "w-7 h-7 grid place-items-center rounded border transition-colors",
              "focus:outline-none focus:ring-1 focus:ring-accent-blue",
              stt.state === "recording"
                ? "border-terminal-red text-terminal-red bg-terminal-red/15 animate-pulse"
                : stt.state === "processing"
                  ? "border-terminal-amber text-terminal-amber cursor-wait"
                  : "border-border text-txt-secondary hover:bg-bg-tertiary hover:text-txt-primary",
            )}
          >
            <Icon.mic />
          </button>
          <button
            type="button"
            onClick={send}
            disabled={!hasText || isDisabled}
            aria-label="Send message"
            data-test="chat-send"
            className={cn(
              "inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded border transition-all",
              "font-mono text-[0.68rem] font-bold tracking-[0.08em]",
              hasText && !isDisabled
                ? cn(
                    memoryMode
                      ? "bg-radbot-magenta text-bg-primary border-radbot-magenta"
                      : "bg-radbot-sunset text-bg-primary border-radbot-sunset",
                    "hover:brightness-110",
                  )
                : "bg-bg-tertiary text-txt-secondary/70 border-border cursor-not-allowed",
              "focus:outline-none focus:ring-1 focus:ring-accent-blue",
            )}
          >
            SEND
            <span
              className={cn(
                "font-mono text-[0.6rem] px-1 py-0.5 border rounded-sm",
                hasText && !isDisabled ? "border-black/35 bg-black/20" : "border-border bg-transparent",
              )}
            >
              ↵
            </span>
          </button>
        </div>
      </div>

      {/* Hint row */}
      <div className="flex gap-3 pt-1.5 pl-1 font-mono text-[0.6rem] text-txt-secondary/70 flex-wrap">
        <span>↑↓ history</span>
        <span>/ commands</span>
        <span>: emoji</span>
        <span className="text-radbot-magenta"># save to memory</span>
        <span className="ml-auto opacity-60 hidden sm:inline">⌘K focus</span>
      </div>
    </div>
  );
}
