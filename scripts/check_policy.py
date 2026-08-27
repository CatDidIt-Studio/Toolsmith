"""Show both halves of the argument: one approval, and sometimes none.

The claim is that this work goes from five interruptions to one, and to zero
for tasks that do not warrant a person. The second half is only worth anything
if the line between them is visible, so this runs two tasks against the same
gate and prints why each landed where it did.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from toolsmith.planning.planner import plan_task  # noqa: E402
from toolsmith.planning.schema import ToolInventory  # noqa: E402
from toolsmith.policy.gate import enabled, evaluate  # noqa: E402

INVENTORY = {
    "list_issues": ToolInventory(
        "list_issues", "Lists issues on a GitHub repository.", ("issues:read",), "gh"
    ),
    "create_issue": ToolInventory(
        "create_issue",
        "Creates an issue on a GitHub repository with a title, body and labels.",
        ("issues:write",),
        "gh",
    ),
}

TASKS = [
    ("Summarise the open issues on CatDidIt-Studio/Toolsmith.", "read-only"),
    ("Open an issue on CatDidIt-Studio/Toolsmith listing the setup steps.", "writes"),
]


async def main() -> int:
    print(f"  auto-approval enabled: {enabled()}\n")
    for task, label in TASKS:
        plan, _ = await plan_task(task, INVENTORY)
        decision = evaluate(plan)
        print(f"  {label:10} {[m.scope for m in plan.footprint]}")
        print(f"             -> {'RUNS UNATTENDED' if decision.auto else 'ASKS'}")
        print(f"             {decision.summary}\n")
        await asyncio.sleep(1)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
