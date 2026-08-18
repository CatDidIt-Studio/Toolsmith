"""Plan a task, wait for one approval, then execute it under that approval.

The whole product in one run: nothing happens before the card, and after it,
only what the card said.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import os
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import uvicorn  # noqa: E402
from google.adk.runners import InMemoryRunner  # noqa: E402
from google.genai import types  # noqa: E402

from toolsmith.approval.model import STORE, PlanApproval  # noqa: E402
from toolsmith.attach.toolset import Attachment, record_attachment  # noqa: E402
from toolsmith.planning.execute import (  # noqa: E402
    ExecutionRecord,
    build_executor,
    plan_brief,
)
from toolsmith.planning.planner import plan_task  # noqa: E402
from toolsmith.planning.schema import ToolInventory  # noqa: E402
from toolsmith.ui.app import app  # noqa: E402

APP_NAME = "toolsmith"
FIXTURE = os.getenv("TOOLSMITH_FIXTURE", "http://127.0.0.1:9100/mcp")

TASK = (
    "Prepare onboarding for a new contributor to CatDidIt-Studio/Toolsmith: "
    "open an issue titled 'Onboarding checklist' with the setup steps, label it "
    "'onboarding', and invite the user 'new-contributor' to the repository."
)

# Approved earlier, in a previous session: this run is about planning and
# execution, not acquisition.
ATTACHED = Attachment(
    server_id="ghlike",
    url=FIXTURE,
    granted_tools=("create_issue", "add_collaborator"),
    granted_scopes=("issues:write", "administration:write"),
)

INVENTORY = {
    "create_issue": ToolInventory(
        "create_issue",
        "Creates an issue on a GitHub repository with a title, body and optional labels.",
        ("issues:write",),
        "ghlike",
    ),
    "add_collaborator": ToolInventory(
        "add_collaborator",
        "Invites a user to a repository as a collaborator with a given role.",
        ("administration:write",),
        "ghlike",
    ),
}


async def run(task: str, port: int, auto: bool) -> None:
    plan, seconds = await plan_task(task, INVENTORY)
    approval = STORE.add(PlanApproval(plan=plan))
    print(f"\n  planned in {seconds:.2f}s — {plan.summary}")
    for step in plan.steps:
        print(f"    {'ok ' if step.tool else 'GAP'} {step.action[:70]}  {step.tool or ''}")
    print(f"    footprint: {[m.scope for m in plan.footprint]}")
    print(f"\n  approve at http://127.0.0.1:{port}/plan/{approval.id}")

    if auto:
        await asyncio.sleep(1)
        approval.answer("approved")
        print("  (auto-approved)")

    decision = await approval.wait(timeout=600)
    print(f"  decision: {decision}")
    if decision != "approved":
        return

    state = {}
    record_attachment(state, ATTACHED)

    record = ExecutionRecord()
    runner = InMemoryRunner(agent=build_executor(plan, record), app_name=APP_NAME)
    session = await runner.session_service.create_session(
        app_name=APP_NAME, user_id="tyler", session_id=str(uuid.uuid4()), state=state
    )
    message = types.Content(role="user", parts=[types.Part(text=plan_brief(plan))])

    print("\n  executing:")
    async for event in runner.run_async(
        user_id="tyler", session_id=session.id, new_message=message
    ):
        for part in (event.content.parts if event.content else None) or []:
            call = getattr(part, "function_call", None)
            if call is not None:
                print(f"    -> {call.name}({dict(call.args or {})})")
            if part.text:
                record.text.append(part.text)

    print(f"\n  calls made : {record.calls}")
    print(f"  refused    : {record.refused}")
    print(f"  in plan    : {record.stayed_in_plan}")
    for text in record.text:
        print(f"\n  executor: {text.strip()}")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", default=TASK)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--auto-approve", action="store_true")
    args = parser.parse_args()

    config = uvicorn.Config(app, host="127.0.0.1", port=args.port, log_level="warning")
    server = uvicorn.Server(config)
    serving = asyncio.create_task(server.serve())
    try:
        await run(args.task, args.port, args.auto_approve)
    finally:
        server.should_exit = True
        await serving


if __name__ == "__main__":
    asyncio.run(main())
