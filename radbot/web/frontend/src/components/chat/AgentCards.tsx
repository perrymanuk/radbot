import { useState } from "react";
import { cn } from "@/lib/utils";
import { Icon } from "@/components/chat/icons";
import MediaDetail from "@/components/chat/MediaDetail";

// ─────────────────────────────────────────────────────────
// PLACEHOLDER CARD COMPONENTS
//
// These components visualize agent tool output (media availability,
// Home Assistant device state, season breakdowns, etc.) that the
// backend does not emit yet. They accept a fully-shaped prop so
// `ChatMessage` can mount them from inline JSON once the backend
// starts returning structured payloads.
//
// Wire them in later by:
//   1. Having an agent reply include a fenced block like
//      ```radbot:media { ...MediaCardData... }```
//   2. Detecting that block in ChatMessage's markdown custom `code`
//      renderer and rendering <MediaCard m={JSON.parse(...)} /> instead.
// ─────────────────────────────────────────────────────────

// ── Types ─────────────────────────────────────────────────
export interface MediaPoster {
  hue?: number;
  accent?: "sunset" | "violet" | "sky" | "magenta";
  title?: string;       // large poster glyph (e.g. "火", "DUNE 2")
  badge?: string;       // small top-left badge (e.g. "ATLA", "LIVE")
  footer?: string;      // small bottom footer (e.g. "RADBOT·SCOUT")
  url?: string;         // real poster image URL (TMDB or other). Takes precedence.
}

export type MediaStatus = "available" | "downloading" | "missing" | "partial";

export interface MediaCardData {
  title: string;
  subtitle?: string;
  kind: "movie" | "show";
  status: MediaStatus;
  year?: number;
  year_range?: string;      // e.g. "2005-2008"
  resolution?: string;      // e.g. "4K HDR"
  format?: string;          // e.g. "1080p WEB-DL"
  content_rating?: string;  // e.g. "TV-Y7", "TV-14", "PG-13"
  season_count?: number;
  episode_count?: number;
  episode_runtime?: string; // e.g. "60m"
  on_server?: { have: number; total: number }; // partial availability
  progress?: number;        // 0-100 for downloading
  note?: string;            // italic footer line
  poster?: MediaPoster;
  // Direct-action fields (so buttons can call /api/media/request without LLM)
  tmdb_id?: number;
  media_type?: "movie" | "tv";
}

export interface SeasonInfo {
  num: number;
  have: number;
  total: number;
  missing: string[]; // e.g. ["E03", "E07"]
}

export interface SeasonBreakdownData {
  show: string;
  seasons: SeasonInfo[];
}

export interface HaDevice {
  id: string;
  name: string;
  area: string;
  state: "on" | "off" | "open" | "closed" | "unavailable";
  detail?: string;                          // free-form right-side detail (e.g. "72°")
  icon?: "light" | "garage" | "lock" | "camera" | "climate";
  brightness_pct?: number;                  // 0-100 (lights)
  domain?: string;                          // optional; inferred from id if absent
}

// HandoffInfo is re-exported from HandoffLine.tsx at the bottom of this file.

// ── Status pill ──────────────────────────────────────────
function StatusPill({ status }: { status: MediaStatus }) {
  const map: Record<MediaStatus, { label: string; color: string }> = {
    available:   { label: "AVAILABLE",   color: "text-terminal-green border-terminal-green/40 bg-terminal-green/10" },
    partial:     { label: "PARTIAL",     color: "text-terminal-amber border-terminal-amber/40 bg-terminal-amber/10" },
    downloading: { label: "DOWNLOADING", color: "text-radbot-sunset border-radbot-sunset/40 bg-radbot-sunset/10" },
    missing:     { label: "MISSING",     color: "text-terminal-red border-terminal-red/40 bg-terminal-red/10" },
  };
  const m = map[status];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 font-mono text-[0.6rem] font-bold tracking-[0.12em] px-1.5 py-0.5 rounded-sm border",
        m.color,
      )}
    >
      <span className="w-1.5 h-1.5 rounded-full bg-current" aria-hidden />
      {m.label}
    </span>
  );
}

