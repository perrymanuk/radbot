#!/usr/bin/env python3
"""Compare two screenshot sets via Claude Code CLI and emit a 0-N quality score.

Drives the `claude` CLI via subprocess rather than the `anthropic` SDK directly.
This lets the tool use whatever auth the Claude Code CLI supports (API key,
subscription OAuth, custom endpoint) without the SDK's strict key format check.

Inputs:
  --before <dir>     Directory of baseline screenshots (e.g. main branch)
  --after <dir>      Directory of candidate screenshots (e.g. PR head)
  --output-json      Path to write structured verdict JSON
  --output-md        Path to write rich markdown summary (for PR sticky comment)
  --max-score        Cap for the emitted score (default 20)
  --pr-context       Optional short blurb describing what the PR changes

Output:
  - Writes structured JSON verdict to --output-json
  - Writes a markdown table with per-screenshot verdicts to --output-md
  - Writes 'score=N' to GITHUB_OUTPUT (if set)
  - Writes a short summary to stdout (suitable for $GITHUB_STEP_SUMMARY)

The judge classifies each pair as one of:
  - unchanged  — pixel-equivalent or trivial anti-aliasing
  - changed    — intentional polish (spacing, copy, accents); does NOT penalize
  - regression — broken layout, missing elements, unexpected overlap
  - error      — page blank / console overlay / unrenderable
Only `regression` and `error` reduce the score. `changed` is noted but free.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
from typing import Any

PROMPT_HEADER = """You are a senior front-end engineer doing visual-regression review.

You will receive a list of before/after screenshot pairs from the same pages of a web app. For each pair, Read both PNG files and classify the visual difference.

For each page, return one of:
  - "unchanged"  — pixel-identical or negligible rendering differences
  - "changed"    — intentional visual change aligned with PR intent (does NOT reduce score)
  - "regression" — unexpected broken layout, missing critical elements, overlap
  - "error"      — page is blank, shows console error overlay, or is unrenderable

If a page is new (no "before" file exists on disk), evaluate the "after" alone and mark it "changed" with a short note.

Only "regression" and "error" reduce the score. "changed" pages should be noted in the summary but must NOT lower the score.

Scoring guide (aggregate across all pairs):
  100   no regressions, no errors
  95    trivial unintentional diffs only
  80    a few minor regressions
  60    one notable regression
  40    multiple or significant regressions
  0     page crashes / unrenderable

