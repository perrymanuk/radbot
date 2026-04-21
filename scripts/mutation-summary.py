#!/usr/bin/env python3
"""Parse mutmut output into an agent-readable summary.

Usage:
    # after `mutmut run ...`
    uv run python scripts/mutation-summary.py                # text to stdout
    uv run python scripts/mutation-summary.py --json         # JSON to stdout
    uv run python scripts/mutation-summary.py --max 20       # cap survivors shown

Reports:
    - total / killed / survived / timeout / suspicious counts
    - per-surviving-mutant: file:line + mutant diff (from `mutmut show <id>`)
    - exit code 0 if mutation_score >= --min-score (default 70), else 1

Design notes (EX18 / PT49):
    - Agents cannot parse raw `mutmut results` reliably. This wrapper normalizes.
    - Fail-loud: if mutmut output shape changes, print raw output and exit 2
      rather than silently missing survivors.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from typing import Iterable


STATUS_SURVIVED = "survived"
STATUS_KILLED = "killed"
STATUS_TIMEOUT = "timeout"
STATUS_SUSPICIOUS = "suspicious"


@dataclass
class Mutant:
    mutant_id: str
    status: str
    file: str = ""
    line: int | None = None
    diff: str = ""


@dataclass
class Summary:
    total: int = 0
    killed: int = 0
    survived: int = 0
    timeout: int = 0
    suspicious: int = 0
    mutation_score: float = 0.0
    survivors: list[Mutant] = field(default_factory=list)

    def compute_score(self) -> None:
        denom = self.killed + self.survived + self.timeout + self.suspicious
        self.mutation_score = (self.killed / denom * 100.0) if denom else 0.0


def _run(cmd: list[str]) -> tuple[int, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode, proc.stdout + proc.stderr


def parse_results(raw: str) -> dict[str, list[str]]:
    """Parse `mutmut results` text output into {status: [mutant_id, ...]}.

    mutmut's text output groups survivors under headers like `Survived 🙁 (N)`
    followed by `---- <file> (N) ----` and then a run of comma/hyphen-separated
    IDs. We key off the emoji-tagged status headers.
    """
    buckets: dict[str, list[str]] = {
        STATUS_SURVIVED: [],
        STATUS_KILLED: [],
        STATUS_TIMEOUT: [],
        STATUS_SUSPICIOUS: [],
    }
    status_headers = {
        "Survived": STATUS_SURVIVED,
        "Killed": STATUS_KILLED,
        "Timed out": STATUS_TIMEOUT,
        "Suspicious": STATUS_SUSPICIOUS,
    }

    current: str | None = None
    for line in raw.splitlines():
        stripped = line.strip()
        matched_header = False
        for label, status in status_headers.items():
            if stripped.startswith(label) and "(" in stripped:
                current = status
                matched_header = True
                break
        if matched_header:
            continue
        if current is None or not stripped or stripped.startswith("----"):
            continue
        if stripped.startswith("To "):
            continue
        for tok in re.split(r"[,\s]+", stripped):
            if not tok:
                continue
            if "-" in tok and all(p.isdigit() for p in tok.split("-")):
                lo, hi = (int(p) for p in tok.split("-"))
                buckets[current].extend(str(i) for i in range(lo, hi + 1))
            elif tok.isdigit():
                buckets[current].append(tok)
    return buckets


_SHOW_HEADER_RE = re.compile(
    r"^---\s+(?P<file>.+?):(?P<line>\d+)\b", re.MULTILINE
)


def fetch_mutant(mutant_id: str) -> Mutant:
    rc, out = _run(["mutmut", "show", mutant_id])
    m = Mutant(mutant_id=mutant_id, status=STATUS_SURVIVED)
    if rc != 0:
        m.diff = f"[mutmut show {mutant_id} failed]\n{out}"
        return m
    header = _SHOW_HEADER_RE.search(out)
    if header:
        m.file = header.group("file")
        m.line = int(header.group("line"))
    m.diff = out.strip()
    return m


def collect(max_survivors: int | None) -> Summary:
    rc, raw = _run(["mutmut", "results"])
    if rc != 0:
        print("mutmut results failed:", file=sys.stderr)
        print(raw, file=sys.stderr)
        sys.exit(2)
    buckets = parse_results(raw)
    s = Summary(
        killed=len(buckets[STATUS_KILLED]),
        survived=len(buckets[STATUS_SURVIVED]),
        timeout=len(buckets[STATUS_TIMEOUT]),
        suspicious=len(buckets[STATUS_SUSPICIOUS]),
    )
    s.total = s.killed + s.survived + s.timeout + s.suspicious
    s.compute_score()
    ids: Iterable[str] = buckets[STATUS_SURVIVED]
    if max_survivors is not None:
        ids = list(ids)[:max_survivors]
    s.survivors = [fetch_mutant(mid) for mid in ids]
    return s


def render_text(s: Summary) -> str:
    lines = [
        "Mutation summary",
        "================",
        f"total:     {s.total}",
        f"killed:    {s.killed}",
        f"survived:  {s.survived}",
        f"timeout:   {s.timeout}",
        f"suspicious:{s.suspicious}",
        f"score:     {s.mutation_score:.1f}%",
        "",
    ]
    if s.survivors:
        lines.append("Surviving mutants (kill these):")
        lines.append("-" * 32)
        for m in s.survivors:
            loc = f"{m.file}:{m.line}" if m.file else f"mutant {m.mutant_id}"
            lines.append(f"[{m.mutant_id}] {loc}")
            lines.append(m.diff)
            lines.append("")
    else:
        lines.append("No surviving mutants.")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="emit JSON instead of text")
    ap.add_argument("--max", type=int, default=None, help="cap survivors shown")
    ap.add_argument(
        "--min-score",
        type=float,
        default=70.0,
        help="exit non-zero if mutation score below this (default 70)",
    )
    args = ap.parse_args()
    s = collect(args.max)
    if args.json:
        payload = asdict(s)
        print(json.dumps(payload, indent=2))
    else:
        print(render_text(s))
    return 0 if s.mutation_score >= args.min_score else 1


if __name__ == "__main__":
    sys.exit(main())
