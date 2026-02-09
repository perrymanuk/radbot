import { useRef, useEffect } from "react";
import { Virtuoso, type VirtuosoHandle } from "react-virtuoso";
import { useAppStore } from "@/stores/app-store";
import ChatMessage from "./ChatMessage";

export default function MessageList() {
  const messages = useAppStore((s) => s.messages);
  const virtuosoRef = useRef<VirtuosoHandle>(null);
  const isAtBottomRef = useRef(true);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    if (isAtBottomRef.current && messages.length > 0) {
      // Small delay to let the DOM render
      requestAnimationFrame(() => {
        virtuosoRef.current?.scrollToIndex({
          index: messages.length - 1,
          behavior: "smooth",
          align: "end",
        });
      });
    }
  }, [messages.length]);

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
      data={messages}
      className="flex-1 min-h-0"
      followOutput="smooth"
      atBottomStateChange={(atBottom) => {
        isAtBottomRef.current = atBottom;
      }}
      itemContent={(index, msg) => (
        <ChatMessage key={msg.id ?? index} message={msg} />
      )}
      style={{
        scrollbarWidth: "thin",
        scrollbarColor: "#3584e4 #0e1419",
      }}
    />
  );
}