// ── Poster ──────────────────────────────────────────────
function Poster({ poster, size = 96 }: { poster?: MediaPoster; size?: number }) {
  const accentMap = {
    sunset: "#ff9966",
    violet: "#b088ff",
    sky: "#66ccff",
    magenta: "#ff66aa",
  } as const;
  const accent = accentMap[poster?.accent ?? "sunset"];
  const [imgErr, setImgErr] = useState(false);
  const hasImage = !!poster?.url && !imgErr;

  return (
    <div
      className="flex-none relative rounded-sm border border-border overflow-hidden"
      style={{
        width: size,
        height: size * 1.48,
        background: hasImage
          ? "#0e1419"
          : `radial-gradient(ellipse at 30% 30%, ${accent}55, #121c2b 70%)`,
        boxShadow: hasImage
          ? `0 0 14px -6px ${accent}99`
          : `inset 0 0 32px -6px ${accent}`,
      }}
    >
      {hasImage && (
        <img
          src={poster!.url}
          alt={poster?.title ?? ""}
          loading="lazy"
          onError={() => setImgErr(true)}
          className="absolute inset-0 w-full h-full object-cover"
        />
      )}
      {!hasImage && (
        <div className="absolute inset-0 grid place-items-center">
          <span
            className="font-pixel text-[2rem] leading-none [text-wrap:balance] px-1"
            style={{ color: accent, textShadow: `0 0 12px ${accent}aa` }}
          >
            {poster?.title ?? "?"}
          </span>
        </div>
      )}
      {poster?.badge && (
        <span
          className="absolute top-1.5 left-1.5 font-mono text-[0.5rem] font-bold tracking-[0.14em] px-1 py-[1px] rounded-sm z-10"
          style={{
            background: `${accent}33`,
            color: accent,
            border: `1px solid ${accent}55`,
            backdropFilter: hasImage ? "blur(4px)" : undefined,
          }}
        >
          {poster.badge}
        </span>
      )}
      {poster?.footer && !hasImage && (
        <span className="absolute bottom-1.5 left-0 right-0 text-center font-mono text-[0.5rem] tracking-[0.16em] text-txt-secondary/70">
          {poster.footer}
        </span>
      )}
    </div>
  );
}

// ── Availability bar ────────────────────────────────────
function AvailabilityBar({
  label = "AVAILABILITY",
  have,
  total,
  color = "#33FF33",
}: {
  label?: string;
  have: number;
  total: number;
  color?: string;
}) {
  const pct = total ? (have / total) * 100 : 0;
  return (
    <div>
      <div className="flex justify-between items-baseline mb-1 gap-2">
        <span className="font-mono text-[0.6rem] tracking-[0.12em] uppercase text-txt-secondary">
          {label}
        </span>
        <span className="font-mono text-[0.65rem] text-txt-primary">
          <span className="font-semibold">{have}</span>
          <span className="text-txt-secondary/60">/{total}</span>
          <span className="ml-1 text-txt-secondary/70">{pct.toFixed(0)}%</span>
        </span>
      </div>
      <div className="h-1.5 rounded-sm bg-bg-primary/60 overflow-hidden">
        <div
          className="h-full rounded-sm"
          style={{
            width: `${pct}%`,
            background: color,
            boxShadow: `0 0 8px ${color}`,
          }}
        />
      </div>
    </div>
  );
}

