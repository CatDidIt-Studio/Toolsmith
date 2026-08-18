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


async def seed(which: str) -> None:
    inventory = {t.name: t for t in (FULL if which == "full" else PARTIAL)}
    task = TASK if which == "full" else TASK + " Then post a welcome note in the team chat."
    plan, seconds = await plan_task(task, inventory)
    approval = STORE.add(PlanApproval(plan=plan))
    print(f"  planned in {seconds:.2f}s: {plan.summary}")
    print(f"  http://127.0.0.1:8000/plan/{approval.id}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--which", choices=["full", "partial", "both"], default="both")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    async def seed_all():
        for which in (["full", "partial"] if args.which == "both" else [args.which]):
            await seed(which)
            await asyncio.sleep(4.2)

    asyncio.run(seed_all())
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
