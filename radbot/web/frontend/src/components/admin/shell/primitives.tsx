import type { CSSProperties, ReactNode } from "react";
import { AIcon, type AIconName } from "./icons";

export type PanelStatus = "connected" | "configured" | "disconnected" | "error" | "neutral";

export function StatusDot({ status, size = 7 }: { status: PanelStatus; size?: number }) {
  const colors: Record<PanelStatus, string> = {
    connected: "var(--crt)",
    configured: "var(--crt)",
    disconnected: "var(--text-dim)",
    error: "var(--magenta)",
    neutral: "var(--text-dim)",
  };
  const c = colors[status] ?? colors.neutral;
  return (
    <span
      style={{
        width: size,
        height: size,
        borderRadius: "50%",
        background: c,
        boxShadow: status === "connected" || status === "configured" ? `0 0 6px ${c}` : "none",
        flex: "none",
        display: "inline-block",
      }}
    />
  );
}

export function StatusPill({ status, label }: { status: PanelStatus; label?: string }) {
  const cfg: Record<PanelStatus, { c: string; label: string }> = {
    connected: { c: "var(--crt)", label: label || "CONNECTED" },
    configured: { c: "var(--crt)", label: label || "CONFIGURED" },
    disconnected: { c: "var(--text-dim)", label: label || "DISCONNECTED" },
    error: { c: "var(--magenta)", label: label || "ERROR" },
    neutral: { c: "var(--text-dim)", label: label || "—" },
  };
  const s = cfg[status] ?? cfg.neutral;
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 5,
        padding: "2px 7px",
        borderRadius: 3,
        fontFamily: "var(--mono)",
        fontSize: 9,
        fontWeight: 700,
        letterSpacing: "0.12em",
        color: s.c,
        background: `color-mix(in oklch, ${s.c} 12%, transparent)`,
        border: `1px solid color-mix(in oklch, ${s.c} 30%, transparent)`,
      }}
    >
      <StatusDot status={status} size={5} />
      {s.label}
    </span>
  );
}

interface SectionCardProps {
  title?: string;
  accent?: string;
  right?: ReactNode;
  children: ReactNode;
  padding?: string;
  noHeader?: boolean;
  className?: string;
}

export function SectionCard({
  title,
  accent = "var(--sunset)",
  right,
  children,
  padding = "16px 18px",
  noHeader,
  className,
}: SectionCardProps) {
  return (
    <div
      className={className}
      style={{
        background: "var(--surface)",
        border: "1px solid var(--border)",
        borderRadius: 10,
        overflow: "hidden",
      }}
    >
      {!noHeader && title && (
        <div
          style={{
            padding: "11px 18px",
            display: "flex",
            alignItems: "center",
            gap: 10,
            borderBottom: "1px solid var(--border-soft)",
            background: `color-mix(in oklch, ${accent} 4%, var(--surface-2))`,
          }}
        >
          <span
            style={{
              fontFamily: "var(--mono)",
              fontSize: 11,
              fontWeight: 700,
              letterSpacing: "0.14em",
              color: accent,
              textTransform: "uppercase",
            }}
          >
            {title}
          </span>
          <span style={{ flex: 1 }} />
          {right}
        </div>
      )}
      <div style={{ padding }}>{children}</div>
    </div>
  );
}

interface FieldProps {
  label: string;
  hint?: ReactNode;
  children: ReactNode;
  span?: number;
}

export function Field({ label, hint, children, span = 1 }: FieldProps) {
  return (
    <label
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 6,
        gridColumn: `span ${span}`,
      }}
    >
      <span
        style={{
          fontFamily: "var(--mono)",
          fontSize: 10,
          fontWeight: 600,
          letterSpacing: "0.08em",
          color: "var(--text-mute)",
          textTransform: "uppercase",
        }}
      >
        {label}
      </span>
      {children}
      {hint && <span style={{ fontSize: 11, color: "var(--text-dim)", lineHeight: 1.4 }}>{hint}</span>}
    </label>
  );
}

