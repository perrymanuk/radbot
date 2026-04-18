import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";
import type { MediaCardData } from "@/components/chat/AgentCards";

// Right-side drawer showing enriched media metadata (fetched via
// /api/media/{tmdb_id}). Mirrors the NotificationDetail layout so the
// user gets a consistent drawer pattern across the app.

interface Props {
  tmdbId: number;
  mediaType: "movie" | "tv";
  fallback?: MediaCardData; // shown while /api/media/{tmdb_id} is loading or fails
  onClose: () => void;
}

interface Detail extends MediaCardData {
  // server adds nothing past MediaCardData right now, but leave room.
}

export default function MediaDetail({ tmdbId, mediaType, fallback, onClose }: Props) {
  const [detail, setDetail] = useState<Detail | null>(fallback ?? null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setErr(null);
      try {
        const res = await fetch(`/api/media/${tmdbId}?media_type=${mediaType}`);
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body.detail || `${res.status} ${res.statusText}`);
        }
        const body = (await res.json()) as Detail;
        if (!cancelled) setDetail(body);
      } catch (e: any) {
        if (!cancelled) setErr(e.message || "Failed to load details");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [tmdbId, mediaType]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [onClose]);

  const accent = "#ff9966"; // radbot-sunset
  const d = detail;

  return (
    <>
      <div
        onClick={onClose}
        aria-hidden
        className="fixed inset-0 z-[900] bg-black/55 backdrop-blur-[3px]"
      />
      <div
        role="dialog"
        aria-label={d?.title ?? "Media detail"}
        className="fixed top-0 right-0 bottom-0 z-[901] w-[min(560px,calc(100vw-24px))] bg-bg-primary flex flex-col animate-drawer-in"
        style={{
          borderLeft: `2px solid ${accent}`,
          boxShadow: `-30px 0 60px -20px rgba(0,0,0,0.7), 0 0 100px -40px ${accent}`,
        }}
      >
        <div
          className="flex items-start gap-3 px-5 py-3.5 border-b border-border flex-none"
          style={{
            background: `linear-gradient(180deg, color-mix(in oklch, ${accent} 10%, #1b2939), #121c2b)`,
          }}
        >
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1 flex-wrap">
              <span className="text-[0.6rem] font-mono font-bold tracking-[0.14em] uppercase text-radbot-sunset">
                {mediaType === "movie" ? "MOVIE" : "TV SERIES"}
              </span>
              {d?.year_range && (
                <span className="text-[0.6rem] font-mono text-txt-secondary">
                  · {d.year_range}
                </span>
              )}
              {!d?.year_range && d?.year && (
                <span className="text-[0.6rem] font-mono text-txt-secondary">· {d.year}</span>
              )}
              {d?.content_rating && (
                <span className="text-[0.6rem] font-mono text-txt-secondary px-1 border border-border rounded-sm">
                  {d.content_rating}
                </span>
              )}
            </div>
            <h2 className="text-[18px] font-bold text-txt-primary leading-tight m-0">
              {d?.title ?? "Loading…"}
            </h2>
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            className="w-[30px] h-[30px] flex-none rounded-sm grid place-items-center text-txt-secondary border border-border hover:text-txt-primary hover:bg-bg-tertiary transition-colors"
          >
            ✕
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 pt-4 pb-6">
          {loading && !detail && (
            <div className="py-6 text-center text-[0.7rem] font-mono text-txt-secondary">
              LOADING…
            </div>
          )}
          {err && (
            <div className="py-3 px-3 mb-4 text-[0.75rem] text-terminal-red border border-terminal-red/30 bg-terminal-red/5 rounded-sm">
              {err}
            </div>
          )}

          {d && (
            <>
              {d.poster?.url && (
                <div className="mb-4 flex justify-center">
                  <img
                    src={d.poster.url}
                    alt={d.title}
                    className="max-w-[220px] rounded-sm border border-border"
                  />
                </div>
              )}

              <Row label="status" value={d.status} />
              {d.format && <Row label="format" value={d.format} />}
              {d.resolution && <Row label="resolution" value={d.resolution} />}
              {typeof d.season_count === "number" && (
                <Row label="seasons" value={String(d.season_count)} />
              )}
              {typeof d.episode_count === "number" && (
                <Row label="episodes" value={String(d.episode_count)} />
              )}
              {d.episode_runtime && <Row label="runtime" value={d.episode_runtime} />}
              {d.on_server && (
                <Row
                  label="on server"
                  value={`${d.on_server.have} / ${d.on_server.total}`}
                />
              )}
              {typeof d.tmdb_id === "number" && (
                <Row label="tmdb_id" value={String(d.tmdb_id)} mono />
              )}

              {d.note && (
                <div className="mt-4">
                  <div className="font-mono text-[9px] font-bold tracking-[0.16em] text-txt-secondary uppercase mb-1.5">
                    OVERVIEW
                  </div>
                  <p className="text-[0.82rem] leading-[1.55] text-txt-primary whitespace-pre-wrap">
                    {d.note}
                  </p>
                </div>
              )}
            </>
          )}
        </div>

        <div className="flex items-center gap-2 flex-wrap px-5 py-3 border-t border-border bg-bg-tertiary flex-none">
          {d?.tmdb_id && (
            <a
              href={`https://www.themoviedb.org/${mediaType === "movie" ? "movie" : "tv"}/${d.tmdb_id}`}
              target="_blank"
              rel="noopener noreferrer"
              className={cn(
                "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-sm no-underline",
                "font-mono text-[0.7rem] font-bold tracking-[0.12em] uppercase",
                "text-txt-secondary border border-border bg-bg-secondary",
                "hover:text-txt-primary transition-colors",
              )}
            >
              TMDB ↗
            </a>
          )}
          <div className="flex-1" />
          <button
            onClick={onClose}
            className={cn(
              "inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-sm",
              "font-mono text-[0.7rem] font-bold tracking-[0.12em] uppercase",
              "text-txt-secondary border border-border bg-transparent",
              "hover:text-txt-primary hover:bg-bg-secondary transition-colors",
            )}
          >
            ESC ✕
          </button>
        </div>
      </div>
    </>
  );
}

function Row({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex gap-3 py-1.5 items-start border-b border-dashed border-border/40 last:border-b-0">
      <span className="text-[0.7rem] font-mono text-txt-secondary min-w-[110px] flex-none uppercase tracking-[0.08em]">
        {label}
      </span>
      <span
        className={cn(
          "text-[0.8rem] text-txt-primary break-all flex-1",
          mono && "font-mono",
        )}
      >
        {value}
      </span>
    </div>
  );
}
