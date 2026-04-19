import type { TelosEntry } from "@/lib/telos-api";
import { cn } from "@/lib/utils";

const STATUS_COLORS: Record<string, string> = {
  inprogress: "bg-accent-blue",
  backlog: "bg-txt-secondary",
  done: "bg-green-500",
  other: "bg-yellow-500",
};

interface Props {
  task: TelosEntry;
  bucket: string;
}

export default function TaskRow({ task, bucket }: Props) {
  const firstLine = (task.content || "").split("\n")[0];
  return (
    <div
      className="flex items-start gap-2 px-2 py-1.5 hover:bg-bg-tertiary transition-colors"
      data-test={`projects-task-${task.ref_code}`}
    >
      <span
        className={cn(
          "inline-block w-1.5 h-1.5 rounded-full mt-1.5 flex-shrink-0",
          STATUS_COLORS[bucket] ?? STATUS_COLORS.other,
        )}
        title={bucket}
      />
      <span className="text-[0.65rem] font-mono text-accent-blue flex-shrink-0 mt-0.5">
        {task.ref_code}
      </span>
      <span
        className={cn(
          "text-[0.8rem] font-mono text-txt-primary truncate",
          bucket === "done" && "line-through text-txt-secondary",
        )}
      >
        {firstLine}
      </span>
    </div>
  );
}
