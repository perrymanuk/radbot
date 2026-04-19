import type { ReactNode } from "react";
import PIcon from "./PIcon";

export function SectionLabel({
  children,
  color = "var(--text-dim)",
}: {
  children: ReactNode;
  color?: string;
}) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
      <span
        style={{
          fontFamily: "var(--p-mono)",
          fontSize: 9,
          fontWeight: 700,
          letterSpacing: "0.18em",
          color,
        }}
      >
        {children}
      </span>
      <span style={{ flex: 1, height: 1, background: "var(--border-soft)" }} />
    </div>
  );
}

export function MiniStat({
  label,
  value,
  color,
}: {
  label: string;
  value: ReactNode;
  color?: string;
}) {
  return (
    <span style={{ display: "inline-flex", alignItems: "baseline", gap: 5 }}>
      <span
        style={{
          fontSize: 9,
          fontWeight: 700,
          letterSpacing: "0.14em",
          color: "var(--text-dim)",
        }}
      >
        {label}
      </span>
      <span
        style={{
          fontFamily: "var(--p-mono)",
          fontSize: 12,
          fontWeight: 700,
          color: color || "var(--text)",
        }}
      >
        {value}
      </span>
    </span>
  );
}

export function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
      <span
        style={{
          width: 6,
          height: 6,
          borderRadius: "50%",
          background: color,
          boxShadow: `0 0 6px ${color}`,
        }}
      />
      <span>{label}</span>
    </span>
  );
}

export function Empty({ label, icon }: { label: string; icon: Parameters<typeof PIcon>[0]["name"] }) {
  return (
    <div
      style={{
        padding: "60px 24px",
        textAlign: "center",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 12,
      }}
    >
      <div
        style={{
          width: 48,
          height: 48,
          borderRadius: 10,
          background: "var(--surface)",
          border: "1px dashed var(--p-border)",
          color: "var(--text-dim)",
          display: "grid",
          placeItems: "center",
        }}
      >
        <PIcon name={icon} size={22} />
      </div>
      <div style={{ fontFamily: "var(--p-mono)", fontSize: 12, color: "var(--text-dim)" }}>
        {label}
      </div>
    </div>
  );
}
