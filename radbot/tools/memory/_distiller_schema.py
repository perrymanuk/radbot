"""Pydantic AI schema for the SemanticDistiller worker (EX8).

Defines the strict output schema enforced on the LLM:
  * `statement` — distilled implicit rule, capped at 25 words via validator.
  * `relation_to_prior` — required taxonomy of how the rule relates to
    pre-existing implicit memories.
  * `supersedes` — Qdrant point IDs of prior `implicit` rules this one
    replaces (empty for novel rules).

The Pydantic AI Agent is constructed lazily so importing this module does
not require network access or credentials.
"""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

MAX_STATEMENT_WORDS = 25

RelationToPrior = Literal["novel", "refines", "contradicts", "reinforces"]


class DistilledRule(BaseModel):
    """One implicit rule distilled from a batch of episodic memories."""

    statement: str = Field(..., description="Implicit rule, <= 25 words.")
    relation_to_prior: RelationToPrior = Field(
        ...,
        description=(
            "How this rule relates to existing implicit rules: novel, "
            "refines (narrows/strengthens), contradicts (replaces), "
            "reinforces (restates)."
        ),
    )
    supersedes: List[str] = Field(
        default_factory=list,
        description=(
            "Qdrant point IDs of prior implicit rules this one replaces. "
            "MUST be non-empty when relation_to_prior is 'refines' or "
            "'contradicts'."
        ),
    )

    @field_validator("statement")
    @classmethod
    def _statement_word_budget(cls, v: str) -> str:
        words = v.split()
        if len(words) == 0:
            raise ValueError("statement must be non-empty")
        if len(words) > MAX_STATEMENT_WORDS:
            raise ValueError(
                f"statement must be <= {MAX_STATEMENT_WORDS} words, got {len(words)}"
            )
        return v.strip()

    @field_validator("supersedes")
    @classmethod
    def _supersedes_required_for_revisions(cls, v, info):
        relation = info.data.get("relation_to_prior")
        if relation in ("refines", "contradicts") and not v:
            raise ValueError(
                f"supersedes must be non-empty when relation_to_prior='{relation}'"
            )
        return v


class DistillationResult(BaseModel):
    """Full output of one distillation pass over a batch of episodes."""

    rules: List[DistilledRule] = Field(default_factory=list)


SYSTEM_PROMPT = (
    "You distill recent episodic memories into durable implicit rules "
    "(heuristics, preferences, patterns).\n\n"
    "Hard constraints:\n"
    "- Each statement MUST be <= 25 words.\n"
    "- Set relation_to_prior to one of: novel, refines, contradicts, reinforces.\n"
    "- When refining or contradicting, populate `supersedes` with the IDs of "
    "the prior rules you are replacing (from the provided prior rules list).\n"
    "- Emit only high-signal rules. If the episodes are noise, return an "
    "empty rules list. Do NOT invent rules to fill the response."
)


def build_distiller_agent(model: str):
    """Construct a Pydantic AI Agent bound to DistillationResult.

    Imported lazily to keep this module importable without pydantic_ai
    installed (e.g. during partial test runs).
    """
    from pydantic_ai import Agent

    return Agent(
        model=model,
        result_type=DistillationResult,
        system_prompt=SYSTEM_PROMPT,
    )


def format_prompt(
    episodes: List[dict],
    prior_rules: Optional[List[dict]] = None,
) -> str:
    """Render the user prompt for the distiller agent."""
    lines = ["# Recent episodic memories", ""]
    for i, ep in enumerate(episodes, 1):
        text = (ep.get("text") or "").strip()
        ts = ep.get("timestamp") or ""
        lines.append(f"{i}. ({ts}) {text}")
    lines.append("")
    if prior_rules:
        lines.append("# Prior implicit rules (candidates for supersedes)")
        lines.append("")
        for r in prior_rules:
            rid = r.get("id") or r.get("point_id") or ""
            text = (r.get("text") or "").strip()
            lines.append(f"- id={rid} :: {text}")
        lines.append("")
    lines.append(
        "Distill implicit rules from the episodes above, revising prior rules "
        "where warranted."
    )
    return "\n".join(lines)
