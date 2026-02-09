import { useRef, useEffect, useCallback } from "react";
import { Virtuoso, type VirtuosoHandle } from "react-virtuoso";
import { useAppStore } from "@/stores/app-store";
import ChatMessage from "./ChatMessage";

export default function MessageList() {
  const messages = useAppStore((s) => s.messages);
  const virtuosoRef = useRef<VirtuosoHandle>(null);
  const scrollerRef = useRef<HTMLElement | null>(null);
  const isAtBottomRef = useRef(true);

  const scrollToBottom = useCallback(() => {
    if (scrollerRef.current) {
      // Set scrollTop directly on the DOM element — the browser clamps
      // to (scrollHeight − clientHeight), which is the true bottom
      // regardless of Virtuoso's internal height estimates.
      scrollerRef.current.scrollTop = scrollerRef.current.scrollHeight;
    }
  }, []);

  // Scroll to bottom when new messages arrive (if user is at bottom)
  useEffect(() => {
    if (messages.length > 0 && isAtBottomRef.current) {
      // Double-rAF: first lets React commit, second lets Virtuoso
      // render + measure the new item so scrollHeight is accurate.
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          scrollToBottom();
        });
      });
    }
  }, [messages.length, scrollToBottom]);

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
      style={{
        scrollbarWidth: "thin",
        scrollbarColor: "#3584e4 #0e1419",
      }}
    />
  );
}
