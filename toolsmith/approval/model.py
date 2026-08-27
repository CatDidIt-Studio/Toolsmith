"""The approval request, and the place the agent waits for an answer.

This is the one point in the system where the agent stops and a person
decides. Everything upstream -- discovery, triage, sandboxed probing,
screening -- exists to make this single decision well-informed enough to be
made in a few seconds.

The store is in-memory and keyed per session, which is right for a demo and
would need to be Firestore-backed to survive a restart. What is not a demo
shortcut is the shape: a request carries the evidence, the answer carries only
a decision and the scopes actually granted, and nothing attaches without one.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

from toolsmith.approval.scopes import Risk, ScopeMeaning, explain_all, overall_risk
from toolsmith.planning.schema import TaskPlan
from toolsmith.screening.candidate import Candidate
from toolsmith.screening.schema import Verdict

Decision = Literal["pending", "approved", "denied"]


@dataclass(frozen=True)
class Provenance:
    """Where this thing came from, as far as anyone can tell."""

    server_name: str
    version: str
    repository_url: str | None = None
    publisher: str | None = None
    signed: bool = False
    registry_status: str = "unknown"
    published_at: str | None = None
    updated_at: str | None = None

    @property
    def republished(self) -> bool:
        return bool(
            self.published_at and self.updated_at and self.published_at != self.updated_at
        )


@dataclass
class ApprovalRequest:
    """One tool, screened, waiting on a person."""

    capability: str
    tool: Candidate
    verdict: Verdict
    provenance: Provenance
    endpoint: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    decision: Decision = "pending"
    _answered: asyncio.Event = field(default_factory=asyncio.Event, repr=False)

    # -- what the card renders -------------------------------------------- #

    @property
    def requested(self) -> list[ScopeMeaning]:
        return explain_all(self.verdict.requested_scopes)

    @property
    def granted(self) -> list[ScopeMeaning]:
        return explain_all(self.verdict.granted_scopes)

    @property
    def withheld(self) -> list[ScopeMeaning]:
        """What was asked for and is not being given.

        This is the part of the card that earns its place. The user is not
        being asked to trust a judgement call they cannot see -- they are shown
        the gap between the ask and the grant, in plain words, before they
        decide.
        """
        kept = {m.scope for m in self.granted}
        return [m for m in self.requested if m.scope not in kept]

    @property
    def risk(self) -> Risk:
        return overall_risk(self.verdict.granted_scopes)

    @property
    def blocking_findings(self) -> list:
        return [f for f in self.verdict.findings if f.severity == "block"]

    @property
    def warnings(self) -> list:
        return [f for f in self.verdict.findings if f.severity == "warn"]

    @property
    def notes(self) -> list:
        return [f for f in self.verdict.findings if f.severity == "info"]

    @property
    def approvable(self) -> bool:
        """A blocked verdict is not offered for approval.

        The card is where a person weighs a real trade-off. Putting an
        approve button under a blocked entry would turn screening into a
        suggestion, and would teach people that the button is always there.
        """
        return not self.verdict.blocked

    # -- the wait --------------------------------------------------------- #

    async def wait(self, timeout: float | None = None) -> Decision:
        try:
            await asyncio.wait_for(self._answered.wait(), timeout)
        except asyncio.TimeoutError:
            # Silence is not consent.
            self.decision = "denied"
        return self.decision

    def answer(self, decision: Literal["approved", "denied"]) -> None:
        if self.decision != "pending":
            return
        if decision == "approved" and not self.approvable:
            raise ValueError(f"request {self.id} is blocked and cannot be approved")
        self.decision = decision
        self._answered.set()


@dataclass
class PlanApproval:
    """A whole task, costed, waiting on one decision.

    This is the consent unit the product settled on. Asking per tool means
    interrupting someone three times about things they have never heard of;
    asking per task means asking once, about the thing they actually wanted.

    Bundling only works if the bundle is shown honestly, which is why the plan
    carries its footprint and its gaps rather than a summary of them. A single
    approval that hides what it covers is how consent screens became something
    people click past.
    """

    plan: "TaskPlan"
    # Why this is being asked about at all. Shown on the card, because "you
    # are being asked because this writes and attaches something new" is
    # itself information the person deciding should have.
    policy: object | None = None
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    decision: Decision = "pending"
    _answered: asyncio.Event = field(default_factory=asyncio.Event, repr=False)

    @property
    def approvable(self) -> bool:
        # A plan with a step nothing can perform is not offered for approval.
        # Approving it would authorise a footprint for work that cannot finish.
        return self.plan.feasible

    @property
    def risk(self) -> Risk:
        return self.plan.risk

    async def wait(self, timeout: float | None = None) -> Decision:
        try:
            await asyncio.wait_for(self._answered.wait(), timeout)
        except asyncio.TimeoutError:
            self.decision = "denied"
        return self.decision

    def answer(self, decision: Literal["approved", "denied"]) -> None:
        if self.decision != "pending":
            return
        if decision == "approved" and not self.approvable:
            raise ValueError(f"plan {self.id} has uncovered steps and cannot be approved")
        self.decision = decision
        self._answered.set()


class ApprovalStore:
    def __init__(self) -> None:
        self._requests: dict[str, ApprovalRequest | PlanApproval] = {}

    def add(self, request):
        self._requests[request.id] = request
        return request

    def get(self, request_id: str):
        return self._requests.get(request_id)

    def pending(self) -> list[ApprovalRequest]:
        return [r for r in self._requests.values() if r.decision == "pending"]

    def all(self) -> list[ApprovalRequest]:
        return sorted(self._requests.values(), key=lambda r: r.created_at, reverse=True)


STORE = ApprovalStore()
