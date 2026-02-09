/** Reusable admin form controls matching the legacy FormBuilder (FB). */
import { cn } from "@/lib/utils";

const fieldBase =
  "w-full p-2 border border-[#2a3a5c] rounded-md bg-[#1a1a2e] text-[#eee] text-sm outline-none focus:border-[#e94560] transition-colors";

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
  label, value, onChange, type = "text", placeholder, hint, readOnly, datalist, className,
}: InputProps) {
  const listId = datalist ? `dl-${label.replace(/\s/g, "-").toLowerCase()}` : undefined;
  return (
    <div className={cn("mb-3", className)}>
      <label className="block text-xs text-[#999] mb-1 font-medium">{label}</label>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        readOnly={readOnly}
        list={listId}
        className={cn(fieldBase, readOnly && "opacity-60 cursor-not-allowed")}
      />
      {datalist && (
        <datalist id={listId}>
          {datalist.map((v) => <option key={v} value={v} />)}
        </datalist>
      )}
      {hint && <div className="text-[0.72rem] text-[#666] mt-0.5">{hint}</div>}
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
    <div className="flex items-center gap-2.5 mb-3">
      <button
        type="button"
        onClick={() => onChange(!checked)}
        className={cn(
          "relative w-[38px] h-5 rounded-[10px] transition-colors flex-shrink-0 cursor-pointer border-none p-0",
          checked ? "bg-[#2ecc71]" : "bg-[#e94560]",
        )}
      >
        <span
          className={cn(
            "absolute left-0 w-3.5 h-3.5 rounded-full transition-transform top-[3px]",
            checked ? "translate-x-[21px] bg-white" : "translate-x-[3px] bg-[#999]",
          )}
        />
      </button>
      <span className="text-sm text-[#999] cursor-pointer" onClick={() => onChange(!checked)}>
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
      <label className="block text-xs text-[#999] mb-1 font-medium">{label}</label>
      <select value={value} onChange={(e) => onChange(e.target.value)} className={cn(fieldBase, "cursor-pointer")}>
        {options.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
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
    <div className="mb-3">
      <label className="block text-xs text-[#999] mb-1 font-medium">{label}</label>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className={cn(fieldBase, "resize-y font-mono text-[0.8rem]", large ? "min-h-[200px]" : "min-h-[80px]")}
      />
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
    <div className="mb-3">
      <label className="block text-xs text-[#999] mb-1 font-medium">{label}</label>
      <div className="flex items-center gap-3">
        <input
          type="range"
          value={value}
          onChange={(e) => onChange(parseFloat(e.target.value))}
          min={min}
          max={max}
          step={step}
          className="flex-1 accent-[#e94560]"
        />
        <span className="min-w-[3em] text-right text-sm text-[#999] font-mono">{value}</span>
      </div>
    </div>
  );
}

// ── Form Row (grid) ──────────────────────────────────────
export function FormRow({ children, cols = 2 }: { children: React.ReactNode; cols?: 2 | 3 }) {
  return (
    <div className={cn("grid gap-3", cols === 3 ? "grid-cols-3" : "grid-cols-2")}>
      {children}
    </div>
  );
}

// ── Card ─────────────────────────────────────────────────
export function Card({ title, children }: { title?: string; children: React.ReactNode }) {
  return (
    <div className="bg-[#16213e] border border-[#2a3a5c] rounded-lg p-4 mb-4">
      {title && <h3 className="text-sm mb-3 text-[#e94560]">{title}</h3>}
      {children}
    </div>
  );
}

// ── Note ─────────────────────────────────────────────────
export function Note({ children }: { children: React.ReactNode }) {
  return (
    <div className="bg-[#0f3460] border border-[#2a3a5c] rounded-md px-3 py-2.5 text-[0.8rem] text-[#999] mb-4">
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
    <div className="flex items-center gap-2.5 mt-5 pt-3.5 border-t border-[#2a3a5c]">
      {onTest && (
        <button
          onClick={onTest}
          disabled={testing}
          className="px-3 py-2 bg-[#0f3460] text-[#eee] border border-[#2a3a5c] rounded-md text-sm font-medium hover:border-[#e94560] transition-colors cursor-pointer disabled:opacity-50"
        >
          {testing ? "Testing..." : "Test Connection"}
        </button>
      )}
      {testResult && (
        <span className={cn("text-sm", testResult.status === "ok" ? "text-[#4caf50]" : "text-[#c0392b]")}>
          {testResult.message}
        </span>
      )}
      <span className="flex-1" />
      {onSave && (
        <button
          onClick={onSave}
          disabled={saving}
          className="px-4 py-2 bg-[#e94560] text-white rounded-md text-sm font-medium hover:bg-[#b83350] transition-colors cursor-pointer disabled:opacity-50"
        >
          {saving ? "Saving..." : "Save"}
        </button>
      )}
    </div>
  );
}

// ── Badge ────────────────────────────────────────────────
export function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    ok: "bg-[#1b3a1b] text-[#4caf50]",
    error: "bg-[#3a1b1b] text-[#c0392b]",
    unconfigured: "bg-[#2a2a2a] text-[#666]",
  };
  const labels: Record<string, string> = {
    ok: "Connected",
    error: "Error",
    unconfigured: "Not Configured",
  };
  return (
    <span className={cn("text-xs px-2.5 py-0.5 rounded-full font-semibold", styles[status] || styles.unconfigured)}>
      {labels[status] || status}
    </span>
  );
}
