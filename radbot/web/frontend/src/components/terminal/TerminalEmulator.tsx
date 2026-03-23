import { useEffect, useRef, useCallback, useState } from "react";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import { WebLinksAddon } from "@xterm/addon-web-links";
import { WebglAddon } from "@xterm/addon-webgl";
import { CanvasAddon } from "@xterm/addon-canvas";
import { Unicode11Addon } from "@xterm/addon-unicode11";
import { SearchAddon } from "@xterm/addon-search";
import "@xterm/xterm/css/xterm.css";
import { useTerminalWS } from "@/hooks/use-terminal-ws";
import type { ConnectionState } from "@/hooks/use-terminal-ws";

interface TerminalEmulatorProps {
  terminalId: string;
  onClosed?: (exitCode: number) => void;
  onSendInputRef?: (fn: (data: string) => void) => void;
  onConnectionStateChange?: (state: ConnectionState) => void;
}

export default function TerminalEmulator({ terminalId, onClosed, onSendInputRef, onConnectionStateChange }: TerminalEmulatorProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const terminalRef = useRef<Terminal | null>(null);
  const fitAddonRef = useRef<FitAddon | null>(null);
  const searchAddonRef = useRef<SearchAddon | null>(null);
  const resizeTimerRef = useRef<ReturnType<typeof setTimeout>>();
  const [terminal, setTerminal] = useState<Terminal | null>(null);
  const [searchVisible, setSearchVisible] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [fontSize, setFontSize] = useState(14);
  const searchInputRef = useRef<HTMLInputElement>(null);

  const { sendInput, sendResize, connectionState } = useTerminalWS({
    terminalId,
    terminal,
    onClosed,
  });

  // Notify parent of connection state changes
  useEffect(() => {
    onConnectionStateChange?.(connectionState);
  }, [connectionState, onConnectionStateChange]);

  // Expose sendInput to parent
  useEffect(() => {
    onSendInputRef?.(sendInput);
  }, [sendInput, onSendInputRef]);

  // Handle font size changes
  useEffect(() => {
    if (terminalRef.current && fitAddonRef.current) {
      terminalRef.current.options.fontSize = fontSize;
      try {
        fitAddonRef.current.fit();
      } catch {
        // Ignore fit errors
      }
    }
  }, [fontSize]);

  // Create terminal instance
  useEffect(() => {
    if (!containerRef.current) return;
    let disposed = false;

    const term = new Terminal({
      cursorBlink: true,
      cursorStyle: "block",
      cursorInactiveStyle: "outline",
      fontSize,
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
    const searchAddon = new SearchAddon();

    term.loadAddon(fitAddon);
    term.loadAddon(webLinksAddon);
    term.loadAddon(searchAddon);
    searchAddonRef.current = searchAddon;

    // Wait for fonts to load before opening to prevent column miscalculation
    const init = async () => {
      await document.fonts.ready;
      if (disposed) return;

      term.open(containerRef.current!);

      // GPU-accelerated renderer with fallback chain: WebGL -> Canvas -> DOM
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
      searchAddonRef.current = null;
      setTerminal(null);
    };
  }, []);

  // Keyboard shortcuts (page-level, not terminal-level)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Ctrl+Shift+F: toggle search
      if (e.ctrlKey && e.shiftKey && e.key === "F") {
        e.preventDefault();
        setSearchVisible((v) => {
          if (!v) {
            setTimeout(() => searchInputRef.current?.focus(), 50);
          }
          return !v;
        });
        return;
      }
      // Ctrl+= / Ctrl+Shift+=: increase font size
      if (e.ctrlKey && (e.key === "=" || e.key === "+")) {
        e.preventDefault();
        setFontSize((s) => Math.min(s + 1, 24));
        return;
      }
      // Ctrl+-: decrease font size
      if (e.ctrlKey && e.key === "-") {
        e.preventDefault();
        setFontSize((s) => Math.max(s - 1, 10));
        return;
      }
      // Ctrl+0: reset font size
      if (e.ctrlKey && e.key === "0") {
        e.preventDefault();
        setFontSize(14);
        return;
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  // Search functionality
  const handleSearch = useCallback((query: string, direction: "next" | "prev" = "next") => {
    if (!searchAddonRef.current) return;
    if (!query) return;
    if (direction === "next") {
      searchAddonRef.current.findNext(query, { regex: false, caseSensitive: false });
    } else {
      searchAddonRef.current.findPrevious(query, { regex: false, caseSensitive: false });
    }
  }, []);

  const closeSearch = useCallback(() => {
    setSearchVisible(false);
    setSearchQuery("");
    searchAddonRef.current?.clearDecorations();
    terminalRef.current?.focus();
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
    <div className="relative w-full h-full">
      {/* Connection state banner */}
      {(connectionState === "disconnected" || connectionState === "reconnecting") && (
        <div className="absolute top-0 left-0 right-0 z-20 bg-bg-tertiary/90 border-b border-terminal-amber text-terminal-amber text-xs font-mono text-center py-1.5 transition-opacity">
          {connectionState === "reconnecting" ? "Reconnecting..." : "Disconnected"}
        </div>
      )}
      {connectionState === "connecting" && (
        <div className="absolute top-0 left-0 right-0 z-20 bg-bg-tertiary/90 border-b border-accent-blue text-accent-blue text-xs font-mono text-center py-1.5 transition-opacity">
          Connecting...
        </div>
      )}

      {/* Search bar */}
      {searchVisible && (
        <div className="absolute top-1 right-1 z-20 flex items-center gap-1 bg-bg-tertiary border border-border rounded px-2 py-1 shadow-lg">
          <input
            ref={searchInputRef}
            type="text"
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              if (e.target.value) handleSearch(e.target.value);
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                if (e.shiftKey) {
                  handleSearch(searchQuery, "prev");
                } else {
                  handleSearch(searchQuery, "next");
                }
              }
              if (e.key === "Escape") {
                closeSearch();
              }
            }}
            placeholder="Search..."
            className="bg-bg-secondary text-txt-primary border-none outline-none font-mono text-xs w-48 px-1 py-0.5"
            autoFocus
          />
          <button
            onClick={() => handleSearch(searchQuery, "prev")}
            className="text-txt-secondary hover:text-txt-primary text-xs font-mono px-1"
            title="Previous (Shift+Enter)"
          >
            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" /></svg>
          </button>
          <button
            onClick={() => handleSearch(searchQuery, "next")}
            className="text-txt-secondary hover:text-txt-primary text-xs font-mono px-1"
            title="Next (Enter)"
          >
            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg>
          </button>
          <button
            onClick={closeSearch}
            className="text-txt-secondary hover:text-txt-primary text-xs font-mono px-1"
            title="Close (Escape)"
          >
            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>
      )}

      <div
        ref={containerRef}
        className="w-full h-full"
        onClick={handleClick}
        style={{ padding: "4px" }}
      />
    </div>
  );
}
