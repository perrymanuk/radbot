"""Trigger heuristic — is this plan worth convening the council?

The council is overkill for a one-line fix. Running it on every plan burns
tokens and adds latency scout feels. We use a conservative "probably worth
reviewing" rule: plans get a council if any of these hits:

- plan touches ≥ 2 files / modules
- plan introduces a new dependency, API, credential, or integration
- plan has auth / security / secret surface
- plan touches database schema
- plan declares a migration or irreversible change

Scout reads the verdict and decides. This heuristic runs as a FunctionTool
so scout can ask for a rationale instead of silently skipping.
"""

from __future__ import annotations

import re
from typing import Any, Dict

from google.adk.tools import FunctionTool

# Keywords that elevate a plan past "trivial" — if any appear (case-insensitive),
# the council should convene. Each category is kept small and high-signal;
# the goal is "fail open toward reviewing" — false positives are fine,
# false negatives are expensive.
_RISK_KEYWORDS = {
    "auth": (
        "auth",
        "oauth",
        "token",
        "session",
        "credential",
        "secret",
        "password",
        "api key",
        "api_key",
        "permission",
        "authz",
        "authn",
    ),
    "integration": (
        "new integration",
        "new dependency",
        "new api",
        "new client",
        "new mcp server",
        "webhook",
        "third-party",
    ),
    "storage": (
        "schema",
        "migration",
        "add column",
        "alter table",
        "create table",
        "drop table",
        "new table",
        "rename column",
        "backfill",
    ),
    "deploy": (
        "nomad",
        "docker",
        "ci/cd",
        "pipeline",
        "rollout",
        "deploy",
        "release",
        "ship",
        "production",
        "irreversible",
    ),
    "security": (
        "vulnerability",
        "cve",
        "sanitize",
        "prompt injection",
        "cross-site",
        "xss",
        "csrf",
        "ssrf",
        "rce",
    ),
}


_FILE_PATH_RE = re.compile(r"`([\w./\-]+\.(?:py|ts|tsx|md|yaml|yml|json|sql|tf|hcl))`")


def _matched_keywords(text: str) -> Dict[str, list[str]]:
    lowered = text.lower()
    hits: Dict[str, list[str]] = {}
    for category, words in _RISK_KEYWORDS.items():
        matched = [w for w in words if w in lowered]
        if matched:
            hits[category] = matched
    return hits


def _count_file_mentions(plan: str) -> int:
    """Count distinct file paths mentioned in backticks.

    Underestimates when plans describe files in prose, but the signal is
    the relative count — trivial plans cite 0-1 files, substantive ones
    cite several.
    """
    return len(set(_FILE_PATH_RE.findall(plan)))


def should_convene_council(plan: str) -> Dict[str, Any]:
    """Return a structured verdict on whether scout should convene the council.

    Errs on the side of convening. A plan that doesn't deserve review will
    still pass through in ~30s with all three critics approving; a plan
    that skipped review and breaks prod is much more expensive.

    Args:
        plan: The plan text (5-role markdown or free-form draft).

    Returns:
        ``{"convene": bool, "reason": str, "signals": {...}}`` — scout can
        surface the reason to the user if she's overriding the verdict.
    """
    if not plan or len(plan.strip()) < 40:
        return {
            "convene": False,
            "reason": "plan is too short to review meaningfully",
            "signals": {"plan_chars": len(plan or "")},
        }

    file_mentions = _count_file_mentions(plan)
    risk_hits = _matched_keywords(plan)
    signals = {
        "file_mentions": file_mentions,
        "risk_categories": sorted(risk_hits.keys()),
        "risk_keywords_hit": {k: v for k, v in risk_hits.items()},
    }

    # Rule 1: two or more distinct files touched → convene.
    if file_mentions >= 2:
        return {
            "convene": True,
            "reason": f"plan touches {file_mentions} files (≥2 → council)",
            "signals": signals,
        }

    # Rule 2: any risk-surface keyword → convene.
    if risk_hits:
        return {
            "convene": True,
            "reason": (
                "plan mentions risk-surface keywords in categories: "
                + ", ".join(sorted(risk_hits.keys()))
            ),
            "signals": signals,
        }

    # Rule 3: long plan (>2000 chars) even with no keyword hits → convene,
    # because there's enough going on that something probably deserves a second pair of eyes.
    if len(plan) > 2000:
        return {
            "convene": True,
            "reason": "plan length suggests non-trivial work (>2000 chars)",
            "signals": {**signals, "plan_chars": len(plan)},
        }

    return {
        "convene": False,
        "reason": (
            "plan appears trivial (≤1 file, no risk keywords, short). "
            "Scout may still convene if she wants — this is advisory."
        ),
        "signals": {**signals, "plan_chars": len(plan)},
    }


should_convene_council_tool = FunctionTool(should_convene_council)
