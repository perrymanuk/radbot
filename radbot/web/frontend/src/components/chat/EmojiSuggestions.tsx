import { useState, useEffect, useCallback } from "react";
import { cn } from "@/lib/utils";

interface EmojiData {
  shortcode: string;
  emoji: string;
  description: string;
}

const COMMON_EMOJIS: EmojiData[] = [
  { shortcode: ":hangloose:", emoji: "\u{1F919}", description: "Hang Loose / Shaka" },
  { shortcode: ":ok_hand:", emoji: "\u{1F44C}", description: "OK Hand" },
  { shortcode: ":wave:", emoji: "\u{1F44B}", description: "Waving Hand" },
  { shortcode: ":raised_hands:", emoji: "\u{1F64C}", description: "Raised Hands" },
  { shortcode: ":clap:", emoji: "\u{1F44F}", description: "Clapping Hands" },
  { shortcode: ":pray:", emoji: "\u{1F64F}", description: "Praying Hands" },
  { shortcode: ":metal:", emoji: "\u{1F918}", description: "Rock On" },
  { shortcode: ":punch:", emoji: "\u{1F44A}", description: "Fist Bump" },
  { shortcode: ":smile:", emoji: "\u{1F60A}", description: "Smile" },
  { shortcode: ":grin:", emoji: "\u{1F601}", description: "Grin" },
  { shortcode: ":joy:", emoji: "\u{1F602}", description: "Joy" },
  { shortcode: ":rofl:", emoji: "\u{1F923}", description: "ROFL" },
  { shortcode: ":wink:", emoji: "\u{1F609}", description: "Wink" },
  { shortcode: ":thinking:", emoji: "\u{1F914}", description: "Thinking" },
  { shortcode: ":sunglasses:", emoji: "\u{1F60E}", description: "Cool" },
  { shortcode: ":nerd_face:", emoji: "\u{1F913}", description: "Nerd Face" },
  { shortcode: ":heart:", emoji: "\u2764\uFE0F", description: "Heart" },
  { shortcode: ":+1:", emoji: "\u{1F44D}", description: "Thumbs Up" },
  { shortcode: ":-1:", emoji: "\u{1F44E}", description: "Thumbs Down" },
  { shortcode: ":tada:", emoji: "\u{1F389}", description: "Celebration" },
  { shortcode: ":rocket:", emoji: "\u{1F680}", description: "Rocket" },
  { shortcode: ":fire:", emoji: "\u{1F525}", description: "Fire" },
  { shortcode: ":boom:", emoji: "\u{1F4A5}", description: "Explosion" },
  { shortcode: ":star:", emoji: "\u2B50", description: "Star" },
  { shortcode: ":check:", emoji: "\u2705", description: "Check Mark" },
  { shortcode: ":x:", emoji: "\u274C", description: "Cross Mark" },
  { shortcode: ":warning:", emoji: "\u26A0\uFE0F", description: "Warning" },
  { shortcode: ":zap:", emoji: "\u26A1", description: "Lightning" },
  { shortcode: ":bulb:", emoji: "\u{1F4A1}", description: "Light Bulb" },
  { shortcode: ":computer:", emoji: "\u{1F4BB}", description: "Computer" },
  { shortcode: ":gear:", emoji: "\u2699\uFE0F", description: "Gear" },
  { shortcode: ":eyes:", emoji: "\u{1F440}", description: "Eyes" },
  { shortcode: ":brain:", emoji: "\u{1F9E0}", description: "Brain" },
  { shortcode: ":robot:", emoji: "\u{1F916}", description: "Robot" },
  { shortcode: ":bug:", emoji: "\u{1F41B}", description: "Bug" },
  { shortcode: ":lock:", emoji: "\u{1F512}", description: "Lock" },
  { shortcode: ":key:", emoji: "\u{1F511}", description: "Key" },
  { shortcode: ":mag:", emoji: "\u{1F50D}", description: "Magnifying Glass" },
  { shortcode: ":memo:", emoji: "\u{1F4DD}", description: "Memo" },
  { shortcode: ":book:", emoji: "\u{1F4DA}", description: "Books" },
];

interface Props {
  filter: string;
  onSelect: (shortcode: string) => void;
  onClose: () => void;
}

export default function EmojiSuggestions({ filter, onSelect, onClose }: Props) {
  const [activeIndex, setActiveIndex] = useState(-1);

  const filtered = COMMON_EMOJIS.filter((e) =>
    e.shortcode.slice(1, -1).toLowerCase().includes(filter.toLowerCase()),
  )
    .sort((a, b) => {
      const aCode = a.shortcode.slice(1, -1).toLowerCase();
      const bCode = b.shortcode.slice(1, -1).toLowerCase();
      const f = filter.toLowerCase();
      if (aCode === f) return -1;
      if (bCode === f) return 1;
      if (aCode.startsWith(f) && !bCode.startsWith(f)) return -1;
      if (!aCode.startsWith(f) && bCode.startsWith(f)) return 1;
      return aCode.localeCompare(bCode);
    })
    .slice(0, 8);

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
            onSelect(filtered[activeIndex].shortcode);
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

  useEffect(() => {
    setActiveIndex(-1);
  }, [filter]);

  if (filtered.length === 0) return null;

  return (
    <div className="absolute bottom-full left-0 w-[300px] max-h-[200px] overflow-y-auto bg-bg-tertiary border border-border z-10 mb-1 p-0">
      {filtered.map((emoji, i) => (
        <div
          key={emoji.shortcode}
          onClick={() => onSelect(emoji.shortcode)}
          className={cn(
            "px-2 py-1.5 flex items-center cursor-pointer transition-colors font-mono text-[0.85rem]",
            i === activeIndex && "bg-accent-blue/20",
          )}
        >
          <span className="inline-block w-5 text-center mr-2 text-[1.2em]">
            {emoji.emoji}
          </span>
          <span className="text-accent-blue mr-2">{emoji.shortcode}</span>
          <span className="text-txt-secondary text-[0.8em] ml-auto">
            {emoji.description}
          </span>
        </div>
      ))}
    </div>
  );
}
