"""Deterministic checks that run before the judge.

Not everything about a registry entry is a judgment call. Whether the
description changed since we last approved it, whether the publisher signed
it, whether the parameter schema is well-formed -- these are computable, and
computing them is strictly better than asking a model:

* they cannot be argued out of it by attacker-authored text
* they are exact rather than probable, so rug-pull detection stops being
  something the screener sometimes notices
* they cost nothing, which keeps the in-loop latency budget for the judgment
  that actually needs a model

The division of labour is the point. The model is left with the questions
that genuinely require reading comprehension: does this description instruct
rather than describe, does it match what the schema can do, is the requested
scope wider than the function needs.
"""

from __future__ import annotations

import re

from toolsmith.config import MAX_EVIDENCE_CHARS
from toolsmith.screening.candidate import Candidate
from toolsmith.screening.schema import Finding, FindingCode

_WS = re.compile(r"\s+")


def _normalise(text: str) -> str:
    return _WS.sub(" ", text).strip().lower()


def _clip(text: str) -> str:
    text = text.strip()
    if len(text) <= MAX_EVIDENCE_CHARS:
        return text
    return text[: MAX_EVIDENCE_CHARS - 1] + "…"


def check_description_drift(c: Candidate) -> Finding | None:
    """Rug-pull: approved once, quietly rewritten afterwards.

    Any material change is reported. Deciding whether the new wording is
    benign is the human's call at the approval card -- the point here is that
    the change is never silent.
    """
    if not c.previous_description:
        return None
    if _normalise(c.previous_description) == _normalise(c.description):
        return None
    return Finding(
        code=FindingCode.DESCRIPTION_CHANGED_SINCE_SEEN,
        severity="block",
        evidence=_clip(
            f"previously: {c.previous_description!r}\nnow: {c.description!r}"
        ),
    )


def check_provenance(c: Candidate) -> Finding | None:
    """Reported as context, not as a warning.

    Most published MCP servers are unsigned today. A warning that fires on
    almost every entry teaches users to click through warnings, which costs
    more than it buys -- so this is surfaced on the approval card and left out
    of the decision. Revisit if signing ever becomes the norm.
    """
    if c.signed:
        return None
    publisher = c.publisher or "(none declared)"
    return Finding(
        code=FindingCode.UNVERIFIED_PROVENANCE,
        severity="info",
        evidence=_clip(f"unsigned entry, publisher: {publisher}"),
    )


def check_schema_quality(c: Candidate) -> Finding | None:
    """A schema you cannot read is a schema you cannot scope."""
    props = (c.input_schema or {}).get("properties")
    if not props:
        return Finding(
            code=FindingCode.LOW_SCHEMA_QUALITY,
            severity="block",
            evidence=_clip(f"no parameter properties declared: {c.input_schema!r}"),
        )
    untyped = sorted(k for k, v in props.items() if not isinstance(v, dict) or "type" not in v)
    if untyped:
        return Finding(
            code=FindingCode.LOW_SCHEMA_QUALITY,
            severity="warn",
            evidence=_clip(f"parameters declared without a type: {', '.join(untyped)}"),
        )
    return None


CHECKS = (check_description_drift, check_provenance, check_schema_quality)


def static_findings(candidate: Candidate) -> list[Finding]:
    return [f for check in CHECKS if (f := check(candidate)) is not None]
