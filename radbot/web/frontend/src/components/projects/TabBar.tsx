import PIcon from "./shared/PIcon";

export interface Tab {
  key: string;
  label: string;
  icon: Parameters<typeof PIcon>[0]["name"];
  count?: number | null;
}

interface Props {
  tabs: Tab[];
  active: string;
  setActive: (key: string) => void;
  accent: string;
}

export default function TabBar({ tabs, active, setActive, accent }: Props) {
  return (
    <div
      className="projects-tab-bar"
      style={{
        display: "flex",
        borderBottom: "1px solid var(--p-border)",
        background: "var(--surface)",
        padding: "0 20px",
        flex: "none",
        gap: 0,
        overflowX: "auto",
      }}
    >
      {tabs.map((t) => {
        const isActive = t.key === active;
        return (
          <button
            key={t.key}
            onClick={() => setActive(t.key)}
            style={{
              padding: "10px 14px",
              fontFamily: "var(--p-mono)",
              fontSize: 11,
              fontWeight: 700,
              letterSpacing: "0.12em",
              color: isActive ? accent : "var(--text-mute)",
              borderBottom: `2px solid ${isActive ? accent : "transparent"}`,
              display: "inline-flex",
              alignItems: "center",
              gap: 7,
              textTransform: "uppercase",
              marginBottom: -1,
            }}
            data-test={`projects-tab-${t.key}`}
          >
            <span style={{ color: isActive ? accent : "var(--text-dim)", display: "inline-flex" }}>
              <PIcon name={t.icon} size={12} />
            </span>
            <span>{t.label}</span>
            {t.count != null && t.count > 0 && (
              <span
                style={{
                  fontFamily: "var(--p-mono)",
                  fontSize: 9,
                  fontWeight: 700,
                  padding: "1px 5px",
                  borderRadius: 2,
                  color: isActive ? "var(--bg)" : "var(--text-dim)",
                  background: isActive ? accent : "var(--surface-2)",
                  border: isActive ? "none" : "1px solid var(--border-soft)",
                }}
              >
                {t.count}
              </span>
            )}
          </button>
        );
      })}
      <div style={{ flex: 1, borderBottom: "1px solid var(--p-border)", marginBottom: -1 }} />
      <div
        className="projects-tab-kbd-hint"
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          padding: "8px 0",
          fontFamily: "var(--p-mono)",
          fontSize: 9,
          color: "var(--text-dim)",
          letterSpacing: "0.12em",
        }}
      >
        <span>TAB</span>
        <span className="kbd">1-5</span>
      </div>
    </div>
  );
}
