import { useEffect, useRef, useCallback, useState } from "react";
import type { Terminal } from "@xterm/xterm";

/**
 * Binary WebSocket protocol for terminal I/O.
 *
 * Each frame is prefixed with a 1-byte type tag:
 *
 * Client -> Server:
 *   0x01 + raw UTF-8 bytes   (input)
 *   0x02 + uint16BE cols + uint16BE rows  (resize)
 *
 * Server -> Client:
 *   0x01 + raw PTY bytes     (output)
 *   0x03 + int32BE exit code  (closed)
 *   0x04                      (end of scrollback replay)
 */

const MSG_DATA = 0x01;
const MSG_RESIZE = 0x02;
const MSG_CLOSED = 0x03;
const MSG_REPLAY_END = 0x04;

const encoder = new TextEncoder();
const decoder = new TextDecoder();

export type ConnectionState = "connecting" | "connected" | "disconnected" | "reconnecting";

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
  const [connectionState, setConnectionState] = useState<ConnectionState>("disconnected");

  terminalIdRef.current = terminalId;

  const sendInput = useCallback((data: string) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      const payload = encoder.encode(data);
      const buf = new Uint8Array(1 + payload.length);
      buf[0] = MSG_DATA;
      buf.set(payload, 1);
      ws.send(buf.buffer);
    }
  }, []);

  const sendResize = useCallback((cols: number, rows: number) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      const buf = new ArrayBuffer(5);
      const view = new DataView(buf);
      view.setUint8(0, MSG_RESIZE);
      view.setUint16(1, cols, false); // big-endian
      view.setUint16(3, rows, false);
      ws.send(buf);
    }
  }, []);

  useEffect(() => {
    if (!terminalId || !terminal) return;

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host;
    const url = `${protocol}//${host}/ws/terminal/${terminalId}`;

    setConnectionState("connecting");

    const ws = new WebSocket(url);
    ws.binaryType = "arraybuffer";
    wsRef.current = ws;

    ws.onopen = () => {
      console.log("[Terminal WS] Connected to", terminalId);
      setConnectionState("connected");
      // Send initial size
      sendResize(terminal.cols, terminal.rows);
      onReady?.();
    };

    ws.onmessage = (evt) => {
      // Drop messages from stale connections
      if (terminalIdRef.current !== terminalId) return;

      if (evt.data instanceof ArrayBuffer) {
        const buf = new Uint8Array(evt.data);
        if (buf.length === 0) return;

        const type = buf[0];
        if (type === MSG_DATA) {
          terminal.write(decoder.decode(buf.subarray(1)));
        } else if (type === MSG_CLOSED) {
          const view = new DataView(evt.data);
          const exitCode = buf.length >= 5 ? view.getInt32(1, false) : -1;
          onClosed?.(exitCode);
        } else if (type === MSG_REPLAY_END) {
          // Write a visual divider marking end of scrollback replay
          terminal.write("\x1b[2m\x1b[36m──── reconnected ────\x1b[0m\r\n");
        }
      } else {
        // Fallback: handle text frames (legacy/transition)
        try {
          const msg = JSON.parse(evt.data);
          if (msg.type === "output" && msg.data) {
            terminal.write(msg.data);
          } else if (msg.type === "closed") {
            onClosed?.(msg.exit_code ?? -1);
          }
        } catch (err) {
          console.error("[Terminal WS] Parse error:", err);
        }
      }
    };

    ws.onclose = () => {
      console.log("[Terminal WS] Disconnected");
      setConnectionState("disconnected");
    };

    ws.onerror = (err) => {
      console.error("[Terminal WS] Error:", err);
      setConnectionState("disconnected");
    };

    // Wire terminal input to WebSocket
    const inputDisposable = terminal.onData((data: string) => {
      if (ws.readyState === WebSocket.OPEN) {
        const payload = encoder.encode(data);
        const buf = new Uint8Array(1 + payload.length);
        buf[0] = MSG_DATA;
        buf.set(payload, 1);
        ws.send(buf.buffer);
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
      setConnectionState("disconnected");
    };
  }, [terminalId, terminal, onClosed, onReady, sendResize]);

  return { sendInput, sendResize, connectionState };
}
