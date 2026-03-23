import { useRef, useEffect, useCallback } from "react";
import { Virtuoso, type VirtuosoHandle } from "react-virtuoso";
import { useAppStore } from "@/stores/app-store";
import ChatMessage from "./ChatMessage";

function TypingIndicator() {
  return (
    <div className="w-full px-2 mb-2 py-1">
      <div className="flex items-center gap-2">
        <span className="text-terminal-amber text-[0.8125rem] sm:text-[0.85rem] font-mono tracking-[0.5px]">
          beto@radbox:~$
        </span>
        <div className="flex items-center gap-1">
          <span className="w-1.5 h-1.5 rounded-full bg-terminal-amber animate-bounce [animation-delay:0ms]" />
          <span className="w-1.5 h-1.5 rounded-full bg-terminal-amber animate-bounce [animation-delay:150ms]" />
          <span className="w-1.5 h-1.5 rounded-full bg-terminal-amber animate-bounce [animation-delay:300ms]" />
        </div>
        <span className="text-txt-secondary/60 text-[0.7rem] font-mono ml-1">thinking</span>
      </div>
    </div>
  );
}

export default function MessageList() {
  const messages = useAppStore((s) => s.messages);
  const connectionStatus = useAppStore((s) => s.connectionStatus);
  const virtuosoRef = useRef<VirtuosoHandle>(null);
  const scrollerRef = useRef<HTMLElement | null>(null);
  const isAtBottomRef = useRef(true);
  const isThinking = connectionStatus === "thinking";

  const scrollToBottom = useCallback(() => {
    if (scrollerRef.current) {
      scrollerRef.current.scrollTop = scrollerRef.current.scrollHeight;
    }
  }, []);

  // Scroll to bottom when new messages arrive (if user is at bottom)
  useEffect(() => {
    if (messages.length > 0 && isAtBottomRef.current) {
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          scrollToBottom();
        });
      });
    }
  }, [messages.length, scrollToBottom]);

  // Also scroll when thinking state changes
  useEffect(() => {
    if (isThinking && isAtBottomRef.current) {
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          scrollToBottom();
        });
      });
    }
  }, [isThinking, scrollToBottom]);

  const handleScrollerRef = useCallback(
    (ref: HTMLElement | Window | null) => {
      scrollerRef.current = ref as HTMLElement;
    },
    [],
  );

  if (messages.length === 0) {
    return (
      <div className="flex-1 min-h-0 flex items-center justify-center text-txt-secondary text-sm font-mono opacity-50 overflow-hidden">
        <div className="text-center">
          <div className="text-lg mb-2">RadBot Terminal</div>
          <div className="text-xs">Type a message to begin...</div>
        </div>
      </div>
    );
  }

  return (
    <Virtuoso
      ref={virtuosoRef}
      scrollerRef={handleScrollerRef}
      data={messages}
      className="flex-1 min-h-0"
      initialTopMostItemIndex={messages.length - 1}
      atBottomThreshold={150}
      atBottomStateChange={(atBottom) => {
        isAtBottomRef.current = atBottom;
      }}
      computeItemKey={(_index, msg) => msg.id}
      itemContent={(_index, msg) => <ChatMessage message={msg} />}
      followOutput="smooth"
      components={{
        Footer: () => (isThinking ? <TypingIndicator /> : null),
      }}
      style={{
        scrollbarWidth: "thin",
        scrollbarColor: "#3584e4 #0e1419",
      }}
    />
  );
}
