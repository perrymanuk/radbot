import { useMemo, useState } from "react";
import { AIcon } from "./icons";
import { StatusDot } from "./primitives";
import { PANEL_CATEGORIES, mapStatus, totalPanelCount } from "./catalog";
import type { IntegrationStatus } from "@/lib/admin-api";

interface SidebarProps {
  active: string;
  setActive: (id: string) => void;
  status: IntegrationStatus;
}

export function AdminSidebar({ active, setActive, status }: SidebarProps) {
  const [q, setQ] = useState("");
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const qLower = q.trim().toLowerCase();

  const groups = useMemo(
    () =>
      PANEL_CATEGORIES.map((cat) => {
        const panels = qLower
          ? cat.panels.filter((p) => (p.label + " " + p.id).toLowerCase().includes(qLower))
          : cat.panels;
        return { ...cat, panels };
      }).filter((cat) => !qLower || cat.panels.length > 0),
    [qLower],
  );

  return (
    <aside
      data-test="admin-sidebar"
      style={{
        width: 230,
        height: "100%",
        display: "flex",
        flexDirection: "column",
        background: "var(--bg-sunk)",
        borderRight: "1px solid var(--border)",
        flex: "none",
      }}
    >
      {/* Search */}
      <div style={{ padding: "10px 12px", borderBottom: "1px solid var(--border-soft)" }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 6,
            padding: "6px 9px",
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: 5,
          }}
        >
          <span style={{ color: "var(--text-dim)" }}>
            <AIcon name="search" size={12} />
          </span>
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="filter panels…"
            style={{
              flex: 1,
              fontFamily: "var(--mono)",
              fontSize: 11,
              color: "var(--text)",
              background: "transparent",
              border: "none",
              outline: "none",
              minWidth: 0,
            }}
          />
        </div>
      </div>

      <nav style={{ flex: 1, overflowY: "auto", padding: "6px 0" }}>
        {groups.map((cat) => {
          const isCollapsed = !!collapsed[cat.key] && !qLower;
          return (
            <div
              key={cat.key}
              data-test={`admin-group-${cat.key}`}
            >
              <button
                type="button"
                onClick={() =>
                  setCollapsed((c) => ({ ...c, [cat.key]: !c[cat.key] }))
                }
                style={{
                  width: "100%",
                  padding: "8px 14px 4px",
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                  background: "transparent",
                  border: "none",
                  cursor: "pointer",
                  color: "inherit",
                }}
              >
                <span
                  style={{
                    color: "var(--text-dim)",
                    transition: "transform 120ms",
                    transform: `rotate(${isCollapsed ? 0 : 90}deg)`,
                    display: "inline-flex",
                  }}
                >
                  <AIcon name="chev" size={9} />
                </span>
                <span
                  style={{
                    fontFamily: "var(--mono)",
                    fontSize: 9,
                    fontWeight: 700,
                    letterSpacing: "0.18em",
                    color: "var(--text-dim)",
                  }}
                >
                  {cat.label}
                </span>
                <span style={{ flex: 1 }} />
                <span style={{ fontFamily: "var(--mono)", fontSize: 9, color: "var(--text-dim)" }}>
                  {cat.panels.length}
                </span>
              </button>
              {!isCollapsed &&
                cat.panels.map((p) => {
                  const isActive = p.id === active;
                  const dotStatus = mapStatus(p.statusKey ? status[p.statusKey] : undefined);
                  return (
                    <button
                      key={p.id}
                      type="button"
                      onClick={() => setActive(p.id)}
                      data-test={`admin-nav-${p.id}`}
                      data-status={dotStatus}
                      data-active={isActive ? "true" : "false"}
                      style={{
                        width: "100%",
                        display: "flex",
                        alignItems: "center",
                        gap: 8,
                        padding: "6px 14px 6px 22px",
                        textAlign: "left",
                        color: isActive ? "var(--text)" : "var(--text-mute)",
                        background: isActive
                          ? "linear-gradient(90deg, color-mix(in oklch, var(--sunset) 14%, transparent), transparent 70%)"
                          : "transparent",
                        borderLeft: isActive
                          ? "2px solid var(--sunset)"
                          : "2px solid transparent",
                        borderTop: "none",
                        borderRight: "none",
                        borderBottom: "none",
                        marginLeft: -1,
                        cursor: "pointer",
                      }}
                    >
                      <StatusDot status={dotStatus} size={6} />
                      <span
                        style={{
                          fontFamily: "var(--sans)",
                          fontSize: 12,
                          fontWeight: isActive ? 600 : 500,
                          whiteSpace: "nowrap",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          flex: 1,
                          minWidth: 0,
                        }}
                      >
                        {p.label}
                      </span>
                    </button>
                  );
                })}
            </div>
          );
        })}
      </nav>

      <div
        style={{
          padding: "8px 14px",
          borderTop: "1px solid var(--border-soft)",
          fontFamily: "var(--mono)",
          fontSize: 10,
          color: "var(--text-dim)",
          display: "flex",
          alignItems: "center",
          gap: 6,
        }}
      >
        <span
          style={{
            width: 6,
            height: 6,
            borderRadius: "50%",
            background: "var(--crt)",
            boxShadow: "0 0 6px var(--crt)",
          }}
        />
        <span>{totalPanelCount()} panels</span>
      </div>
    </aside>
  );
}