Respond with ONLY this JSON object (no prose, no markdown fences):
{
  "score": <integer 0-100>,
  "summary": "<one-sentence overall assessment>",
  "pages": [
    {"name": "<screenshot-name>", "status": "unchanged|changed|regression|error", "note": "<one-line explanation>"}
  ]
}
"""


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--before", required=True, type=pathlib.Path)
    p.add_argument("--after", required=True, type=pathlib.Path)
    p.add_argument("--output-json", required=True, type=pathlib.Path)
    p.add_argument("--output-md", type=pathlib.Path)
    p.add_argument("--max-score", type=int, default=20)
    p.add_argument("--pr-context", default="")
    p.add_argument("--timeout", type=int, default=600)
    return p.parse_args()


def build_prompt(
    before_dir: pathlib.Path,
    after_dir: pathlib.Path,
    names: list[str],
    before_pngs: dict[str, pathlib.Path],
    after_pngs: dict[str, pathlib.Path],
    pr_context: str,
) -> str:
    lines = [PROMPT_HEADER, ""]
    if pr_context:
        lines.append("## PR Context")
        lines.append(pr_context)
        lines.append("")
    lines.append("## Screenshot pairs")
    lines.append(f"Before (baseline) dir: {before_dir}")
    lines.append(f"After (PR) dir:        {after_dir}")
    lines.append("")
    for name in names:
        before = before_pngs.get(name)
        after = after_pngs.get(name)
        lines.append(f"### {name}")
        lines.append(f"  Before: {before if before else '(missing — new page)'}")
        lines.append(f"  After:  {after if after else '(missing — page removed)'}")
    lines.append("")
    lines.append(
        "Use the Read tool to view each before and after PNG, then produce the JSON verdict."
    )
    return "\n".join(lines)


def _build_auth_env() -> dict[str, str]:
    """Reuse the same auth pattern as radbot's claude_code_client.

    Reads ANTHROPIC_API_KEY from the environment (set by the workflow from
    the `ANTHROPIC_API_KEY` secret) and routes it by prefix:
      - `sk-ant-api*`  → keep as ANTHROPIC_API_KEY (standard API-key flow).
      - anything else  → treat as an OAuth / setup token: unset
        ANTHROPIC_API_KEY (its presence disables OAuth mode in the CLI),
        set CLAUDE_CODE_OAUTH_TOKEN, and stash the token at
        ~/.claude/remote/.oauth_token where the CLI reads it.

    This matches the behavior of `ClaudeCodeClient._run_process` at
    radbot/tools/claude_code/claude_code_client.py — one user was pasting
    an OAuth token into the ANTHROPIC_API_KEY secret and getting
    "Invalid API key" because the CLI was treating it as an SDK key.
    """
    env = os.environ.copy()
    token = env.get("ANTHROPIC_API_KEY") or env.get("CLAUDE_CODE_OAUTH_TOKEN")
    if not token:
        return env

    if token.startswith("sk-ant-api"):
        env["ANTHROPIC_API_KEY"] = token
        env.pop("CLAUDE_CODE_OAUTH_TOKEN", None)
    else:
        # OAuth / setup token path — ANTHROPIC_API_KEY must NOT be set.
        env.pop("ANTHROPIC_API_KEY", None)
        env["CLAUDE_CODE_OAUTH_TOKEN"] = token
        _write_oauth_token_file(token)

    # Running as root in GH Actions runner; required for --dangerously-skip-permissions.
    try:
        if os.getuid() == 0:
            env["IS_SANDBOX"] = "1"
    except AttributeError:
        pass
    return env


def _write_oauth_token_file(token: str) -> None:
    """Stash the OAuth token where the CLI reads it for headless auth."""
    try:
        home = pathlib.Path.home()
        remote_dir = home / ".claude" / "remote"
        remote_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
        stale_api_key = remote_dir / ".api_key"
        if stale_api_key.exists():
            stale_api_key.unlink()
        token_path = remote_dir / ".oauth_token"
        token_path.write_text(token)
        token_path.chmod(0o600)
    except Exception as e:
        sys.stderr.write(f"WARN: failed to write OAuth token file: {e}\n")


def _ensure_onboarding_complete() -> None:
    """Pre-set the flags that otherwise cause interactive prompts in CI."""
    try:
        home = pathlib.Path.home()
        claude_json = home / ".claude.json"
        data: dict[str, Any] = {}
        if claude_json.exists():
            try:
                data = json.loads(claude_json.read_text())
            except Exception:
                data = {}
        if not data.get("hasCompletedOnboarding"):
            data["hasCompletedOnboarding"] = True
            claude_json.write_text(json.dumps(data, indent=2))
            claude_json.chmod(0o600)

        settings_json = home / ".claude" / "settings.json"
        settings: dict[str, Any] = {}
        if settings_json.exists():
            try:
                settings = json.loads(settings_json.read_text())
            except Exception:
                settings = {}
        if not settings.get("skipDangerousModePermissionPrompt"):
            settings["skipDangerousModePermissionPrompt"] = True
            settings_json.parent.mkdir(parents=True, exist_ok=True)
            settings_json.write_text(json.dumps(settings, indent=2))
    except Exception as e:
        sys.stderr.write(f"WARN: onboarding prep failed: {e}\n")


def run_claude(prompt: str, timeout: int) -> str:
    """Invoke `claude -p` with a prompt on stdin and return its stdout."""
    _ensure_onboarding_complete()
    env = _build_auth_env()

    cmd = [
        "claude",
        "-p",
        "--allowed-tools",
        "Read",
        "--max-turns",
        "30",
        "--dangerously-skip-permissions",
    ]
    try:
        result = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=env,
        )
    except FileNotFoundError:
        raise RuntimeError(
            "`claude` CLI not found on PATH. Install with: "
            "npm install -g @anthropic-ai/claude-code"
        )
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"claude CLI timed out after {timeout}s") from e

    if result.returncode != 0:
        # Claude CLI often writes diagnostic info to stdout even on failure
        stderr = (result.stderr or "").strip()[:2000]
        stdout = (result.stdout or "").strip()[:2000]
        parts: list[str] = [f"claude CLI exited {result.returncode}"]
        if stderr:
            parts.append(f"stderr: {stderr}")
        if stdout:
            parts.append(f"stdout: {stdout}")
        if not stderr and not stdout:
            parts.append("(no output on either stream)")
        raise RuntimeError(" — ".join(parts))
    return result.stdout or ""


def _preflight() -> None:
    """Surface a clear error up-front if the CLI or API key is missing."""
    token = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get(
        "CLAUDE_CODE_OAUTH_TOKEN"
    )
    if not token:
        sys.stderr.write(
            "WARN: neither ANTHROPIC_API_KEY nor CLAUDE_CODE_OAUTH_TOKEN set. "
            "Claude CLI will fail to auth.\n"
        )
    else:
        kind = "api_key" if token.startswith("sk-ant-api") else "oauth_token"
        sys.stderr.write(
            f"Auth: {kind} ({token[:10]}…), "
            f"{'ANTHROPIC_API_KEY' if kind == 'api_key' else 'CLAUDE_CODE_OAUTH_TOKEN'} path.\n"
        )
    try:
        ver = subprocess.run(
            ["claude", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        sys.stderr.write(f"claude CLI: {(ver.stdout or ver.stderr).strip()[:200]}\n")
    except FileNotFoundError:
        sys.stderr.write(
            "ERROR: `claude` CLI not found on PATH. "
            "Install with: npm install -g @anthropic-ai/claude-code\n"
        )
    except Exception as e:
        sys.stderr.write(f"WARN: claude --version failed: {e}\n")


_JSON_OBJ_RE = re.compile(
    r"\{(?:[^{}\[\]]|\[(?:[^\[\]]|\[(?:[^\[\]])*\])*\]|\"(?:[^\"\\]|\\.)*\")*\}",
    re.DOTALL,
)


def extract_verdict(text: str) -> dict[str, Any] | None:
    """Pull a JSON object with a `score` field out of Claude's mixed output."""
    stripped = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        obj = json.loads(stripped)
        if isinstance(obj, dict) and "score" in obj:
            return obj
    except json.JSONDecodeError:
        pass
    for candidate in _JSON_OBJ_RE.findall(text):
        try:
            obj = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and "score" in obj:
            return obj
    return None


