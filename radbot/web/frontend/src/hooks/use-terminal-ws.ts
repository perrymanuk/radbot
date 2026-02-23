import { useEffect, useRef, useCallback } from "react";
import type { Terminal } from "@xterm/xterm";

interface UseTerminalWSOptions {
  terminalId: string | null;
  terminal: Terminal | null;
  onClosed?: (exitCode: number) => void;
  onReady?: () => void;
}

export function useTerminalWS({
  terminalId,
  terminal,
  onClosed,
  onReady,
}: UseTerminalWSOptions) {
  const wsRef = useRef<WebSocket | null>(null);
  const terminalIdRef = useRef(terminalId);

  terminalIdRef.current = terminalId;

  const sendInput = useCallback((data: string) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "input", data }));
    }
  }, []);

  const sendResize = useCallback((cols: number, rows: number) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "resize", cols, rows }));
    }
  }, []);

  useEffect(() => {
    if (!terminalId || !terminal) return;

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host;
    const url = `${protocol}//${host}/ws/terminal/${terminalId}`;

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log("[Terminal WS] Connected to", terminalId);
      // Send initial size
      sendResize(terminal.cols, terminal.rows);
      onReady?.();
    };

    ws.onmessage = (evt) => {
      try {
        const msg = JSON.parse(evt.data);

        // Drop messages from stale connections
        if (terminalIdRef.current !== terminalId) return;

        switch (msg.type) {
          case "output":
            if (msg.data) {
              terminal.write(msg.data);
            }
            break;
          case "closed":
            onClosed?.(msg.exit_code ?? -1);
            break;
        }
      } catch (err) {
        console.error("[Terminal WS] Parse error:", err);
      }
    };

    ws.onclose = () => {
      console.log("[Terminal WS] Disconnected");
    };

    ws.onerror = (err) => {
      console.error("[Terminal WS] Error:", err);
    };

    // Wire terminal input to WebSocket
    const inputDisposable = terminal.onData((data: string) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "input", data }));
      }
    });

    return () => {
      inputDisposable.dispose();
      ws.onopen = null;
      ws.onclose = null;
      ws.onerror = null;
      ws.onmessage = null;
      if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
        ws.close();
      }
      wsRef.current = null;
    };
  }, [terminalId, terminal, onClosed, onReady, sendResize]);

  return { sendInput, sendResize };
}
