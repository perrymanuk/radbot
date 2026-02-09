import { useEffect, useState } from "react";
import { useAppStore } from "@/stores/app-store";
import SessionItem from "./SessionItem";
import { useIsMobile } from "@/hooks/use-mobile";

export default function SessionsPanel() {
  const sessions = useAppStore((s) => s.sessions);
  const loadSessions = useAppStore((s) => s.loadSessions);
  const createNewSession = useAppStore((s) => s.createNewSession);
  const setActivePanel = useAppStore((s) => s.setActivePanel);
  const [search, setSearch] = useState("");
  const isMobile = useIsMobile();

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  const filtered = sessions.filter(
    (s) =>
      s.name?.toLowerCase().includes(search.toLowerCase()) ||
      s.id.toLowerCase().includes(search.toLowerCase()),
  );

  return (
    <div className="flex flex-col h-full bg-bg-primary">
      {/* Header */}
      <div className="px-2 py-1.5 bg-bg-tertiary border-b border-border flex items-center gap-2 min-h-[44px] md:min-h-0">
        {isMobile && (
          <button
            onClick={() => setActivePanel(null)}
            className="px-2 py-1 text-txt-secondary hover:text-txt-primary font-mono text-sm"
          >
            &larr;
          </button>
        )}
        <span className="text-accent-blue text-[0.9rem] font-mono flex-1">
          Sessions
        </span>
        <button
          onClick={() => createNewSession()}
          className="px-2 py-1 sm:py-0.5 border border-border bg-bg-tertiary text-txt-primary text-[0.7rem] font-mono uppercase tracking-wider hover:bg-accent-blue hover:text-bg-primary transition-all cursor-pointer min-h-[36px] sm:min-h-0"
        >
          + NEW
        </button>
      </div>

      {/* Search */}
      <div className="p-1.5 border-b border-border">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search sessions..."
          className="w-full bg-bg-secondary text-txt-primary border border-border px-2 py-1 font-mono text-[0.75rem] outline-none focus:border-accent-blue h-6"
        />
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto p-1">
        {filtered.length === 0 ? (
          <div className="p-4 text-center text-txt-secondary text-[0.75rem] italic">
            No sessions found
          </div>
        ) : (
          filtered.map((session) => (
            <SessionItem key={session.id} session={session} />
          ))
        )}
      </div>
    </div>
  );
}
