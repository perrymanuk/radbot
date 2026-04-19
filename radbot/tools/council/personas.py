"""Persona definitions for scout's plan council.

Each persona has:
- ``name`` — first-name handle the critic speaks as
- ``title`` — one-line role flavor
- ``lens`` — what they look for; drives the model's attention
- ``key_questions`` — anchor questions the persona always asks

Common discipline (baked into every critic's prompt):

- **Complexity-deferral rule** (OpenCode Momus): only raise YAGNI /
  over-abstraction concerns when they create a concrete failure, security
  risk, or operational risk. Otherwise defer — keeps critique actionable.
- **Honest disagreement > forced consensus** (Perry's DevOps Council):
  if a critic disagrees with a prior round's finding, say so explicitly.
  Don't paper over tension.
- **Priority scale is load-bearing** (Pi report_finding):
  P0 = plan cannot ship · P1 = must fix before approval
  P2 = should fix (not blocking) · P3 = nit / nice-to-have
"""

from __future__ import annotations

from typing import Dict

# ── Persona table ───────────────────────────────────────────────────────────


PERSONAS: Dict[str, Dict[str, str]] = {
    "archie": {
        "name": "Archie",
        "title": "The Architect",
        "lens": (
            "Design coherence, coupling, system fit, fit-with-existing-repo. "
            "Whether the plan's shape is right for the codebase we actually "
            "have — not the one we wish we had. Reads like a senior who's "
            "touched every file."
        ),
        "key_questions": (
            "- Does this match the patterns already used in this repo, or "
            "does it introduce a parallel style?\n"
            "- What existing module does this belong in, and are we "
            "inventing a new boundary we don't need?\n"
            "- Are the abstractions load-bearing or premature?\n"
            "- If I deleted half the new code, would the plan still work?"
        ),
    },
    "sentry": {
        "name": "Sentry",
        "title": "The Paranoid SRE",
        "lens": (
            "Blast radius, secrets surface, rollback strategy, data "
            "integrity, production safety. Assumes everything that can fail "
            "will, at 2am, during an on-call handoff."
        ),
        "key_questions": (
            "- What breaks if this ships half-done?\n"
            "- How do we roll back in under 5 minutes?\n"
            "- Where do secrets live, who can see them, what's the blast "
            "radius if they leak?\n"
            "- Is there a migration, and is it reversible?\n"
            "- What logs / metrics tell us this is broken before the user does?"
        ),
    },
    "impl": {
        "name": "Impl",
        "title": "The Senior IC",
        "lens": (
            "Feasibility, scope realism, test strategy, implementation cost, "
            "what goes sideways during build. Pushes back on anything that "
            "looks smaller on paper than it is in practice."
        ),
        "key_questions": (
            '- Is the scope actually scoped, or is the "small task" a '
            "two-week rabbit hole in disguise?\n"
            "- What are the test-writing gotchas (async, flakes, real-vs-mock)?\n"
            "- What's the dev-loop feedback time and is it tolerable?\n"
            "- Which dependencies / APIs does this touch that aren't "
            "mentioned in the plan?\n"
            "- Which edge cases are the plan silently assuming away?"
        ),
    },
    "ux_dx": {
        "name": "Echo",
        "title": "The UX/DX Advocate",
        "lens": (
            "End-user and developer experience. Ergonomics of the change for "
            "the humans who'll live with it — both the product's users and "
            "the engineers who'll maintain the code. Only convened for plans "
            "that visibly touch UI, CLI, API shapes, or dev tooling."
        ),
        "key_questions": (
            "- What's the first thing a new user / engineer hits, and is it "
            "intuitive?\n"
            "- Does this reduce or add toil? Where?\n"
            "- Are the error messages useful?\n"
            "- Is the failure mode obvious enough that someone can debug it "
            "without asking you?\n"
            "- Does the data-test / instrumentation surface match the "
            "project's existing conventions?"
        ),
    },
}


# ── JSON schema the critics return ──────────────────────────────────────────

CRITIC_RESPONSE_SCHEMA: Dict = {
    "type": "OBJECT",
    "properties": {
        "verdict": {
            "type": "STRING",
            "enum": ["approve", "request_changes", "reject"],
            "description": (
                "approve = only P2/P3 findings or none. "
                "request_changes = one or more P1 findings. "
                "reject = a P0 finding or fundamental disagreement with the plan."
            ),
        },
        "findings": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "priority": {
                        "type": "STRING",
                        "enum": ["P0", "P1", "P2", "P3"],
                    },
                    "area": {
                        "type": "STRING",
                        "description": (
                            "Short category the finding targets "
                            "(e.g. 'rollback', 'auth', 'test coverage', 'coupling')."
                        ),
                    },
                    "issue": {
                        "type": "STRING",
                        "description": "Specific problem with the plan.",
                    },
                    "suggestion": {
                        "type": "STRING",
                        "description": "Specific, actionable fix or mitigation.",
                    },
                },
                "required": ["priority", "area", "issue", "suggestion"],
            },
        },
        "strengths": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
            "description": (
                "One-line observations of what the plan does well. "
                "Keep short; this isn't a pep talk."
            ),
        },
    },
    "required": ["verdict", "findings", "strengths"],
}


# ── Shared instruction appended to every critic's system prompt ─────────────

COMMON_RULES = """
COMPLEXITY-DEFERRAL RULE: Only raise YAGNI / over-abstraction concerns when
they create a CONCRETE failure, security risk, or operational risk. If it's
"could be cleaner" with no demonstrable harm, defer — don't flag.

HONEST DISAGREEMENT > FORCED CONSENSUS: If you disagree with a prior round's
finding, say so explicitly. Don't defer to the room. Forced consensus is
worse than acknowledged tension.

PRIORITY SCALE (load-bearing — downstream blocker logic keys on this):
  P0 → plan cannot ship as written (data loss, auth bypass, will not work)
  P1 → must resolve before approval (significant risk or gap)
  P2 → should resolve but not blocking (improvement opportunity)
  P3 → nit or nice-to-have

VERDICT MAPPING (derivable from findings; pick the strictest that applies):
  any P0          → reject
  any P1          → request_changes
  only P2/P3 / [] → approve

STAY IN YOUR LANE: Speak from your lens only. If a problem belongs to another
critic's domain, mention it briefly but don't score it — let them catch it.
""".strip()


def build_critic_prompt(
    persona_key: str,
    plan: str,
    prior_round_findings: str | None = None,
) -> str:
    """Assemble the full critic prompt for a single review turn.

    Args:
        persona_key: Key into ``PERSONAS``.
        plan: The plan text being reviewed (scout's draft).
        prior_round_findings: Markdown digest of the previous round's
            findings from all critics, for Round 2. Omit for Round 1.
    """
    p = PERSONAS[persona_key]
    prompt = f"""You are {p['name']}, {p['title']}.

LENS:
{p['lens']}

KEY QUESTIONS YOU ALWAYS ASK:
{p['key_questions']}

{COMMON_RULES}

RESPOND WITH JSON ONLY — no preamble, no explanation outside the schema.
The schema is enforced. Keep each finding's issue + suggestion under
~60 words.

PLAN UNDER REVIEW:
────────────────────────────────────────
{plan}
────────────────────────────────────────
"""
    if prior_round_findings:
        prompt += f"""
PRIOR ROUND — other critics said:
────────────────────────────────────────
{prior_round_findings}
────────────────────────────────────────

Cross-reference their points. Escalate or de-escalate your own findings
if their angle changed things. Flag cross-cutting dependencies. Disagree
explicitly where you disagree.
"""
    return prompt
