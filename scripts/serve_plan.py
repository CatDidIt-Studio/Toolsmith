"""Plan a task against a tool inventory and serve the approval card."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import uvicorn  # noqa: E402

from toolsmith.approval.model import STORE, PlanApproval  # noqa: E402
from toolsmith.planning.planner import plan_task  # noqa: E402
from toolsmith.planning.schema import ToolInventory  # noqa: E402
from toolsmith.ui.app import app  # noqa: E402

TASK = (
    "Prepare onboarding for a new contributor to CatDidIt-Studio/Toolsmith: "
    "open an issue with the setup checklist, label it 'onboarding', and invite "
    "them to the repository."
)

FULL = [
    ToolInventory(
        "github_create_issue",
        "Creates an issue on a GitHub repository with a title, body and labels.",
        ("issues:write",),
        "gh",
    ),
    ToolInventory(
        "github_add_collaborator",
        "Invites a user to a repository as a collaborator with a given role.",
        ("administration:write",),
        "gh",
    ),
]

PARTIAL = FULL[:1] + [
    ToolInventory(
        "github_list_issues", "Lists issues on a repository.", ("issues:read",), "gh"
    )
]


async def seed(which: str, fill: bool, port: int) -> None:
    inventory = {t.name: t for t in (FULL if which == "full" else PARTIAL)}
    task = TASK if which == "full" else TASK + " Then post a welcome note in the team chat."
    plan, seconds = await plan_task(task, inventory)
    print(f"  planned in {seconds:.2f}s: {plan.summary}")

    if fill and plan.missing:
        from toolsmith.planning.fill import fill_gaps
        from toolsmith.sandbox.backends import get_sandbox

        print(f"  filling {len(plan.missing)} gap(s)...")
        plan.fills = await fill_gaps(
            plan.missing,
            sandbox=get_sandbox(),
            attached_tool_names=list(inventory),
        )
        for f in plan.fills:
            print(f"    filled: {f.step.action[:44]:44} <- {f.tool_name} "
                  f"({f.server.name}) {f.verdict.decision} {f.verdict.granted_scopes}")
        print(f"  now: {plan.summary}  feasible={plan.feasible}")

    approval = STORE.add(PlanApproval(plan=plan))
    print(f"  http://127.0.0.1:{port}/plan/{approval.id}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--which", choices=["full", "partial", "both"], default="both")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--fill", action="store_true")
    args = parser.parse_args()

    async def seed_all():
        for which in (["full", "partial"] if args.which == "both" else [args.which]):
            await seed(which, args.fill, args.port)
            await asyncio.sleep(2)

    asyncio.run(seed_all())
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
