import type { ReactNode } from "react";
import { AIcon } from "./icons";
import { StatusPill, type PanelStatus } from "./primitives";
import type { CatalogPanel, CatalogCategory } from "./catalog";

interface PanelHeaderProps {
  panel: CatalogPanel;
  category: CatalogCategory;
  status: PanelStatus;
  actions?: ReactNode;
}

export function PanelHeader({ panel, category, status, actions }: PanelHeaderProps) {
  return (
    <div
      style={{
        padding: "18px 26px 14px",
        borderBottom: "1px solid var(--border)",
        background: "linear-gradient(180deg, var(--surface-2), var(--surface))",
        flex: "none",
      }}
    >
      <div
        style={{
          fontFamily: "var(--mono)",
          fontSize: 10,
          fontWeight: 700,
          letterSpacing: "0.18em",
          color: "var(--text-dim)",
          marginBottom: 4,
        }}
      >
        ADMIN · {category.label}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <div
          style={{
            width: 32,
            height: 32,
            flex: "none",
            borderRadius: 7,
            background: "color-mix(in oklch, var(--sunset) 16%, var(--surface))",
            border: "1px solid color-mix(in oklch, var(--sunset) 38%, transparent)",
            color: "var(--sunset)",
            display: "grid",
            placeItems: "center",
          }}
        >
          <AIcon name={panel.icon} size={16} />
        </div>
        <h1
          style={{
            margin: 0,
            fontFamily: "var(--sans)",
            fontSize: 22,
            fontWeight: 700,
            color: "var(--text)",
            lineHeight: 1.15,
          }}
        >
          {panel.label}
        </h1>
        <StatusPill status={status} />
        <span style={{ flex: 1 }} />
        {actions}
      </div>
    </div>
  );
}
