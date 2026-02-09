import { useEffect, useRef, useCallback } from "react";
import { useAppStore } from "@/stores/app-store";
import { uuid } from "@/lib/utils";
import type { Message, AgentEvent } from "@/types";

const HEARTBEAT_INTERVAL = 90_000; // 90s
const MAX_MISSED_HEARTBEATS = 8;
const INITIAL_RECONNECT_DELAY = 1_000;
const MAX_RECONNECT_DELAY = 30_000;

export function useWebSocket(sessionId: string | null) {
  const wsRef = useRef<WebSocket | null>(null);
  const heartbeatRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const missedHeartbeatsRef = useRef(0);
  const reconnectDelayRef = useRef(INITIAL_RECONNECT_DELAY);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const messageQueueRef = useRef<string[]>([]);
  const isConnectedRef = useRef(false);

  const setConnectionStatus = useAppStore((s) => s.setConnectionStatus);
  const addMessage = useAppStore((s) => s.addMessage);
  const setMessages = useAppStore((s) => s.setMessages);
  const addEvents = useAppStore((s) => s.addEvents);

  const cleanup = useCallback(() => {
    if (heartbeatRef.current) {
      clearInterval(heartbeatRef.current);
      heartbeatRef.current = null;
    }
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    if (wsRef.current) {
      wsRef.current.onopen = null;
      wsRef.current.onclose = null;
      wsRef.current.onerror = null;
      wsRef.current.onmessage = null;
      if (
        wsRef.current.readyState === WebSocket.OPEN ||
        wsRef.current.readyState === WebSocket.CONNECTING
      ) {
        wsRef.current.close();
      }
      wsRef.current = null;
    }
    isConnectedRef.current = false;
  }, []);

  const flushQueue = useCallback(() => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    while (messageQueueRef.current.length > 0) {
      const msg = messageQueueRef.current.shift()!;
      wsRef.current.send(msg);
    }
  }, []);

  const startHeartbeat = useCallback(() => {
    if (heartbeatRef.current) clearInterval(heartbeatRef.current);
    missedHeartbeatsRef.current = 0;

    heartbeatRef.current = setInterval(() => {
      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;

      missedHeartbeatsRef.current++;
      if (missedHeartbeatsRef.current >= MAX_MISSED_HEARTBEATS) {
        console.warn("[WS] Too many missed heartbeats, reconnecting...");
        wsRef.current.close();
        return;
      }

      wsRef.current.send(JSON.stringify({ type: "heartbeat" }));
    }, HEARTBEAT_INTERVAL);
  }, []);

  const connect = useCallback(
    (sid: string) => {
      cleanup();
      setConnectionStatus("connecting");

      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const host = window.location.host;
      const url = `${protocol}//${host}/ws/${sid}`;

      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log("[WS] Connected to", sid);
        isConnectedRef.current = true;
        reconnectDelayRef.current = INITIAL_RECONNECT_DELAY;
        setConnectionStatus("active");
        startHeartbeat();
        flushQueue();

        // Request history
        ws.send(
          JSON.stringify({ type: "history_request", limit: 50 }),
        );
      };

      ws.onmessage = (evt) => {
        try {
          const data = JSON.parse(evt.data);

          switch (data.type) {
            case "heartbeat":
              missedHeartbeatsRef.current = 0;
              break;

            case "status":
              if (data.content === "thinking") {
                setConnectionStatus("thinking");
              } else if (
                data.content === "ready" ||
                data.content === "reset"
              ) {
                setConnectionStatus("active");
              } else if (
                typeof data.content === "string" &&
                data.content.startsWith("error")
              ) {
                setConnectionStatus("error");
                addMessage({
                  id: uuid(),
                  role: "system",
                  content: data.content,
                  timestamp: Date.now(),
                });
              }
              break;

            case "message":
              if (typeof data.content === "string") {
                addMessage({
                  id: uuid(),
                  role: data.role === "system" ? "system" : "assistant",
                  content: data.content,
                  timestamp: Date.now(),
                });
              }
              break;

            case "events":
              if (Array.isArray(data.content)) {
                const events = data.content as AgentEvent[];
                addEvents(events);

                // Extract final model response as chat message
                const finalResponse = events.find(
                  (e) =>
                    (e.type === "model_response" && e.is_final) ||
                    e.category === "model_response",
                );
                if (finalResponse?.text) {
                  addMessage({
                    id: uuid(),
                    role: "assistant",
                    content: finalResponse.text,
                    timestamp: Date.now(),
                    agent: finalResponse.agent_name,
                  });
                }
              }
              break;

            case "history":
              if (Array.isArray(data.messages)) {
                setMessages(data.messages as Message[]);
              }
              break;

            case "sync_response":
              if (Array.isArray(data.messages)) {
                const current = useAppStore.getState().messages;
                const newMsgs = (data.messages as Message[]).filter(
                  (m) => !current.some((c) => c.id === m.id),
                );
                if (newMsgs.length > 0) {
                  useAppStore.setState({
                    messages: [...current, ...newMsgs],
                  });
                }
              }
              break;
          }
        } catch (err) {
          console.error("[WS] Message parse error:", err);
        }
      };

      ws.onclose = () => {
        console.log("[WS] Disconnected");
        isConnectedRef.current = false;
        if (heartbeatRef.current) {
          clearInterval(heartbeatRef.current);
          heartbeatRef.current = null;
        }

        setConnectionStatus("reconnecting");

        // Exponential backoff reconnect
        const delay = reconnectDelayRef.current;
        reconnectDelayRef.current = Math.min(
          delay * 2,
          MAX_RECONNECT_DELAY,
        );

        reconnectTimerRef.current = setTimeout(() => {
          const currentSession = useAppStore.getState().sessionId;
          if (currentSession) connect(currentSession);
        }, delay);
      };

      ws.onerror = (err) => {
        console.error("[WS] Error:", err);
      };
    },
    [
      cleanup,
      setConnectionStatus,
      addMessage,
      setMessages,
      addEvents,
      startHeartbeat,
      flushQueue,
    ],
  );

  // Send a chat message via WebSocket
  const sendMessage = useCallback(
    (text: string) => {
      const msg = JSON.stringify({ message: text });
      if (
        wsRef.current &&
        wsRef.current.readyState === WebSocket.OPEN
      ) {
        wsRef.current.send(msg);
      } else {
        messageQueueRef.current.push(msg);
      }
    },
    [],
  );

  // Expose sendMessage globally for components to use
  useEffect(() => {
    (window as unknown as Record<string, unknown>).__wsSend = sendMessage;
    return () => {
      delete (window as unknown as Record<string, unknown>).__wsSend;
    };
  }, [sendMessage]);

  // Connect when sessionId changes
  useEffect(() => {
    if (sessionId) {
      connect(sessionId);
    }
    return cleanup;
  }, [sessionId, connect, cleanup]);

  return { sendMessage };
}

// Helper to send message from anywhere
export function wsSend(text: string) {
  const fn = (window as unknown as Record<string, (t: string) => void>)
    .__wsSend;
  if (fn) fn(text);
}
