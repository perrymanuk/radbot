import { useEffect, useRef } from "react";
import { useAppStore } from "@/stores/app-store";
import { useWebSocket } from "@/hooks/use-websocket";
import { useTTS } from "@/hooks/use-tts";
import AppLayout from "@/components/layout/AppLayout";
import MatrixBackground from "@/components/effects/MatrixBackground";

export default function ChatPage() {
  const sessionId = useAppStore((s) => s.sessionId);
  const initSession = useAppStore((s) => s.initSession);
  const messages = useAppStore((s) => s.messages);
  const { speak } = useTTS();

  // Track message count to detect new assistant messages for auto-play TTS
  const lastMsgCountRef = useRef(0);
  const historyLoadedRef = useRef(false);

  useEffect(() => {
    initSession();
  }, [initSession]);

  // Connect WebSocket once we have a session
  useWebSocket(sessionId);

  // Auto-play TTS for new assistant messages
  useEffect(() => {
    const count = messages.length;

    if (count === 0) {
      // Messages cleared (session switch or /clear)
      lastMsgCountRef.current = 0;
      historyLoadedRef.current = false;
      return;
    }

    if (!historyLoadedRef.current) {
      // First batch of messages (history load) — skip TTS
      lastMsgCountRef.current = count;
      historyLoadedRef.current = true;
      return;
    }

    // New messages added after history
    if (count > lastMsgCountRef.current) {
      const autoPlay = localStorage.getItem("radbot_tts_autoplay") === "true";
      if (autoPlay) {
        for (let i = lastMsgCountRef.current; i < count; i++) {
          if (messages[i].role === "assistant") {
            speak(messages[i].content);
          }
        }
      }
    }

    lastMsgCountRef.current = count;
  }, [messages, speak]);

  return (
    <>
      <MatrixBackground />
      <AppLayout />
    </>
  );
}
