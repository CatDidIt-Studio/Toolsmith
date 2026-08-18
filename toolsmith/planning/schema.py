"""What a task will take, worked out before any of it happens.

The unit of consent here is the task, not the tool. Nobody wants to be asked
four times whether an agent may attach a thing they have never heard of; they
want to know what the job will touch, once, before it starts.

The split is the same one used everywhere else in this codebase. A model
decides which held tool serves which step, because that is a language
judgement. Code computes the permission footprint and whether the task is
possible at all, because those are sums over a set and must not be
negotiable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

from toolsmith.approval.scopes import Risk, ScopeMeaning, explain_all, overall_risk

StepStatus = Literal["held", "missing"]


class PlannedStep(BaseModel):
    """One thing the task requires, and what would do it."""

    action: str = Field(description="What gets done, in plain words")
    tool: str | None = Field(
        default=None, description="Name of an available tool, or null if none fits"
    )
    needs: str | None = Field(
        default=None,
        description="When tool is null: the kind of capability that is missing",
    )

    @property
    def status(self) -> StepStatus:
        return "held" if self.tool else "missing"


class DraftPlan(BaseModel):
    """The planner's output, before any arithmetic is done on it."""

    steps: list[PlannedStep] = Field(default_factory=list)


@dataclass(frozen=True)
class ToolInventory:
    """A tool the agent already holds, and what it was granted."""

    name: str
    description: str
    scopes: tuple[str, ...] = ()
    server_id: str = ""


@dataclass
class TaskPlan:
    """A costed plan, ready to put in front of a person."""

    task: str
    steps: list[PlannedStep]
    inventory: dict[str, ToolInventory]
    # Screened candidates that would close the gaps, if any were found.
    fills: list = field(default_factory=list)

    @property
    def filled_steps(self) -> set[int]:
        return {id(fill.step) for fill in self.fills}

    @property
    def unfilled(self) -> list[PlannedStep]:
        """Gaps nothing was found for. These are what make a plan impossible."""
        filled = self.filled_steps
        return [s for s in self.missing if id(s) not in filled]

    @property
    def new_footprint(self) -> list[ScopeMeaning]:
        """Permissions that would be granted to tools not yet attached.

        Kept apart from the footprint of held tools on purpose. Approving this
        plan does two things -- runs a task and hands authority to something
        new -- and a card that adds those together is asking for one consent
        while collecting two.
        """
        scopes = {scope for fill in self.fills for scope in fill.granted_scopes}
        return explain_all(sorted(scopes))

    @property
    def held(self) -> list[PlannedStep]:
        return [s for s in self.steps if s.status == "held"]

    @property
    def missing(self) -> list[PlannedStep]:
        return [s for s in self.steps if s.status == "missing"]

    @property
    def feasible(self) -> bool:
        """Every step has something that can do it, held or offered."""
        return bool(self.steps) and not self.unfilled

    @property
    def used_tools(self) -> list[ToolInventory]:
        seen: dict[str, ToolInventory] = {}
        for step in self.held:
            entry = self.inventory.get(step.tool or "")
            if entry is not None:
                seen[entry.name] = entry
        return list(seen.values())

    @property
    def footprint(self) -> list[ScopeMeaning]:
        """Every permission this task would actually exercise.

        The union of what the steps use, not of everything the agent holds.
        A tool that is attached but not needed for this job contributes
        nothing here -- the question being answered is what this task
        touches, and answering it with the agent's whole standing authority
        would be the same overstatement the product exists to correct.
        """
        scopes = {scope for tool in self.used_tools for scope in tool.scopes}
        return explain_all(sorted(scopes))

    @property
    def risk(self) -> Risk:
        return overall_risk([m.scope for m in self.footprint])

    @property
    def summary(self) -> str:
        if not self.steps:
            return "nothing to do"
        if self.feasible:
            new = f", {len(self.fills)} new tool(s)" if self.fills else ""
            return (
                f"{len(self.steps)} steps, all covered{new}, "
                f"{len(self.footprint) + len(self.new_footprint)} permissions used"
            )
        return f"{len(self.unfilled)} of {len(self.steps)} steps have no tool"