// ── MediaCard ───────────────────────────────────────────
export function MediaCard({ m }: { m: MediaCardData }) {
  const accent =
    m.status === "available"
      ? "#33FF33"
      : m.status === "partial"
        ? "#FFBF00"
        : m.status === "downloading"
          ? "#ff9966"
          : "#CC0000";

  const kindLabel = m.kind === "movie" ? "MOVIE" : "TV SERIES";
  const yearText = m.year_range ?? (m.year ? String(m.year) : "");

  return (
    <div className="inline-flex align-top gap-3.5 p-3.5 mr-2 mb-2 bg-bg-secondary border border-border rounded-sm w-[440px] max-w-full">
      <Poster poster={m.poster} />
      <div className="flex-1 min-w-0 flex flex-col gap-2">
        {/* Top badge row: kind · year · content rating */}
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="inline-flex items-center gap-1 font-mono text-[0.6rem] text-txt-secondary tracking-[0.12em] uppercase px-1 py-[1px] border border-border rounded-sm">
            <Icon.film size={10} /> {kindLabel}
          </span>
          {yearText && (
            <span className="font-mono text-[0.6rem] text-txt-secondary/70 tracking-[0.1em]">
              · {yearText}
            </span>
          )}
          {m.content_rating && (
            <span className="font-mono text-[0.6rem] text-txt-secondary tracking-[0.1em] px-1 py-[1px] border border-border rounded-sm">
              {m.content_rating}
            </span>
          )}
        </div>

        {/* Title */}
        <div className="text-[0.95rem] font-bold text-txt-primary leading-tight">
          {m.title}
        </div>
        {m.subtitle && (
          <div className="text-[0.72rem] text-txt-secondary -mt-1">{m.subtitle}</div>
        )}

        {/* Status + format row */}
        <div className="flex items-center gap-2 flex-wrap">
          <StatusPill status={m.status} />
          {m.format && (
            <span className="font-mono text-[0.6rem] text-txt-secondary tracking-[0.1em] uppercase">
              {m.format}
            </span>
          )}
          {m.resolution && !m.format && (
            <span className="font-mono text-[0.6rem] text-txt-secondary tracking-[0.1em] uppercase">
              {m.resolution}
            </span>
          )}
        </div>

        {/* Availability bar (partial / downloading) */}
        {m.on_server && m.on_server.total > 0 && (
          <AvailabilityBar
            label="ON SERVER"
            have={m.on_server.have}
            total={m.on_server.total}
            color={accent}
          />
        )}
        {m.status === "downloading" && typeof m.progress === "number" && !m.on_server && (
          <AvailabilityBar label="DOWNLOADING" have={m.progress} total={100} color={accent} />
        )}

        {/* Season / episode meta */}
        {(m.season_count || m.episode_count || m.episode_runtime) && (
          <div className="flex items-center gap-2 font-mono text-[0.65rem] text-txt-secondary">
            {m.season_count !== undefined && (
              <span>
                <span className="text-txt-primary font-semibold">{m.season_count}</span>{" "}
                {m.season_count === 1 ? "season" : "seasons"}
              </span>
            )}
            {m.episode_count !== undefined && (
              <span>
                <span className="text-txt-primary font-semibold">{m.episode_count}</span> eps
              </span>
            )}
            {m.episode_runtime && (
              <span>
                {m.season_count || m.episode_count ? "· " : ""}
                {m.episode_runtime}
              </span>
            )}
          </div>
        )}

        {/* Note */}
        {m.note && (
          <div className="text-[0.7rem] text-txt-secondary/80 italic leading-snug">
            {m.note}
          </div>
        )}

        {/* Actions */}
        <MediaActions m={m} accent={accent} />
      </div>
    </div>
  );
}

// ── Actions ─────────────────────────────────────────────

type ActionState = "idle" | "loading" | "success" | "error";

/** Resolve a tmdb_id + media_type, falling back to a title search if the
 *  agent-emitted card didn't carry one. Returns null if nothing matches. */
async function resolveTmdb(
  m: MediaCardData,
): Promise<{ tmdb_id: number; media_type: "movie" | "tv" } | null> {
  if (m.tmdb_id && m.media_type) {
    return { tmdb_id: m.tmdb_id, media_type: m.media_type };
  }
  // Fallback: search Overseerr by title; pick the closest match, preferring
  // same kind (movie vs show) if the card specified one.
  try {
    const res = await fetch(
      `/api/media/search?query=${encodeURIComponent(m.title)}&limit=10`,
    );
    if (!res.ok) return null;
    const body = (await res.json()) as { results: MediaCardData[] };
    const wantType = m.kind === "movie" ? "movie" : "tv";
    const hit =
      body.results.find((r) => r.media_type === wantType && r.tmdb_id) ??
      body.results.find((r) => r.tmdb_id);
    if (hit?.tmdb_id && hit.media_type) {
      return { tmdb_id: hit.tmdb_id, media_type: hit.media_type };
    }
    return null;
  } catch {
    return null;
  }
}

