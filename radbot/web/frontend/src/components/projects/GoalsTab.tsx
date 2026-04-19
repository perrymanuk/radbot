import { useShallow } from "zustand/shallow";
import type { TelosEntry } from "@/lib/telos-api";
import {
  selectGoalsForProject,
  useProjectsStore,
} from "@/stores/projects-store";
import PIcon from "./shared/PIcon";
import RefCode from "./shared/RefCode";
import { Empty } from "./shared/Misc";

interface Props {
  project: TelosEntry;
}

export default function GoalsTab({ project }: Props) {
  const goals = useProjectsStore(
    useShallow((s) => selectGoalsForProject(s, project.ref_code!)),
  );

  if (goals.length === 0) {
    return <Empty label="No goals attached — set a North Star for this project." icon="target" />;
  }

  return (
    <div
      style={{
        padding: "18px 22px",
        display: "flex",
        flexDirection: "column",
        gap: 12,
      }}
      data-test="projects-goals-tab"
    >
      {goals.map((g) => {
        const title = (g.content || "").split("\n")[0];
        const body = (g.content || "").split("\n").slice(1).join("\n").trim();
        return (
          <div
            key={g.entry_id}
            style={{
              padding: "14px 16px",
              borderRadius: 8,
              background: "color-mix(in oklch, var(--sky) 8%, var(--surface))",
              border: "1px solid color-mix(in oklch, var(--sky) 32%, var(--p-border))",
              borderLeft: "3px solid var(--sky)",
            }}
            data-test={`projects-goal-${g.ref_code}`}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                marginBottom: 6,
              }}
            >
              <span style={{ color: "var(--sky)", display: "inline-flex" }}>
                <PIcon name="target" size={14} />
              </span>
              <RefCode code={g.ref_code || ""} color="var(--sky)" />
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
