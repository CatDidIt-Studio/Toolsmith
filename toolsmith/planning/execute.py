"""Carrying out a plan the user approved, and nothing else.

Asking once only works if the answer binds. A single approval that authorises
"this task" and then permits whatever the agent decides to do next is a blank
cheque with a consent screen attached -- worse than asking per tool, because
it looks like more care and is less.

So the approved plan is enforced as a contract at call time. The executor may
use the tools the plan named, for the steps the plan listed. A call to
anything else does not happen: it is refused before it reaches the tool, and
the refusal is recorded rather than smoothed over, because an agent reaching
outside its plan is exactly the thing the user should hear about.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from google.adk.agents import LlmAgent
from google.adk.tools.base_tool import BaseTool

from toolsmith.attach.toolset import ToolsmithToolset
from toolsmith.config import DETERMINISTIC, ORCHESTRATOR_MODEL
from toolsmith.planning.schema import TaskPlan

logger = logging.getLogger(__name__)


@dataclass
class ExecutionRecord:
    calls: list[str] = field(default_factory=list)
    refused: list[str] = field(default_factory=list)
    text: list[str] = field(default_factory=list)

    @property
    def stayed_in_plan(self) -> bool:
        return not self.refused


def _permitted_names(plan: TaskPlan) -> set[str]:
    return {step.tool for step in plan.held if step.tool}


def _matches(called: str, permitted: set[str]) -> bool:
    """Match a call against the approved names.

    ToolsmithToolset prefixes tool names with their server id so two servers
    offering `create_issue` stay distinguishable, which means the name the
    model calls is not always the name the plan recorded. Comparing on the
    suffix keeps the contract intact without making the prefix part of it.
    """
    if called in permitted:
        return True
    return any(called.endswith(f"_{name}") or name.endswith(f"_{called}") for name in permitted)


def enforce(plan: TaskPlan, record: ExecutionRecord):
    """A before_tool_callback that holds the executor to the approved plan."""

    permitted = _permitted_names(plan)

    # ADK invokes this with keywords (tool=, args=, tool_context=), so the
    # names matter more than the order.
    def check(
        *, tool: BaseTool, args: dict[str, Any], tool_context: Any = None
    ) -> dict | None:
        if _matches(tool.name, permitted):
            record.calls.append(tool.name)
            return None
        record.refused.append(tool.name)
        logger.warning("refused out-of-plan call to %s", tool.name)
        # Returning a value short-circuits the call: the tool is never
        # invoked. The executor is told why, so it reports rather than
        # silently retrying something else.
        return {
            "error": "not_in_approved_plan",
            "detail": (
                f"{tool.name} was not part of the plan the user approved. "
                "Stop and report this instead of trying another way."
            ),
        }

    return check


INSTRUCTION = """\
Carry out the approved plan, in order, and stop when it is done.

Do only what the plan lists. It was shown to the user and approved as a whole,
and its steps are the extent of what they agreed to -- doing more, even
something helpful and obviously related, means doing something nobody
consented to.

If a step fails, say what failed and stop. Do not substitute another approach
and do not retry with a different tool. If a call comes back refused as not in
the approved plan, that is not an obstacle to work around; report it.

When finished, state plainly what was done, one line per step.
"""


def build_executor(plan: TaskPlan, record: ExecutionRecord) -> LlmAgent:
    return LlmAgent(
        name="executor",
        model=ORCHESTRATOR_MODEL,
        description="Carries out an approved plan.",
        instruction=INSTRUCTION,
        generate_content_config=DETERMINISTIC,
        tools=[ToolsmithToolset()],
        before_tool_callback=enforce(plan, record),
    )


def plan_brief(plan: TaskPlan) -> str:
    lines = [f"Task: {plan.task}", "", "Approved steps:"]
    for index, step in enumerate(plan.held, start=1):
        lines.append(f"{index}. {step.action}  (use {step.tool})")
    return "\n".join(lines)
