import { useState } from "react";
import { useTerminalStore } from "@/stores/terminal-store";
import { cn } from "@/lib/utils";

export default function CloneForm() {
  const cloneRepo = useTerminalStore((s) => s.cloneRepo);
  const [owner, setOwner] = useState("");
  const [repo, setRepo] = useState("");
  const [branch, setBranch] = useState("main");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<{ text: string; isError: boolean } | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!owner.trim() || !repo.trim()) return;

    setLoading(true);
    setMessage(null);

    const result = await cloneRepo(owner.trim(), repo.trim(), branch.trim());

    if (result.status === "success") {
      setMessage({ text: "Repository cloned successfully!", isError: false });
      setOwner("");
      setRepo("");
      setBranch("main");
    } else {
      setMessage({ text: result.message || "Clone failed", isError: true });
    }

    setLoading(false);
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="border border-border bg-bg-secondary p-4 flex flex-col gap-3"
    >
      <h3 className="text-sm font-mono text-txt-primary uppercase tracking-wider">
        Clone Repository
      </h3>

      <div className="flex gap-2">
        <div className="flex-1">
          <label className="text-xs font-mono text-txt-secondary mb-1 block">
            Owner
          </label>
          <input
            type="text"
            value={owner}
            onChange={(e) => setOwner(e.target.value)}
            placeholder="perrymanuk"
            className="w-full bg-bg-primary border border-border text-txt-primary text-sm font-mono px-2 py-1.5 focus:border-accent-blue focus:outline-none"
          />
        </div>
        <div className="flex-1">
          <label className="text-xs font-mono text-txt-secondary mb-1 block">
            Repository
          </label>
          <input
            type="text"
            value={repo}
            onChange={(e) => setRepo(e.target.value)}
            placeholder="radbot"
            className="w-full bg-bg-primary border border-border text-txt-primary text-sm font-mono px-2 py-1.5 focus:border-accent-blue focus:outline-none"
          />
        </div>
        <div className="w-32">
          <label className="text-xs font-mono text-txt-secondary mb-1 block">
            Branch
          </label>
          <input
            type="text"
            value={branch}
            onChange={(e) => setBranch(e.target.value)}
            placeholder="main"
            className="w-full bg-bg-primary border border-border text-txt-primary text-sm font-mono px-2 py-1.5 focus:border-accent-blue focus:outline-none"
          />
        </div>
      </div>

      {message && (
        <p
          className={cn(
            "text-xs font-mono",
            message.isError ? "text-terminal-red" : "text-terminal-green",
          )}
        >
          {message.text}
        </p>
      )}

      <button
        type="submit"
        disabled={loading || !owner.trim() || !repo.trim()}
        className={cn(
          "self-end px-4 py-1.5 border text-xs font-mono uppercase tracking-wider transition-all cursor-pointer",
          loading
            ? "border-border text-txt-secondary cursor-not-allowed"
            : "border-terminal-green text-terminal-green hover:bg-terminal-green hover:text-bg-primary",
        )}
      >
        {loading ? "Cloning..." : "Clone"}
      </button>
    </form>
  );
}
