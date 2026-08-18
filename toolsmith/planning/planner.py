"""Turning a request into a costed plan."""

from __future__ import annotations

import json

from toolsmith.agent_io import run_structured
from toolsmith.agents.planner import build_planner
from toolsmith.config import ATTACHED_STATE_KEY
from toolsmith.planning.schema import DraftPlan, TaskPlan, ToolInventory

APP_NAME = "toolsmith-planner"


def inventory_from_state(state: dict, tool_descriptions: dict[str, str] | None = None) -> dict[str, ToolInventory]:
    """Read what the agent currently holds out of session state.

    Descriptions are optional because they are not always to hand: state
    records what was granted, while the wording came from the server. When a
    description is missing the tool still appears -- an unlabelled capability
    the user approved is still a capability, and dropping it would understate
    the footprint.
    """
    descriptions = tool_descriptions or {}
    inventory: dict[str, ToolInventory] = {}
    for record in state.get(ATTACHED_STATE_KEY) or []:
        for name in record.get("granted_tools", []):
            inventory[name] = ToolInventory(
                name=name,
                description=descriptions.get(name, ""),
                scopes=tuple(record.get("granted_scopes", [])),
                server_id=record.get("server_id", ""),
            )
    return inventory


async def plan_task(task: str, inventory: dict[str, ToolInventory]) -> tuple[TaskPlan, float]:
    listing = (
        "\n".join(
            f"- {t.name}: {t.description or '(no description recorded)'}"
            f"\n    granted: {', '.join(t.scopes) or 'nothing'}"
            for t in inventory.values()
        )
        or "(the agent currently holds no tools)"
    )
    prompt = f"Task:\n{task}\n\nTools currently held:\n{listing}\n"

    draft, seconds = await run_structured(
        build_planner(as_root=True), prompt, DraftPlan, app_name=APP_NAME
    )

    # The planner is not trusted to only name tools that exist. A hallucinated
    # match would otherwise become a step the plan claims is covered, and the
    # user would approve a footprint for something that cannot run.
    for step in draft.steps:
        if step.tool and step.tool not in inventory:
            step.needs = step.needs or f"a tool that can {step.action}"
            step.tool = None

    return TaskPlan(task=task, steps=draft.steps, inventory=inventory), seconds