const inputBase: CSSProperties = {
  padding: "8px 11px",
  borderRadius: 6,
  background: "var(--bg-sunk)",
  border: "1px solid var(--border)",
  color: "var(--text)",
  fontSize: 13,
  width: "100%",
  outline: "none",
};

interface TextInputProps {
  value: string | number | undefined;
  onChange?: (v: string) => void;
  placeholder?: string;
  mono?: boolean;
  type?: "text" | "password" | "number" | "email";
  readOnly?: boolean;
  list?: string;
  disabled?: boolean;
}

export function TextInput({
  value,
  onChange,
  placeholder,
  mono,
  type = "text",
  readOnly,
  list,
  disabled,
}: TextInputProps) {
  return (
    <input
      type={type}
      value={value ?? ""}
      onChange={(e) => onChange?.(e.target.value)}
      placeholder={placeholder}
      readOnly={readOnly}
      disabled={disabled}
      list={list}
      style={{
        ...inputBase,
        fontFamily: mono ? "var(--mono)" : "var(--sans)",
        opacity: disabled || readOnly ? 0.7 : 1,
      }}
    />
  );
}

interface TextAreaProps {
  value: string | undefined;
  onChange?: (v: string) => void;
  placeholder?: string;
  rows?: number;
  mono?: boolean;
}

export function TextArea({ value, onChange, placeholder, rows = 4, mono = true }: TextAreaProps) {
  return (
    <textarea
      value={value ?? ""}
      onChange={(e) => onChange?.(e.target.value)}
      placeholder={placeholder}
      rows={rows}
      style={{
        ...inputBase,
        padding: "10px 12px",
        fontFamily: mono ? "var(--mono)" : "var(--sans)",
        fontSize: 12,
        lineHeight: 1.5,
        resize: "vertical",
      }}
    />
  );
}

type SelectOption = string | { value: string; label: string };

interface SelectProps {
  value: string | undefined;
  onChange?: (v: string) => void;
  options: SelectOption[];
  disabled?: boolean;
}

export function Select({ value, onChange, options, disabled }: SelectProps) {
  return (
    <select
      value={value ?? ""}
      onChange={(e) => onChange?.(e.target.value)}
      disabled={disabled}
      style={{
        ...inputBase,
        fontFamily: "var(--mono)",
        fontSize: 12,
        appearance: "none",
        backgroundImage:
          "linear-gradient(45deg, transparent 50%, var(--text-dim) 50%)," +
          "linear-gradient(135deg, var(--text-dim) 50%, transparent 50%)",
        backgroundPosition: "calc(100% - 14px) 50%, calc(100% - 10px) 50%",
        backgroundSize: "4px 4px, 4px 4px",
        backgroundRepeat: "no-repeat",
        paddingRight: 28,
        cursor: disabled ? "not-allowed" : "pointer",
      }}
    >
      {options.map((o) =>
        typeof o === "string" ? (
          <option key={o} value={o}>
            {o}
          </option>
        ) : (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ),
      )}
    </select>
  );
}

interface ToggleProps {
  value: boolean;
  onChange?: (v: boolean) => void;
  label?: string;
}

export function Toggle({ value, onChange, label }: ToggleProps) {
  return (
    <button
      type="button"
      onClick={() => onChange?.(!value)}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 8,
        padding: "6px 10px 6px 6px",
        borderRadius: 22,
        background: value
          ? "color-mix(in oklch, var(--sunset) 18%, var(--bg-sunk))"
          : "var(--bg-sunk)",
        border: `1px solid ${value ? "var(--sunset)" : "var(--border)"}`,
        transition: "all 120ms",
        cursor: "pointer",
      }}
    >
      <span
        style={{
          position: "relative",
          width: 26,
          height: 14,
          borderRadius: 7,
          background: value ? "var(--sunset)" : "var(--border)",
          boxShadow: value
            ? "0 0 10px color-mix(in oklch, var(--sunset) 55%, transparent)"
            : "none",
          transition: "all 120ms",
          display: "inline-block",
        }}
      >
        <span
          style={{
            position: "absolute",
            top: 1,
            left: value ? 13 : 1,
            width: 12,
            height: 12,
            borderRadius: "50%",
            background: "var(--bg)",
            transition: "left 140ms",
          }}
        />
      </span>
      {label && (
        <span
          style={{
            fontFamily: "var(--mono)",
            fontSize: 11,
            fontWeight: 600,
            letterSpacing: "0.06em",
            color: value ? "var(--sunset)" : "var(--text-mute)",
            textTransform: "uppercase",
          }}
        >
          {label}
        </span>
      )}
    </button>
  );
}