function MediaActions({ m, accent }: { m: MediaCardData; accent: string }) {
  const [state, setState] = useState<ActionState>("idle");
  const [msg, setMsg] = useState("");
  const [detail, setDetail] = useState<
    { tmdb_id: number; media_type: "movie" | "tv" } | null
  >(null);

  const primary = primaryActionFor(m.status);
  const canAct = primary.enabled; // button always shown; fallback resolves tmdb on click

  const handlePrimary = async () => {
    if (!canAct || state === "loading") return;
    setState("loading");
    setMsg("");
    try {
      const ids = await resolveTmdb(m);
      if (!ids) {
        throw new Error("No match found in Overseerr for this title");
      }
      const res = await fetch("/api/media/request", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(ids),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `${res.status} ${res.statusText}`);
      }
      const body = await res.json();
      setState("success");
      setMsg(body.request_status ? `Queued · ${body.request_status}` : "Queued");
    } catch (e: any) {
      setState("error");
      setMsg(e.message || "Request failed");
    }
  };

  const handleDetails = async () => {
    const ids = await resolveTmdb(m);
    if (ids) {
      setDetail(ids);
    } else {
      setMsg("Couldn't find this title in Overseerr");
      setState("error");
    }
  };

  return (
    <>
      <div className="flex items-center gap-2 flex-wrap pt-1">
        <button
          onClick={handlePrimary}
          disabled={!canAct || state === "loading" || state === "success"}
          className={cn(
            "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-sm",
            "font-mono text-[0.65rem] font-bold tracking-[0.08em]",
            "transition-all focus:outline-none focus:ring-1 focus:ring-accent-blue",
            canAct && state !== "success"
              ? "text-bg-primary hover:brightness-110"
              : "bg-bg-tertiary text-txt-secondary/60 border border-border cursor-not-allowed",
          )}
          style={
            canAct && state !== "success"
              ? { background: accent, border: `1px solid ${accent}` }
              : undefined
          }
        >
          <Icon.download size={10} />
          {state === "loading"
            ? "REQUESTING…"
            : state === "success"
              ? "QUEUED"
              : primary.label}
        </button>

        <button
          onClick={handleDetails}
          className={cn(
            "inline-flex items-center gap-1 px-2.5 py-1 rounded-sm",
            "font-mono text-[0.65rem] font-bold tracking-[0.08em]",
            "text-txt-secondary border border-border bg-bg-tertiary",
            "hover:text-txt-primary hover:border-txt-secondary transition-colors",
            "focus:outline-none focus:ring-1 focus:ring-accent-blue",
          )}
        >
          DETAILS
        </button>

        {msg && (
          <span
            className={cn(
              "font-mono text-[0.6rem]",
              state === "error" ? "text-terminal-red" : "text-txt-secondary",
            )}
          >
            {msg}
          </span>
        )}
      </div>

      {detail && (
        <MediaDetail
          tmdbId={detail.tmdb_id}
          mediaType={detail.media_type}
          fallback={m}
          onClose={() => setDetail(null)}
        />
      )}
    </>
  );
}

function primaryActionFor(status: MediaStatus): { label: string; enabled: boolean } {
  switch (status) {
    case "missing":
      return { label: "REQUEST DOWNLOAD", enabled: true };
    case "partial":
      return { label: "FILL THE GAPS", enabled: true };
    case "downloading":
      return { label: "DOWNLOADING…", enabled: false };
    case "available":
      return { label: "ON SERVER", enabled: false };
  }
}

