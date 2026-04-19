import { useShallow } from "zustand/shallow";
import type { TelosEntry } from "@/lib/telos-api";
import {
  selectExplorationsForProject,
  useProjectsStore,
} from "@/stores/projects-store";
import PIcon from "./shared/PIcon";
import RefCode from "./shared/RefCode";
import { Empty } from "./shared/Misc";

interface Props {
  project: TelosEntry;
}

export default function ExplorationsTab({ project }: Props) {
  const explorations = useProjectsStore(
    useShallow((s) => selectExplorationsForProject(s, project.ref_code!)),
  );

  if (explorations.length === 0) {
    return <Empty label="No explorations yet — start a spike, drop notes here." icon="flask" />;
  }

  return (
    <div
      style={{
        padding: "18px 22px",
        display: "flex",
        flexDirection: "column",
        gap: 12,
      }}
      data-test="projects-explorations-tab"
    >
      {explorations.map((e) => {
        const title = (e.content || "").split("\n")[0];
        const body = (e.content || "").split("\n").slice(1).join("\n").trim();
        return (
          <div
            key={e.entry_id}
            style={{
              padding: "14px 16px",
              borderRadius: 8,
              background: "color-mix(in oklch, var(--magenta) 6%, var(--surface))",
              border: "1px dashed color-mix(in oklch, var(--magenta) 38%, var(--p-border))",
            }}
            data-test={`projects-exploration-${e.ref_code}`}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                marginBottom: 6,
              }}
            >
              <span style={{ color: "var(--magenta)", display: "inline-flex" }}>
                <PIcon name="flask" size={14} />
              </span>
              <RefCode code={e.ref_code || ""} color="var(--magenta)" />
              <span
                style={{
                  fontFamily: "var(--sans)",
                  fontSize: 15,
                  fontWeight: 600,
                  color: "var(--text)",
                }}
              >
                {title}
              </span>
              <span style={{ flex: 1 }} />
              <span
                style={{
                  fontFamily: "var(--p-mono)",
                  fontSize: 9,
                  fontWeight: 700,
                  letterSpacing: "0.14em",
                  color: "var(--text-dim)",
                }}
              >
                {e.status.toUpperCase()}
              </span>
            </div>
            {body && (
              <div
                style={{
                  fontSize: 13,
                  color: "var(--text-mute)",
                  lineHeight: 1.6,
                  paddingLeft: 22,
                  whiteSpace: "pre-wrap",
                }}
              >
                {body}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
