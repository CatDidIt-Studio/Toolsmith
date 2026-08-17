"""The contract that crosses the trust boundary.

Everything the screener sees is attacker-controlled: a third-party MCP
server's tool descriptions are, in practice, a self-authored resume. The
screener therefore returns *only* this schema -- never free-form prose that
would flow back into the orchestrator's prompt.

The split matters. `Verdict.for_orchestrator()` is the narrow, enum-only view
the credentialed agent is allowed to read. The evidence strings exist for the
human approval card and are never fed to a model again.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from toolsmith.config import MAX_EVIDENCE_CHARS


class FindingCode(str, Enum):
    """Failure modes worth naming. This list is the product.

    Everything here is derived from how MCP servers actually misbehave, not
    from generic security taxonomy.
    """

    # The description tells the reading model to do something.
    INJECTION_IN_DESCRIPTION = "injection_in_description"
    # Description promises one thing, the JSON schema does another.
    DESCRIPTION_SCHEMA_MISMATCH = "description_schema_mismatch"
    # Asks for far more than the task needs (the classic GitHub `repo` scope).
    EXCESSIVE_SCOPE = "excessive_scope"
    # Description changed after the version we last saw -- rug-pull shape.
    DESCRIPTION_CHANGED_SINCE_SEEN = "description_changed_since_seen"
    # Name/description collides with an already-attached tool, inviting the
    # model to route calls to the wrong one. Confused-deputy setup.
    SHADOWS_EXISTING_TOOL = "shadows_existing_tool"
    # Unparseable, untyped, or empty parameter schema.
    LOW_SCHEMA_QUALITY = "low_schema_quality"
    # No signature, no provenance, anonymous publisher.
    UNVERIFIED_PROVENANCE = "unverified_provenance"
    # Claims an affiliation it cannot back -- "official", "verified" -- while
    # carrying no signature. Distinct from merely being unsigned: most of the
    # registry is unsigned, but only some of it lies about that.
    PROVENANCE_CLAIM_UNSUPPORTED = "provenance_claim_unsupported"
    # Server failed or misbehaved during the isolated trial call.
    SANDBOX_TRIAL_FAILED = "sandbox_trial_failed"
    # The connection itself could not be trusted -- an unverifiable or
    # self-signed certificate means you cannot know who answered.
    TRANSPORT_UNTRUSTED = "transport_untrusted"
    # Listed as available, did not answer.
    SERVER_UNREACHABLE = "server_unreachable"
    # Two consecutive listings disagreed, so the tools screened are not
    # reliably the tools that would be called.
    UNSTABLE_TOOL_LISTING = "unstable_tool_listing"


Severity = Literal["info", "warn", "block"]
Decision = Literal["pass", "warn", "block"]


class Finding(BaseModel):
    code: FindingCode
    severity: Severity
    # Required, and required to be a verbatim quote from the entry being
    # judged. This is not just for the card: forcing the screener to point at
    # the exact text that triggered a finding is what stops it from emitting
    # plausible-sounding findings it cannot actually support.
    #
    # Human-facing only. Capped, and never returned to a model.
    evidence: str = Field(min_length=1, max_length=MAX_EVIDENCE_CHARS)


class Verdict(BaseModel):
    """What the screener is allowed to say."""

    decision: Decision
    findings: list[Finding] = Field(default_factory=list)
    # Scopes the candidate asked for, verbatim.
    requested_scopes: list[str] = Field(default_factory=list)
    # Minimum set that still completes the task. The delta between these two
    # lists is what the approval card puts in front of the user.
    granted_scopes: list[str] = Field(default_factory=list)

    def for_orchestrator(self) -> dict[str, object]:
        """The narrow view the credentialed agent may read.

        Deliberately drops every attacker-authored string. If the screener is
        successfully injected, the blast radius is this dict.
        """
        return {
            "decision": self.decision,
            "granted_scopes": list(self.granted_scopes),
            "finding_codes": [f.code.value for f in self.findings],
        }

    @property
    def blocked(self) -> bool:
        return self.decision == "block"
