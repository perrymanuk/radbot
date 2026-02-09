import { useState, useRef, useCallback, useEffect } from "react";
import { useAppStore } from "@/stores/app-store";
import { wsSend } from "@/hooks/use-websocket";
import { useSTT } from "@/hooks/use-stt";
import CommandSuggestions from "./CommandSuggestions";
import EmojiSuggestions from "./EmojiSuggestions";
import { cn } from "@/lib/utils";

const COMMANDS = [
  { name: "/sessions", description: "Toggle sessions panel" },
  { name: "/tasks", description: "Toggle tasks panel" },
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

  // STT hook - inject transcript into input
  const handleTranscript = useCallback((transcript: string) => {
    setText((prev) => (prev ? prev + " " + transcript : transcript));
  }, []);
  const stt = useSTT(handleTranscript);

  const isDisabled =
    connectionStatus === "disconnected" ||
    connectionStatus === "error";

  // Auto-resize textarea
  const resize = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 120) + "px";
  }, []);

  useEffect(() => {
    resize();
  }, [text, resize]);

  const send = useCallback(() => {
    const trimmed = text.trim();
    if (!trimmed) return;

    // Handle slash commands locally
    if (trimmed.startsWith("/")) {
      const parts = trimmed.slice(1).split(" ");
      const cmd = parts[0].toLowerCase();

      switch (cmd) {
        case "sessions":
          togglePanel("sessions");
          addMessage({
            id: crypto.randomUUID(),
            role: "system",
            content: "Sessions panel toggled",
            timestamp: Date.now(),
          });
          break;
        case "tasks":
          togglePanel("tasks");
          addMessage({
            id: crypto.randomUUID(),
            role: "system",
            content: "Tasks panel toggled",
            timestamp: Date.now(),
          });
          break;
        case "events":
          togglePanel("events");
          addMessage({
            id: crypto.randomUUID(),
            role: "system",
            content: "Events panel toggled",
            timestamp: Date.now(),
          });
          break;
        case "clear":
          clearMessages();
          break;
        case "help": {
          let msg = "**Available Commands:**\n\n";
          COMMANDS.forEach((c) => {
            msg += `- \`${c.name}\` - ${c.description}\n`;
          });
          msg += "\n**Controls:** Enter=send, Shift+Enter=newline, Up/Down=history";
          addMessage({
            id: crypto.randomUUID(),
            role: "system",
            content: msg,
            timestamp: Date.now(),
          });
          break;
        }
        default:
          // Unknown command - send to server
          wsSend(trimmed);
          break;
      }
    } else {
      // Add user message to UI immediately
      addMessage({
        id: crypto.randomUUID(),
        role: "user",
        content: trimmed,
        timestamp: Date.now(),
      });

      // Send via WebSocket
      wsSend(trimmed);
    }

    addToInputHistory(trimmed);
    setText("");
    setMemoryMode(false);
  }, [text, togglePanel, addMessage, clearMessages, addToInputHistory, setMemoryMode]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    // If command suggestions are visible, let them handle arrow keys
    if (commandFilter !== null || emojiFilter !== null) return;

    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }

    if (e.key === "ArrowUp" && text === "") {
      e.preventDefault();
      const prev = navigateHistory("up");
      setText(prev);
    }

    if (e.key === "ArrowDown" && text === "") {
      e.preventDefault();
      const next = navigateHistory("down");
      setText(next);
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const val = e.target.value;
    setText(val);

    // Memory mode: start with #
    if (val.startsWith("#") && !memoryMode) {
      setMemoryMode(true);
    } else if (!val.startsWith("#") && memoryMode) {
      setMemoryMode(false);
    }

    // Command autocomplete
    if (val.startsWith("/")) {
      const cmdPart = val.split(" ")[0];
      setCommandFilter(cmdPart);
    } else {
      setCommandFilter(null);
    }

    // Emoji autocomplete
    const cursorPos = e.target.selectionStart;
    const colonIdx = val.lastIndexOf(":", cursorPos);
    if (
      colonIdx !== -1 &&
      !val.slice(colonIdx, cursorPos).includes(" ") &&
      // Don't trigger if it's a completed shortcode
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
      const newText =
        text.slice(0, colonIdx) + shortcode + text.slice(cursorPos);
      setText(newText);
    }
    setEmojiFilter(null);
    textareaRef.current?.focus();
  };

  const micLabel =
    stt.state === "recording" ? "REC" : stt.state === "processing" ? "..." : "MIC";

  return (
    <div className="px-1 py-1 border-t border-border bg-bg-primary flex-shrink-0 z-10">
      <div className="flex gap-1.5 relative items-stretch">
        {/* $ prompt prefix */}
        <span className="absolute left-2 top-1/2 -translate-y-1/2 text-accent-blue font-bold text-base z-10 pointer-events-none">
          {memoryMode ? "#" : "$"}
        </span>

        {/* Command suggestions */}
        {commandFilter !== null && (
          <CommandSuggestions
            filter={commandFilter}
            commands={COMMANDS}
            onSelect={selectCommand}
            onClose={() => setCommandFilter(null)}
          />
        )}

        {/* Emoji suggestions */}
        {emojiFilter !== null && (
          <EmojiSuggestions
            filter={emojiFilter}
            onSelect={selectEmoji}
            onClose={() => setEmojiFilter(null)}
          />
        )}

        <textarea
          ref={textareaRef}
          value={text}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder={
            connectionStatus === "thinking"
              ? "Agent is thinking..."
              : "Type a message..."
          }
          disabled={isDisabled}
          rows={1}
          className={cn(
            "flex-1 pl-6 pr-2 py-1.5 border border-border resize-none outline-none",
            "text-[0.85rem] min-h-[30px] max-h-[120px] overflow-y-auto",
            "bg-bg-secondary text-txt-primary font-mono",
            "caret-accent-blue transition-all",
            "focus:border-accent-blue focus:shadow-[0_0_5px_rgba(53,132,228,0.3)]",
            "placeholder:text-txt-secondary/50",
            memoryMode && "border-terminal-green caret-terminal-green",
          )}
        />

        {/* MIC button */}
        <button
          onClick={stt.toggle}
          disabled={stt.state === "processing"}
          className={cn(
            "px-2 border border-border bg-bg-tertiary text-txt-primary",
            "cursor-pointer flex items-center justify-center transition-all",
            "uppercase tracking-wider text-[0.7rem] font-mono",
            "hover:bg-accent-blue hover:text-bg-primary",
            stt.state === "recording" &&
              "bg-terminal-red/20 border-terminal-red text-terminal-red animate-pulse",
            stt.state === "processing" &&
              "border-terminal-amber text-terminal-amber cursor-wait",
          )}
        >
          {micLabel}
        </button>

        {/* SEND button */}
        <button
          onClick={send}
          disabled={isDisabled || !text.trim()}
          className={cn(
            "px-3 border border-border bg-bg-tertiary text-txt-primary",
            "cursor-pointer flex items-center justify-center transition-all",
            "uppercase tracking-wider text-[0.7rem] font-mono",
            "hover:bg-accent-blue hover:text-bg-primary",
            "disabled:border-accent-blue/30 disabled:text-accent-blue/30 disabled:bg-bg-tertiary disabled:cursor-not-allowed",
          )}
        >
          SEND
        </button>
      </div>
    </div>
  );
}