STATUS_ICONS = {
    "unchanged": "✅",
    "changed": "ℹ️",
    "regression": "❌",
    "error": "⚠️",
    "added": "➕",
    "removed": "➖",
}


def render_markdown(
    score: int,
    max_score: int,
    overall_summary: str,
    pages: list[dict[str, Any]],
) -> str:
    regressions = [p for p in pages if p.get("status") == "regression"]
    errors = [p for p in pages if p.get("status") == "error"]
    changed = [p for p in pages if p.get("status") in ("changed", "added", "removed")]
    unchanged = [p for p in pages if p.get("status") == "unchanged"]

    lines: list[str] = []
    lines.append(f"**Visual regression: {score} / {max_score}**")
    if overall_summary:
        lines.append("")
        lines.append(f"> {overall_summary}")
    lines.append("")

    noteworthy = regressions + errors + changed
    if noteworthy:
        lines.append("| Page | Status | Notes |")
        lines.append("|---|---|---|")
        for p in noteworthy:
            status = p.get("status", "?")
            icon = STATUS_ICONS.get(status, "❓")
            note = (p.get("note", "") or "").replace("|", "\\|")[:200]
            lines.append(f"| `{p.get('name', '?')}` | {icon} {status} | {note} |")
        lines.append("")

    if unchanged:
        names = ", ".join(f"`{p.get('name', '?')}`" for p in unchanged)
        lines.append(
            f"<details><summary>{len(unchanged)} unchanged page"
            f"{'' if len(unchanged) == 1 else 's'}</summary>\n\n{names}\n\n</details>"
        )
        lines.append("")

    parts: list[str] = []
    if unchanged:
        parts.append(f"{len(unchanged)} unchanged")
    if changed:
        parts.append(f"{len(changed)} changed")
    if regressions:
        parts.append(f"{len(regressions)} regression{'s' if len(regressions) != 1 else ''}")
    if errors:
        parts.append(f"{len(errors)} error{'s' if len(errors) != 1 else ''}")
    if parts:
        lines.append(f"**Summary:** {' · '.join(parts)}")

    return "\n".join(lines)


