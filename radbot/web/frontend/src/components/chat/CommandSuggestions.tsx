import { useState, useEffect, useCallback } from "react";
import { cn } from "@/lib/utils";

interface Command {
  name: string;
  description: string;
}

interface Props {
  filter: string;
  commands: Command[];
  onSelect: (name: string) => void;
  onClose: () => void;
}

export default function CommandSuggestions({
  filter,
  commands,
  onSelect,
  onClose,
}: Props) {
  const [activeIndex, setActiveIndex] = useState(-1);

  const filtered = commands.filter((c) =>
    c.name.startsWith(filter.toLowerCase()),
  );

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (filtered.length === 0) return;

      switch (e.key) {
        case "ArrowDown":
          e.preventDefault();
          setActiveIndex((i) => (i + 1) % filtered.length);
          break;
        case "ArrowUp":
          e.preventDefault();
          setActiveIndex((i) =>
            (i - 1 + filtered.length) % filtered.length,
          );
          break;
        case "Tab":
        case "Enter":
          if (activeIndex >= 0) {
            e.preventDefault();
            onSelect(filtered[activeIndex].name);
          } else if (filtered.length === 1) {
            e.preventDefault();
            onSelect(filtered[0].name);
          }
          break;
        case "Escape":
          e.preventDefault();
          onClose();
          break;
      }
    },
    [filtered, activeIndex, onSelect, onClose],
  );

  useEffect(() => {
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);

  // Reset index when filter changes
  useEffect(() => {
    setActiveIndex(-1);
  }, [filter]);

  if (filtered.length === 0) return null;

  return (
    <div className="absolute bottom-full left-0 w-full max-h-[200px] overflow-y-auto bg-bg-tertiary border border-border z-[100] mb-1">
      {filtered.map((cmd, i) => (
        <div
          key={cmd.name}
          onClick={() => onSelect(cmd.name)}
          className={cn(
            "px-3 py-2 cursor-pointer flex items-center transition-colors",
            i === activeIndex && "bg-accent-blue/20",
          )}
        >
          <span className="text-accent-blue font-bold mr-3">{cmd.name}</span>
          <span className="text-txt-secondary text-[0.9em]">
            {cmd.description}
          </span>
        </div>
      ))}
    </div>
  );
}
