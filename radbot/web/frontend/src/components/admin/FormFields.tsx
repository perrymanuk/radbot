/**
 * Reusable admin form controls.
 *
 * These are thin wrappers around the shell primitives in
 * `components/admin/shell/primitives.tsx`. Every existing panel imports from
 * this module, so restyling here re-skins every panel automatically without
 * touching panel code.
 */
import type { ReactNode } from "react";
import {
  Button,
  Field,
  SectionCard,
  Select,
  StatusPill,
  TextArea,
  TextInput,
  Toggle,
  type PanelStatus,
} from "@/components/admin/shell";
import { cn } from "@/lib/utils";

// ── Text / Password / Number ─────────────────────────────
interface InputProps {
  label: string;
  value: string | number;
  onChange: (v: string) => void;
  type?: "text" | "password" | "number";
  placeholder?: string;
  hint?: string;
  readOnly?: boolean;
  datalist?: string[];
  className?: string;
}

export function FormInput({
  label,
  value,
  onChange,
  type = "text",
  placeholder,
  hint,
  readOnly,
  datalist,
  className,
}: InputProps) {
  const listId = datalist ? `dl-${label.replace(/\s/g, "-").toLowerCase()}` : undefined;
  return (
    <div className={cn("mb-3", className)} style={{ display: "flex", flexDirection: "column" }}>
      <Field label={label} hint={hint}>
        <TextInput
          value={String(value ?? "")}
          onChange={onChange}
          type={type}
          placeholder={placeholder}
          readOnly={readOnly}
          list={listId}
        />
        {datalist && (
          <datalist id={listId}>
            {datalist.map((v) => (
              <option key={v} value={v} />
            ))}
          </datalist>
        )}
      </Field>
    </div>
  );
}

// ── Toggle ───────────────────────────────────────────────
interface ToggleProps {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}

export function FormToggle({ label, checked, onChange }: ToggleProps) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
      <Toggle value={checked} onChange={onChange} />
      <span
        style={{
          fontSize: 13,
          color: "var(--text)",
          cursor: "pointer",
        }}
        onClick={() => onChange(!checked)}
      >
        {label}
      </span>
    </div>
  );
}

// ── Dropdown ─────────────────────────────────────────────
interface DropdownProps {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
  className?: string;
}

export function FormDropdown({ label, value, onChange, options, className }: DropdownProps) {
  return (
    <div className={cn("mb-3", className)}>
      <Field label={label}>
        <Select value={value} onChange={onChange} options={options} />
      </Field>
    </div>
  );
}

// ── Textarea ─────────────────────────────────────────────
interface TextareaProps {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  large?: boolean;
}

export function FormTextarea({ label, value, onChange, placeholder, large }: TextareaProps) {
  return (
    <div style={{ marginBottom: 12 }}>
      <Field label={label}>
        <TextArea
          value={value}
          onChange={onChange}
          placeholder={placeholder}
          rows={large ? 12 : 4}
          mono
        />
      </Field>
    </div>
  );
}

// ── Slider ───────────────────────────────────────────────
interface SliderProps {
  label: string;
  value: number;
  onChange: (v: number) => void;
  min: number;
  max: number;
  step: number;
}

export function FormSlider({ label, value, onChange, min, max, step }: SliderProps) {
  return (
    <div style={{ marginBottom: 12 }}>
      <Field label={label}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <input
            type="range"
            value={value}
            onChange={(e) => onChange(parseFloat(e.target.value))}
            min={min}
            max={max}
            step={step}
            style={{ flex: 1, accentColor: "var(--sunset)" }}
          />
          <span
            style={{
              minWidth: "3em",
              textAlign: "right",
              fontSize: 12,
              fontFamily: "var(--mono)",
              color: "var(--text-mute)",
            }}
          >
            {value}
          </span>
        </div>
      </Field>
    </div>
  );
}

// ── Form Row (grid) ──────────────────────────────────────
export function FormRow({ children, cols = 2 }: { children: ReactNode; cols?: 2 | 3 }) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`,
        gap: 12,
      }}
    >
      {children}
    </div>
  );
}

// ── Card ─────────────────────────────────────────────────
export function Card({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <SectionCard title={title} accent="var(--sunset)">
        {children}
      </SectionCard>
    </div>
  );
}

// ── Note ─────────────────────────────────────────────────
export function Note({ children }: { children: ReactNode }) {
  return (
    <div
      style={{
        padding: "10px 12px",
        borderRadius: 6,
        background: "color-mix(in oklch, var(--sky) 6%, var(--surface))",
        border: "1px solid color-mix(in oklch, var(--sky) 22%, var(--border))",
        color: "var(--text-mute)",
        fontSize: 12,
        lineHeight: 1.5,
        marginBottom: 14,
      }}
    >
      {children}
    </div>
  );
}

// ── Action Bar ───────────────────────────────────────────
interface ActionBarProps {
  onSave?: () => void;
  onTest?: () => void;
  testResult?: { status: string; message: string } | null;
  testing?: boolean;
  saving?: boolean;
}

export function ActionBar({ onSave, onTest, testResult, testing, saving }: ActionBarProps) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 10,
        marginTop: 18,
        paddingTop: 14,
        borderTop: "1px solid var(--border-soft)",
      }}
    >
      {onTest && (
        <Button onClick={onTest} disabled={testing} variant="default">
          {testing ? "Testing…" : "Test Connection"}
        </Button>
      )}
      {testResult && (
        <span
          style={{
            fontSize: 12,
            color: testResult.status === "ok" ? "var(--crt)" : "var(--magenta)",
          }}
        >
          {testResult.message}
        </span>
      )}
      <span style={{ flex: 1 }} />
      {onSave && (
        <Button onClick={onSave} disabled={saving} variant="primary" icon="check">
          {saving ? "Saving…" : "Save"}
        </Button>
      )}
    </div>
  );
}

// ── Badge ────────────────────────────────────────────────
export function StatusBadge({ status }: { status: string }) {
  const map: Record<string, PanelStatus> = {
    ok: "connected",
    error: "error",
    unconfigured: "disconnected",
  };
  const panelStatus: PanelStatus = map[status] ?? "neutral";
  return <StatusPill status={panelStatus} />;
}
