"""The whole thing, start to finish, timed.

Run before recording. The submission asks for an unedited live execution, so
what matters is not only that each part works but that the sequence holds
together inside four minutes without anything needing a second try.

Every step is timed and printed, because the thing most likely to sink a live
take is a stage that is quietly slower than remembered.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from google.adk.runners import InMemoryRunner  # noqa: E402
from google.genai import types  # noqa: E402

from toolsmith.approval.model import STORE, PlanApproval  # noqa: E402
from toolsmith.attach.toolset import Attachment, record_attachment  # noqa: E402
from toolsmith.planning.execute import (  # noqa: E402
    ExecutionRecord,
    build_executor,
    plan_brief,
)
from toolsmith.planning.fill import attachments_from, fill_gaps  # noqa: E402
from toolsmith.planning.planner import plan_task  # noqa: E402
from toolsmith.planning.schema import ToolInventory  # noqa: E402
from toolsmith.memory.audit import (  # noqa: E402
    record_execution,
    record_plan,
    unused_grants,
)
from toolsmith.memory.store import get_memory  # noqa: E402
from toolsmith.sandbox.backends import get_sandbox  # noqa: E402

N = os.getenv("TOOLSMITH_PROJECT_NUMBER", "111259597572")
GITHUB_MCP = f"https://toolsmith-github-{N}.us-central1.run.app/mcp"

TASK = (
    "Prepare onboarding for a new contributor to CatDidIt-Studio/Toolsmith: "
    "open an issue titled 'Onboarding checklist' with the setup steps, label it "
    "'onboarding', and invite the user 'new-contributor' to the repository."
)

HELD = Attachment(
    server_id="internal.catdidit/github-collaborators",
    url=GITHUB_MCP,
    granted_tools=("create_issue",),
    granted_scopes=("issues:write",),
)
INVENTORY = {
    "create_issue": ToolInventory(
        "create_issue",
        "Creates an issue on a GitHub repository with a title, body and optional labels.",
        ("issues:write",),
        HELD.server_id,
    )
}


def mark(label: str, started: float) -> float:
    now = time.monotonic()
    print(f"  {label:34} {now - started:5.1f}s")
    return now


async def main() -> int:
    sandbox = get_sandbox()
    memory = get_memory()
    print(f"  sandbox {type(sandbox).__name__}, isolated={sandbox.isolated}")
    print(f"  memory  {type(memory).__name__}, durable={memory.durable}\n")
    if not sandbox.isolated:
        print("  REFUSING: rehearse against the deployed sandbox, not the local one")
        return 1

    t0 = last = time.monotonic()

    plan, _ = await plan_task(TASK, INVENTORY)
    last = mark(f"planned: {plan.summary}", last)

    if plan.missing:
        plan.fills = await fill_gaps(
            plan.missing,
            sandbox=sandbox,
            attached_tool_names=list(INVENTORY),
            memory=memory,
        )
        last = mark(f"gaps filled: {len(plan.fills)}/{len(plan.missing)}", last)

    approval = STORE.add(PlanApproval(plan=plan))
    print(f"  card    : /plan/{approval.id}   feasible={plan.feasible}")
    print(f"  footprint: {[m.scope for m in plan.footprint]} "
          f"+ new {[m.scope for m in plan.new_footprint]}")

    if not approval.approvable:
        print(f"\n  not approvable: {[s.action for s in plan.unfilled]}")
        return 1

    approval.answer("approved")
    record_plan(memory, plan, "approved")
    last = mark("approved", last)

    state: dict = {}
    record_attachment(state, HELD)
    for attachment in attachments_from(plan.fills):
        record_attachment(state, attachment)

    record = ExecutionRecord()
    runner = InMemoryRunner(agent=build_executor(plan, record), app_name="rehearsal")
    session = await runner.session_service.create_session(
        app_name="rehearsal", user_id="t", session_id=str(uuid.uuid4()), state=state
    )
    async for event in runner.run_async(
        user_id="t",
        session_id=session.id,
        new_message=types.Content(role="user", parts=[types.Part(text=plan_brief(plan))]),
    ):
        for part in (event.content.parts if event.content else None) or []:
            call = getattr(part, "function_call", None)
            if call is not None:
                print(f"      -> {call.name}")
            if part.text:
                record.text.append(part.text)
    last = mark(f"executed {len(record.calls)}/{len(plan.executable)}: {record.calls}", last)
    record_execution(memory, plan, record)
    unused = unused_grants(plan, record)
    print(f"  granted but unused: {unused or 'none'}")

    total = time.monotonic() - t0
    print(f"\n  total {total:.1f}s   refused={record.refused}   in-plan={record.stayed_in_plan}")
    if record.text:
        print(f"\n  executor: {record.text[-1].strip()[:300]}")

    ok = plan.feasible and record.stayed_in_plan and len(record.calls) == len(plan.executable)
    print(f"\n  {'READY' if ok else 'NOT READY'} — {total:.0f}s of a 240s budget")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