// ── SeasonBreakdownCard ─────────────────────────────────
export function SeasonBreakdownCard({ data }: { data: SeasonBreakdownData }) {
  return (
    <div className="p-3.5 bg-bg-primary border border-border rounded-sm min-w-[320px]">
      <div className="font-mono text-[9px] font-bold tracking-[0.16em] uppercase text-txt-secondary mb-2">
        {data.show} · SEASONS
      </div>
      <div className="flex flex-col gap-3">
        {data.seasons.map((s) => {
          const complete = s.have === s.total;
          const color = complete ? "#33FF33" : "#FFBF00";
          return (
            <div key={s.num} className="flex flex-col gap-1.5">
              <div className="flex items-center gap-2">
                <span className="font-mono text-[0.72rem] text-txt-primary">
                  S{String(s.num).padStart(2, "0")}
                </span>
                <span
                  className="font-mono text-[10px]"
                  style={{ color }}
                >
                  {s.have}/{s.total}
                </span>
                {!complete && s.missing.length > 0 && (
                  <span className="font-mono text-[9px] text-txt-secondary">
                    missing {s.missing.join(", ")}
                  </span>
                )}
              </div>
              <div className="flex gap-[2px]">
                {Array.from({ length: s.total }).map((_, i) => {
                  const epLabel = "E" + String(i + 1).padStart(2, "0");
                  const have = !s.missing.includes(epLabel);
                  return (
                    <div
                      key={i}
                      title={epLabel + (have ? " · on server" : " · missing")}
                      className="h-2 flex-1 rounded-[1px]"
                      style={{
                        background: have ? color : "#304050",
                        boxShadow: have ? `0 0 4px ${color}` : "none",
                      }}
                    />
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── HaDeviceCard ────────────────────────────────────────

// Domain → HA service for toggle action
function haDomainAndServiceFor(entity_id: string, currentOn: boolean): {
  domain: string;
  service: string;
} | null {
  const domain = entity_id.split(".", 1)[0];
  switch (domain) {
    case "light":
    case "switch":
    case "input_boolean":
    case "fan":
    case "automation":
      return { domain, service: "toggle" };
    case "cover":
      return { domain, service: currentOn ? "close_cover" : "open_cover" };
    case "lock":
      return { domain, service: currentOn ? "unlock" : "lock" };
    case "climate":
      return { domain, service: "toggle" };
    default:
      return null;
  }
}

function DomainGlyph({ icon, color, on }: { icon?: HaDevice["icon"]; color: string; on: boolean }) {
  const style: React.CSSProperties = {
    background: on ? `${color}22` : "rgba(255,255,255,0.03)",
    border: `1px solid ${on ? `${color}66` : "rgba(255,255,255,0.08)"}`,
    color,
    boxShadow: on ? `0 0 12px -2px ${color}88, inset 0 0 12px -6px ${color}` : undefined,
  };
  const commonProps = { size: 18, className: "block" };
  let glyph: React.ReactNode;
  switch (icon) {
    case "light":
      glyph = <Icon.lightbulb {...commonProps} />;
      break;
    case "lock":
      glyph = <Icon.bell {...commonProps} />;
      break;
    case "camera":
      glyph = <Icon.film {...commonProps} />;
      break;
    case "climate":
      glyph = <Icon.bolt {...commonProps} />;
      break;
    case "garage":
      glyph = <Icon.home {...commonProps} />;
      break;
    default:
      glyph = <Icon.sparkle {...commonProps} />;
  }
  return (
    <div
      className="w-9 h-9 flex-none rounded-sm grid place-items-center transition-all"
      style={style}
    >
      {glyph}
    </div>
  );
}

function Toggle({
  on,
  color,
  disabled,
  onClick,
}: {
  on: boolean;
  color: string;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      disabled={disabled}
      onClick={onClick}
      className={cn(
        "relative w-9 h-[18px] rounded-full transition-colors flex-none cursor-pointer border-none p-0",
        "focus:outline-none focus:ring-1 focus:ring-accent-blue",
        disabled && "opacity-60 cursor-wait",
      )}
      style={{
        background: on ? color : "rgba(255,255,255,0.12)",
        boxShadow: on ? `0 0 10px -3px ${color}` : undefined,
      }}
    >
      <span
        className="absolute top-[2px] w-[14px] h-[14px] rounded-full bg-bg-primary transition-all"
        style={{ left: on ? 20 : 3 }}
      />
    </button>
  );
}

export function HaDeviceCard({ d }: { d: HaDevice }) {
  const domain = d.domain ?? d.id.split(".", 1)[0];
  const initiallyOn = d.state === "on" || d.state === "open";

  const [on, setOn] = useState(initiallyOn);
  const [brightness, setBrightness] = useState(d.brightness_pct);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [unavailable, setUnavailable] = useState(d.state === "unavailable");

  const color = unavailable
    ? "#CC0000"
    : on
      ? domain === "light"
        ? "#FFBF00"
        : "#33FF33"
      : "#7a8599";

  const handleToggle = async () => {
    if (busy || unavailable) return;
    const resolved = haDomainAndServiceFor(d.id, on);
    if (!resolved) {
      setErr("Toggle not supported for this entity");
      return;
    }
    // Optimistic flip
    const prev = on;
    setOn(!prev);
    setBusy(true);
    setErr(null);
    try {
      const res = await fetch("/api/ha/service", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          domain: resolved.domain,
          service: resolved.service,
          entity_id: d.id,
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `${res.status} ${res.statusText}`);
      }
      const body = await res.json();
      const updated = body.entity as HaDevice | undefined;
      if (updated) {
        setOn(updated.state === "on" || updated.state === "open");
        setBrightness(updated.brightness_pct);
        setUnavailable(updated.state === "unavailable");
      }
    } catch (e: any) {
      // Rollback
      setOn(prev);
      setErr(e.message || "Toggle failed");
    } finally {
      setBusy(false);
    }
  };

  const stateLabel = unavailable
    ? "OFFLINE"
    : on
      ? domain === "cover"
        ? "OPEN"
        : domain === "lock"
          ? "UNLOCKED"
          : "ON"
      : domain === "cover"
        ? "CLOSED"
        : domain === "lock"
          ? "LOCKED"
          : "OFF";

  return (
    <div className="inline-flex align-top gap-3 px-3 py-2.5 mr-2 mb-2 bg-bg-secondary border border-border rounded-sm w-[300px] max-w-full">
      <DomainGlyph icon={d.icon} color={color} on={on && !unavailable} />

      <div className="flex-1 min-w-0 flex flex-col justify-center gap-0.5">
        <div className="text-[0.82rem] font-semibold text-txt-primary truncate">
          {d.name}
        </div>
        <div className="font-mono text-[0.6rem] text-txt-secondary truncate">
          {d.area} · {d.id}
        </div>
        {err && (
          <div className="font-mono text-[0.6rem] text-terminal-red mt-0.5 truncate" title={err}>
            {err}
          </div>
        )}
      </div>

      <div className="flex items-center gap-2 flex-none">
        {typeof brightness === "number" && on && !unavailable && (
          <span className="font-mono text-[0.65rem] text-txt-secondary tabular-nums">
            {brightness}%
          </span>
        )}
        {d.detail && !brightness && (
          <span className="font-mono text-[0.65rem] text-txt-secondary">
            {d.detail}
          </span>
        )}
        <Toggle on={on && !unavailable} color={color} disabled={busy || unavailable} onClick={handleToggle} />
        <span
          className="font-mono text-[0.6rem] font-bold tracking-[0.1em] w-[46px]"
          style={{ color }}
        >
          {stateLabel}
        </span>
      </div>
    </div>
  );
}

// HandoffLine now lives in HandoffLine.tsx (uses the shared agent-registry
// for colors/glyphs). Re-export its type here for any legacy imports.
export type { HandoffInfo } from "@/components/chat/HandoffLine";
