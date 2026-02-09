import { useAppStore } from "@/stores/app-store";
import { cn } from "@/lib/utils";
import type { Session } from "@/types";

interface Props {
  session: Session;
}

export default function SessionItem({ session }: Props) {
  const currentSessionId = useAppStore((s) => s.sessionId);
  const switchSession = useAppStore((s) => s.switchSession);
  const isActive = session.id === currentSessionId;

  return (
    <div
      onClick={() => switchSession(session.id)}
      className={cn(
        "px-2 py-1.5 mb-0.5 border border-border bg-bg-secondary text-[0.75rem] cursor-pointer transition-all",
        "hover:border-accent-blue hover:bg-bg-tertiary",
        isActive && "border-accent-blue bg-bg-tertiary shadow-[0_0_0_1px_#3584e4]",
      )}
    >
      <div className="flex items-center gap-2">
        {isActive && (
          <span className="w-2 h-2 rounded-full bg-terminal-green shadow-[0_0_5px_rgba(51,255,51,0.4)]" />
        )}
        <span className="text-txt-primary flex-1 truncate font-mono">
          {session.name || `Session ${session.id.slice(0, 8)}`}
        </span>
      </div>
      <div className="text-txt-secondary text-[0.65rem] mt-0.5 truncate">
        {session.id.slice(0, 12)}...
        {session.preview && (
          <span className="ml-2 italic">{session.preview}</span>
        )}
      </div>
    </div>
  );
}
