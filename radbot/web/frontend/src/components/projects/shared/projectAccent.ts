/** Deterministic per-project accent colors, assigned by hashing ref_code.
 * Keeps visual wayfinding consistent across sessions without needing a
 * stored metadata.accent. */

export const ACCENT_PALETTE = [
  "#ff7849", // sunset
  "#a884ff", // violet
  "#ff3d7f", // magenta
  "#5ec0ff", // sky
  "#ffb347", // amber
  "#7dffb5", // crt
  "#ff9966", // peach
  "#b088ff", // lilac
  "#66ccff", // cyan
] as const;

export function accentFor(refCode: string): string {
  let h = 0;
  for (let i = 0; i < refCode.length; i++) {
    h = (h * 31 + refCode.charCodeAt(i)) | 0;
  }
  const idx = ((h % ACCENT_PALETTE.length) + ACCENT_PALETTE.length) % ACCENT_PALETTE.length;
  return ACCENT_PALETTE[idx];
}
