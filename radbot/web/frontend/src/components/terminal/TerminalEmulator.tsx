import { useEffect, useRef, useCallback, useState } from "react";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import { WebLinksAddon } from "@xterm/addon-web-links";
import { WebglAddon } from "@xterm/addon-webgl";
import { CanvasAddon } from "@xterm/addon-canvas";
import { Unicode11Addon } from "@xterm/addon-unicode11";
import "@xterm/xterm/css/xterm.css";
import { useTerminalWS } from "@/hooks/use-terminal-ws";

interface TerminalEmulatorProps {
  terminalId: string;
  onClosed?: (exitCode: number) => void;
  onSendInputRef?: (fn: (data: string) => void) => void;
}

export default function TerminalEmulator({ terminalId, onClosed, onSendInputRef }: TerminalEmulatorProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const terminalRef = useRef<Terminal | null>(null);
  const fitAddonRef = useRef<FitAddon | null>(null);
  const resizeTimerRef = useRef<ReturnType<typeof setTimeout>>();
  const [terminal, setTerminal] = useState<Terminal | null>(null);

  const { sendInput, sendResize } = useTerminalWS({
    terminalId,
    terminal,
    onClosed,
  });

  // Expose sendInput to parent
  useEffect(() => {
    onSendInputRef?.(sendInput);
  }, [sendInput, onSendInputRef]);

  // Create terminal instance
  useEffect(() => {
    if (!containerRef.current) return;
    let disposed = false;

    const term = new Terminal({
      cursorBlink: true,
      cursorStyle: "block",
      cursorInactiveStyle: "outline",
      fontSize: 14,
      fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', Menlo, Monaco, monospace",
      theme: {
        background: "#1a1a2e",
        foreground: "#e0e0e0",
        cursor: "#e94560",
        cursorAccent: "#1a1a2e",
        selectionBackground: "rgba(233, 69, 96, 0.3)",
        black: "#1a1a2e",
        red: "#e94560",
        green: "#33ff33",
        yellow: "#ffbf00",
        blue: "#0f3460",
        magenta: "#c678dd",
        cyan: "#56b6c2",
        white: "#e0e0e0",
        brightBlack: "#5c6370",
        brightRed: "#e06c75",
        brightGreen: "#98c379",
        brightYellow: "#e5c07b",
        brightBlue: "#61afef",
        brightMagenta: "#c678dd",
        brightCyan: "#56b6c2",
        brightWhite: "#ffffff",
      },
      scrollback: 50000,
      smoothScrollDuration: 0,
      convertEol: true,
      allowProposedApi: true,
    });

    const fitAddon = new FitAddon();
    const webLinksAddon = new WebLinksAddon();

    term.loadAddon(fitAddon);
    term.loadAddon(webLinksAddon);

    // Wait for fonts to load before opening to prevent column miscalculation
    const init = async () => {
      await document.fonts.ready;
      if (disposed) return;

      term.open(containerRef.current!);

      // GPU-accelerated renderer with fallback chain: WebGL → Canvas → DOM
      try {
        const webgl = new WebglAddon();
        webgl.onContextLoss(() => {
          webgl.dispose();
          try { term.loadAddon(new CanvasAddon()); } catch { /* fall back to DOM */ }
        });
        term.loadAddon(webgl);
      } catch {
        try { term.loadAddon(new CanvasAddon()); } catch { /* fall back to DOM */ }
      }

      // Unicode 11 for proper CJK/emoji character widths
      try {
        const unicode = new Unicode11Addon();
        term.loadAddon(unicode);
        term.unicode.activeVersion = "11";
      } catch { /* continue without unicode11 */ }

      // Initial fit
      try {
        fitAddon.fit();
      } catch {
        // Container may not be sized yet
      }

      terminalRef.current = term;
      fitAddonRef.current = fitAddon;
      setTerminal(term);
    };

    init();

    return () => {
      disposed = true;
      term.dispose();
      terminalRef.current = null;
      fitAddonRef.current = null;
      setTerminal(null);
    };
  }, []);

  // Debounced ResizeObserver for fit + sendResize (150ms debounce)
  const handleResize = useCallback(() => {
    clearTimeout(resizeTimerRef.current);
    resizeTimerRef.current = setTimeout(() => {
      if (fitAddonRef.current && terminalRef.current) {
        try {
          fitAddonRef.current.fit();
          sendResize(terminalRef.current.cols, terminalRef.current.rows);
        } catch {
          // Ignore fit errors during transitions
        }
      }
    }, 150);
  }, [sendResize]);

  useEffect(() => {
    if (!containerRef.current) return;

    const observer = new ResizeObserver(() => {
      handleResize();
    });
    observer.observe(containerRef.current);

    return () => {
      observer.disconnect();
      clearTimeout(resizeTimerRef.current);
    };
  }, [handleResize]);

  // Focus terminal on click
  const handleClick = useCallback(() => {
    terminalRef.current?.focus();
  }, []);

  return (
    <div
      ref={containerRef}
      className="w-full h-full"
      onClick={handleClick}
      style={{ padding: "4px" }}
    />
  );
}
