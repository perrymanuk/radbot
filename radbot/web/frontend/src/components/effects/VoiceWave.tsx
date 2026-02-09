import { useEffect, useRef } from "react";

interface Props {
  active: boolean;
  barCount?: number;
}

export default function VoiceWave({ active, barCount = 40 }: Props) {
  const barsRef = useRef<HTMLDivElement>(null);
  const animRef = useRef<number>(0);

  useEffect(() => {
    if (!active || !barsRef.current) {
      if (animRef.current) cancelAnimationFrame(animRef.current);
      return;
    }

    const bars = barsRef.current.children;

    const animate = () => {
      for (let i = 0; i < bars.length; i++) {
        const bar = bars[i] as HTMLElement;
        const height = 4 + Math.random() * 8;
        bar.style.height = `${height}px`;
      }
      animRef.current = requestAnimationFrame(animate);
    };

    animRef.current = requestAnimationFrame(animate);

    return () => {
      cancelAnimationFrame(animRef.current);
    };
  }, [active]);

  if (!active) return null;

  return (
    <div
      ref={barsRef}
      className="relative h-4 w-[140px] overflow-hidden flex items-center gap-0.5 ml-2"
    >
      {Array.from({ length: barCount }).map((_, i) => (
        <span
          key={i}
          className="inline-block w-0.5 h-3 bg-accent-blue rounded-[1px] shadow-[0_0_3px_#3584e4,0_0_5px_rgba(53,132,228,0.3)] transition-[height] duration-300"
        />
      ))}
    </div>
  );
}