def main() -> int:
    args = parse_args()

    before_pngs = (
        {p.name: p for p in args.before.glob("*.png")} if args.before.exists() else {}
    )
    after_pngs = (
        {p.name: p for p in args.after.glob("*.png")} if args.after.exists() else {}
    )
    names = sorted(set(before_pngs) | set(after_pngs))

    if not names:
        sys.stderr.write("No screenshots found in either directory; emitting 0.\n")
        args.output_json.write_text(
            json.dumps(
                {
                    "score": 0,
                    "max_score": args.max_score,
                    "pairs": [],
                    "reason": "no screenshots",
                },
                indent=2,
            )
        )
        if args.output_md:
            args.output_md.write_text(
                f"**Visual regression: 0 / {args.max_score}**\n\nNo screenshots captured.\n"
            )
        print(f"# Visual regression\nNo screenshots captured — score 0/{args.max_score}.")
        _write_gh_output("score", "0")
        return 0

    prompt = build_prompt(
        args.before, args.after, names, before_pngs, after_pngs, args.pr_context
    )

    _preflight()
    sys.stderr.write(
        f"Evaluating {len(names)} screenshot(s) via claude CLI "
        f"(prompt {len(prompt)} chars, timeout {args.timeout}s)…\n"
    )
    try:
        raw = run_claude(prompt, args.timeout)
    except RuntimeError as e:
        sys.stderr.write(f"Claude CLI failed: {e}\n")
        error_msg = str(e)[:500]
        args.output_json.write_text(
            json.dumps(
                {
                    "score": 0,
                    "max_score": args.max_score,
                    "error": error_msg,
                    "pairs": [],
                },
                indent=2,
            )
        )
        if args.output_md:
            args.output_md.write_text(
                f"**Visual regression: 0 / {args.max_score}** — judge failed\n\n"
                f"```\n{error_msg}\n```\n"
            )
        print(f"# Visual regression\nJudge error — score 0/{args.max_score}:\n\n{error_msg}")
        _write_gh_output("score", "0")
        return 0

    verdict = extract_verdict(raw)
    if verdict is None:
        sys.stderr.write("No valid JSON found in Claude output.\n")
        preview = raw.strip()[:500]
        args.output_json.write_text(
            json.dumps(
                {
                    "score": 0,
                    "max_score": args.max_score,
                    "error": "no JSON in response",
                    "raw_preview": preview,
                    "pairs": [],
                },
                indent=2,
            )
        )
        if args.output_md:
            args.output_md.write_text(
                f"**Visual regression: 0 / {args.max_score}** — judge produced no JSON\n\n"
                f"<details><summary>Raw response preview</summary>\n\n"
                f"```\n{preview}\n```\n\n</details>\n"
            )
        print(f"# Visual regression\nNo JSON in judge response — score 0/{args.max_score}.")
        _write_gh_output("score", "0")
        return 0

    raw_score = verdict.get("score")
    if not isinstance(raw_score, (int, float)):
        raw_score = 0
    score_pct = max(0, min(100, int(raw_score)))
    score = round(score_pct / 100 * args.max_score)

    pages_raw = verdict.get("pages") if isinstance(verdict.get("pages"), list) else []
    pages: list[dict[str, Any]] = []
    seen = set()
    for p in pages_raw:
        if not isinstance(p, dict):
            continue
        name = str(p.get("name") or "")
        status = str(p.get("status") or "").strip().lower() or "changed"
        if status not in {"unchanged", "changed", "regression", "error", "added", "removed"}:
            status = "changed"
        note = str(p.get("note") or "")
        pages.append({"name": name, "status": status, "note": note})
        seen.add(name)

    # Synthesize entries for any screenshot names the judge skipped
    for name in names:
        if name in seen:
            continue
        if name not in before_pngs:
            pages.append(
                {"name": name, "status": "added", "note": "new screenshot (no baseline)"}
            )
        elif name not in after_pngs:
            pages.append(
                {"name": name, "status": "removed", "note": "screenshot disappeared in PR"}
            )
        else:
            pages.append(
                {"name": name, "status": "changed", "note": "not reviewed by judge"}
            )

    summary_text = str(verdict.get("summary") or "")

    args.output_json.write_text(
        json.dumps(
            {
                "score": score,
                "max_score": args.max_score,
                "score_pct": score_pct,
                "summary": summary_text,
                "pages": pages,
            },
            indent=2,
        )
    )

    md = render_markdown(score, args.max_score, summary_text, pages)
    if args.output_md:
        args.output_md.write_text(md + "\n")

    # Short stdout for $GITHUB_STEP_SUMMARY
    print("# Visual regression")
    print()
    print(md)

    _write_gh_output("score", str(score))
    return 0


def _write_gh_output(key: str, value: str) -> None:
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write(f"{key}={value}\n")


if __name__ == "__main__":
    sys.exit(main())