interface ButtonProps {
  children: ReactNode;
  variant?: "primary" | "default" | "ghost" | "danger";
  size?: "sm" | "md" | "lg";
  icon?: AIconName;
  onClick?: () => void;
  disabled?: boolean;
  type?: "button" | "submit";
}

export function Button({
  children,
  variant = "default",
  size = "md",
  icon,
  onClick,
  disabled,
  type = "button",
}: ButtonProps) {
  const sizes = {
    sm: { padding: "5px 9px", fontSize: 10 },
    md: { padding: "7px 12px", fontSize: 11 },
    lg: { padding: "9px 16px", fontSize: 12 },
  }[size];
  const variants: Record<NonNullable<ButtonProps["variant"]>, CSSProperties> = {
    primary: {
      color: "var(--bg)",
      background: "var(--sunset)",
      border: "1px solid var(--sunset)",
      boxShadow: "0 0 16px -4px color-mix(in oklch, var(--sunset) 50%, transparent)",
    },
    default: {
      color: "var(--text)",
      background: "var(--surface)",
      border: "1px solid var(--border)",
    },
    ghost: {
      color: "var(--text-mute)",
      background: "transparent",
      border: "1px solid transparent",
    },
    danger: {
      color: "var(--magenta)",
      background: "color-mix(in oklch, var(--magenta) 12%, transparent)",
      border: "1px solid color-mix(in oklch, var(--magenta) 40%, transparent)",
    },
  };
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        borderRadius: 5,
        fontFamily: "var(--mono)",
        fontWeight: 700,
        letterSpacing: "0.08em",
        textTransform: "uppercase",
        opacity: disabled ? 0.5 : 1,
        cursor: disabled ? "not-allowed" : "pointer",
        ...sizes,
        ...variants[variant],
      }}
    >
      {icon && <AIcon name={icon} size={size === "sm" ? 10 : 12} />}
      {children}
    </button>
  );
}

export function RefCode({ code, color = "var(--sunset)" }: { code: string; color?: string }) {
  return (
    <span
      style={{
        fontFamily: "var(--mono)",
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

export function Empty({
  icon = "sparkle",
  title,
  subtitle,
  cta,
}: {
  icon?: AIconName;
  title: string;
  subtitle?: ReactNode;
  cta?: ReactNode;
}) {
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
          width: 52,
          height: 52,
          borderRadius: 11,
          background: "var(--surface)",
          border: "1px dashed var(--border)",
          color: "var(--text-dim)",
          display: "grid",
          placeItems: "center",
        }}
      >
        <AIcon name={icon} size={22} />
      </div>
      <div style={{ fontFamily: "var(--sans)", fontSize: 14, fontWeight: 600, color: "var(--text)" }}>
        {title}
      </div>
      {subtitle && (
        <div style={{ fontSize: 12, color: "var(--text-mute)", maxWidth: 360, lineHeight: 1.5 }}>
          {subtitle}
        </div>
      )}
      {cta}
    </div>
  );
}

export function FieldGrid({ cols = 2, children }: { cols?: number; children: ReactNode }) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`,
        gap: 14,
      }}
    >
      {children}
    </div>
  );
}

export function Note({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "warning" | "info" }) {
  const color =
    tone === "warning" ? "var(--amber)" : tone === "info" ? "var(--sky)" : "var(--text-mute)";
  return (
    <div
      style={{
        padding: "10px 12px",
        borderRadius: 6,
        background: `color-mix(in oklch, ${color} 8%, transparent)`,
        border: `1px solid color-mix(in oklch, ${color} 26%, transparent)`,
        color: "var(--text)",
        fontSize: 12,
        lineHeight: 1.5,
      }}
    >
      {children}
    </div>
  );
}
