import { useEffect } from "react";
import { useAppStore } from "@/stores/app-store";
import { useWebSocket } from "@/hooks/use-websocket";
import AppLayout from "@/components/layout/AppLayout";
import MatrixBackground from "@/components/effects/MatrixBackground";

export default function ChatPage() {
  const sessionId = useAppStore((s) => s.sessionId);
  const initSession = useAppStore((s) => s.initSession);

  useEffect(() => {
    initSession();
  }, [initSession]);

  // Connect WebSocket once we have a session
  useWebSocket(sessionId);

  return (
    <>
      <MatrixBackground />
      <AppLayout />
    </>
  );
}
