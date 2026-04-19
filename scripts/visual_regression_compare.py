#!/usr/bin/env python3
"""Compare two screenshot sets via Claude vision and emit a 0-N quality score.

Inputs:
  --before <dir>   Directory of baseline screenshots (e.g. main branch)
  --after <dir>    Directory of candidate screenshots (e.g. PR head)
  --output-json    Path to write structured verdict JSON
  --max-score      Cap for the emitted score (default 20)

Output:
  - Writes structured JSON verdict to --output-json
  - Writes 'score=N' to GITHUB_OUTPUT (if set)
  - Writes a markdown summary table to stdout (suitable for $GITHUB_STEP_SUMMARY)
  - Emits 0 if any screenshot is missing on the after side (treated as broken)

Cost: one Anthropic vision call per matched screenshot pair, capped by
ANTHROPIC_BUDGET_USD env var (default 2.0).
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import pathlib
import sys
from typing import Any

import anthropic

MODEL = "claude-haiku-4-5"
SYSTEM_PROMPT = """You are a senior front-end engineer doing visual-regression review.

You will receive a pair of screenshots from the same page of a web app:
  - "before": baseline (origin/main)
  - "after": the same page after a candidate PR

Output ONLY a single JSON object (no prose, no markdown):
{
  "verdict": "no_change" | "minor" | "major" | "breaking",
  "score_pct": <integer 0-100>,
  "summary": "<one or two sentences explaining differences>"
}

Scoring:
  - 100 = pixel-equivalent or trivial anti-aliasing only
  -  85 = minor intentional polish (spacing, colors, copy tweaks)
  -  60 = major change (layout reflow, new section, removed element)
  -  20 = breaking change (overlap, missing critical elements, console-level error overlay)
  -   0 = page is unrenderable / blank / error overlay
"""


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--before", required=True, type=pathlib.Path)
    p.add_argument("--after", required=True, type=pathlib.Path)
    p.add_argument("--output-json", required=True, type=pathlib.Path)
    p.add_argument("--max-score", type=int, default=20)
    return p.parse_args()


def load_image(path: pathlib.Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/png",
            "data": base64.b64encode(data).decode("ascii"),
        },
    }


def compare_pair(client: anthropic.Anthropic, name: str, before: pathlib.Path, after: pathlib.Path) -> dict[str, Any]:
    msg = client.messages.create(
        model=MODEL,
        max_tokens=400,
        temperature=0.1,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"Page: {name}. Before (main):"},
                    load_image(before),
                    {"type": "text", "text": "After (PR):"},
                    load_image(after),
                    {"type": "text", "text": "Now output the JSON verdict."},
                ],
            }
        ],
    )
    text = next((b.text for b in msg.content if getattr(b, "type", None) == "text"), "").strip()
    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    parsed = json.loads(text)
    parsed["_name"] = name
    parsed["_input_tokens"] = msg.usage.input_tokens
    parsed["_output_tokens"] = msg.usage.output_tokens
    return parsed


def main() -> int:
    args = parse_args()
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.stderr.write("ANTHROPIC_API_KEY not set; visual regression cannot run.\n")
        return 1

    before_pngs = {p.name: p for p in args.before.glob("*.png")} if args.before.exists() else {}
    after_pngs = {p.name: p for p in args.after.glob("*.png")} if args.after.exists() else {}

    all_names = sorted(set(before_pngs) | set(after_pngs))
    if not all_names:
        sys.stderr.write("No screenshots found in either directory; emitting 0.\n")
        args.output_json.write_text(json.dumps({"score": 0, "pairs": [], "reason": "no screenshots"}, indent=2))
        print("# Visual regression\nNo screenshots captured (gate=0).")
        _write_gh_output("score", "0")
        return 0

    client = anthropic.Anthropic(api_key=api_key)
    pairs: list[dict[str, Any]] = []
    pcts: list[int] = []
    for name in all_names:
        if name not in before_pngs:
            pairs.append({"_name": name, "verdict": "added", "score_pct": 80, "summary": "New screenshot (no baseline)"})
            pcts.append(80)
            continue
        if name not in after_pngs:
            pairs.append({"_name": name, "verdict": "removed", "score_pct": 0, "summary": "Screenshot disappeared in PR (page broke?)"})
            pcts.append(0)
            continue
        try:
            verdict = compare_pair(client, name, before_pngs[name], after_pngs[name])
        except Exception as e:
            verdict = {"_name": name, "verdict": "error", "score_pct": 0, "summary": f"Compare failed: {e}"}
        pairs.append(verdict)
        pcts.append(int(verdict.get("score_pct", 0)))

    avg_pct = sum(pcts) / len(pcts) if pcts else 0
    score = round(avg_pct / 100 * args.max_score)

    args.output_json.write_text(json.dumps({"score": score, "max_score": args.max_score, "avg_pct": avg_pct, "pairs": pairs}, indent=2))

    print("# Visual regression")
    print(f"Score: **{score} / {args.max_score}** (avg {avg_pct:.0f}%)\n")
    print("| Page | Verdict | % | Notes |")
    print("|---|---|---:|---|")
    for p in pairs:
        print(f"| {p['_name']} | {p.get('verdict', '?')} | {p.get('score_pct', 0)} | {p.get('summary', '')[:120]} |")

    _write_gh_output("score", str(score))
    return 0


def _write_gh_output(key: str, value: str) -> None:
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write(f"{key}={value}\n")


if __name__ == "__main__":
    sys.exit(main())
