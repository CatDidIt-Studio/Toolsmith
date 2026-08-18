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

    Reported as `warn`, not `block`. The check can prove the text moved; it
    cannot tell a new exfiltration path from a clearer sentence, and treating
    those alike would block half the healthy servers in a registry the first
    time they improved their docs. What `warn` buys is that drift can never be
    silent -- it always returns to the approval card.

    Judging whether the *new* wording is dangerous is the screener's job, and
    if it is, that finding blocks on its own merits.
    """
    if not c.previous_description:
        return None
    if _normalise(c.previous_description) == _normalise(c.description):
        return None
    return Finding(
        code=FindingCode.DESCRIPTION_CHANGED_SINCE_SEEN,
        severity="warn",
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
    untyped = sorted(k for k, v in props.items() if not _declares_a_type(v))
    if untyped:
        return Finding(
            code=FindingCode.LOW_SCHEMA_QUALITY,
            severity="warn",
            evidence=_clip(f"parameters declared without a type: {', '.join(untyped)}"),
        )
    return None


_AFFILIATION_CLAIM = re.compile(
    r"\b(official|officially|verified|first[- ]party|authoris?ed|endorsed)\b",
    re.IGNORECASE,
)


def check_provenance_claim(c: Candidate) -> Finding | None:
    """An unsigned entry that calls itself official.

    Being unsigned is unremarkable. Being unsigned while claiming an
    affiliation is a different act, and it is the shape typosquatting takes in
    a registry -- a near-miss publisher name plus the word "official" doing
    the work a signature should be doing.
    """
    if c.signed:
        return None
    match = _AFFILIATION_CLAIM.search(c.description)
    if not match:
        return None
    return Finding(
        code=FindingCode.PROVENANCE_CLAIM_UNSUPPORTED,
        severity="block",
        evidence=_clip(
            f"claims {match.group(0)!r} but carries no signature; "
            f"publisher: {c.publisher or '(none declared)'}"
        ),
    )


# The ways a JSON Schema property can legitimately say what it holds. Only
# `type` is the obvious one, and requiring it alone rejects ordinary schemas:
# an optional typed parameter compiles to `anyOf: [{...}, {"type": "null"}]`
# with no `type` at the top, which is what Pydantic emits for `list[str] |
# None` and therefore what most MCP servers actually publish.
_TYPE_KEYS = ("type", "anyOf", "oneOf", "allOf", "$ref", "enum", "const")


def _declares_a_type(spec: object) -> bool:
    return isinstance(spec, dict) and any(key in spec for key in _TYPE_KEYS)


CHECKS = (
    check_description_drift,
    check_provenance,
    check_provenance_claim,
    check_schema_quality,
)


def static_findings(candidate: Candidate) -> list[Finding]:
    return [f for check in CHECKS if (f := check(candidate)) is not None]


_TLS_FAILURE = re.compile(
    r"CERTIFICATE_VERIFY_FAILED|SSLError|SSLCertVerificationError|self[- ]signed",
    re.IGNORECASE,
)


def probe_findings(result) -> list[Finding]:
    """Findings that only exist once you have tried to connect.

    These are not judgments about what a server claims -- they are facts about
    what happened when we reached for it, and none of them are visible from
    registry metadata. The registry lists servers as active that do not answer
    at all, and lists endpoints whose certificates cannot be verified.
    """
    findings: list[Finding] = []
    error = result.error or ""

    if not result.ok:
        if _TLS_FAILURE.search(error):
            findings.append(
                Finding(
                    code=FindingCode.TRANSPORT_UNTRUSTED,
                    severity="block",
                    # Nothing this server said can be trusted, because there is
                    # no way to establish that this server said it.
                    evidence=_clip(f"{result.endpoint}: {error}"),
                )
            )
        else:
            findings.append(
                Finding(
                    code=FindingCode.SERVER_UNREACHABLE,
                    severity="block",
                    evidence=_clip(f"{result.endpoint}: {error}"),
                )
            )
        return findings

    if result.unstable_listing:
        findings.append(
            Finding(
                code=FindingCode.UNSTABLE_TOOL_LISTING,
                severity="block",
                evidence=_clip(
                    f"{result.endpoint} returned a different tool list on the "
                    "second consecutive call"
                ),
            )
        )

    return findings
