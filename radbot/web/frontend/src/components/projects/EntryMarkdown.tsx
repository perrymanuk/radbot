import { memo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface Props {
  content: string;
  className?: string;
}

function EntryMarkdownImpl({ content, className }: Props) {
  return (
    <div
      className={`prose prose-invert prose-sm max-w-none font-mono text-[0.8rem] leading-relaxed ${className ?? ""}`}
    >
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
    </div>
  );
}

export default memo(EntryMarkdownImpl);
