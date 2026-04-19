interface Props {
  code: string;
  color?: string;
}

export default function RefCode({ code, color = "var(--sunset)" }: Props) {
  return (
    <span
      style={{
        fontFamily: "var(--p-mono)",
        fontSize: 10,
        fontWeight: 700,
        letterSpacing: "0.1em",
        color,
        padding: "1px 5px",
        borderRadius: 3,
        background: `color-mix(in oklch, ${color} 14%, transparent)`,
        border: `1px solid color-mix(in oklch, ${color} 30%, transparent)`,
      }}
    >
      {code}
    </span>
  );
}
