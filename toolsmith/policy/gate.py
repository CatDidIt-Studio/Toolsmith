"""When a task does not need to be asked about.

One approval instead of five is the point of this product. Zero, for the
right tasks, is the next step -- but only if "the right tasks" is a rule
someone can read, argue with, and see applied, rather than a convenience that
quietly grows.

So the gate is written as a small set of reasons to stop, and a task passes
only when none of them apply. Adding a reason narrows what runs unattended;
nothing here can widen it by accident.

Two rules carry most of the weight.

Attaching a tool is never automatic. It does not matter how harmless the
permission looks -- deciding to trust a server nobody has run before is the
decision this whole system exists to put in front of a person, and a policy
that skipped it would have removed the product to save a click.

Anything that writes is never automatic. Reading the wrong thing is a
privacy problem and can be undone by deleting it; writing the wrong thing
changes the world on someone's behalf.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from toolsmith.approval.scopes import risk_rank
from toolsmith.planning.schema import TaskPlan

# Permissions that only read, and only from one named resource. Anything not
# on this list requires a person, including permissions that are probably
# harmless -- an allowlist fails closed when it is out of date, which is the
# direction to fail in.
AUTO_SAFE_SCOPES = frozenset(
    {"issues:read", "contents:read", "metadata:read"}
)

MAX_AUTO_RISK = "low"


@dataclass(frozen=True)
class PolicyDecision:
    """Whether a person has to look, and why."""

    auto: bool
    reasons: tuple[str, ...] = ()

    @property
    def summary(self) -> str:
        if self.auto:
            return "ran without asking: read-only, on tools already approved"
        return "; ".join(self.reasons)


def enabled() -> bool:
    """Off unless switched on. A gate that defaults to open is not a gate."""
    return os.getenv("TOOLSMITH_AUTO_APPROVE") == "1"


def evaluate(plan: TaskPlan) -> PolicyDecision:
    """Decide whether this plan may run unattended."""
    reasons: list[str] = []

    if not enabled():
        reasons.append("auto-approval is not enabled")

    if plan.fills:
        names = ", ".join(f.tool_name for f in plan.fills)
        reasons.append(f"would attach a tool nobody has approved yet ({names})")

    if not plan.feasible:
        reasons.append("some steps have no tool")

    for meaning in plan.footprint:
        if meaning.scope not in AUTO_SAFE_SCOPES:
            reasons.append(f"{meaning.scope} is not on the unattended allowlist")
        elif risk_rank(meaning.risk) > risk_rank(MAX_AUTO_RISK):
            reasons.append(f"{meaning.scope} is rated {meaning.risk}")
        elif meaning.account_wide:
            reasons.append(f"{meaning.scope} reaches the whole account")

    return PolicyDecision(auto=not reasons, reasons=tuple(reasons))
