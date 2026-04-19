interface Props {
  pct: number;
  color?: string;
  height?: number;
}

export default function ProgressBar({ pct, color = "var(--sunset)", height = 4 }: Props) {
  return (
    <div
      style={{
        height,
        borderRadius: 3,
        overflow: "hidden",
        background: "var(--bg-sunk)",
        border: "1px solid var(--border-soft)",
      }}
    >
      <div
        style={{
          width: `${Math.max(0, Math.min(100, pct))}%`,
          height: "100%",
          background: `linear-gradient(90deg, ${color}, color-mix(in oklch, ${color} 55%, var(--magenta)))`,
          boxShadow: `0 0 8px -2px ${color}`,
        }}
      />
    </div>
  );
}
