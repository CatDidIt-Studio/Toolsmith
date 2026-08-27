"""The take. Runs the whole thing and waits for a real click.

Separate from `rehearse.py`, which approves itself so the timing can be
measured without a person. That is the wrong shape for filming: the approval
is the thing being demonstrated, so here it blocks until someone actually
presses the button.

Prints sparsely and pauses between phases, because the operator is driving.
Nothing scrolls away before it has been seen.
"""

from __future__ import annotations

# Before the ADK import, because it warns at import time and the warning
# lands above the first line of the run.
import warnings

warnings.filterwarnings("ignore", category=UserWarning)

import argparse
import asyncio
import logging
import os
import sys
import time
import uuid
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import uvicorn  # noqa: E402
from google.adk.runners import InMemoryRunner  # noqa: E402
from google.genai import types  # noqa: E402

from toolsmith.approval.model import STORE, PlanApproval  # noqa: E402
from toolsmith.attach.toolset import Attachment, record_attachment  # noqa: E402
from toolsmith.memory.audit import (  # noqa: E402
    record_execution,
    record_plan,
    unused_grants,
)
from toolsmith.memory.store import get_memory  # noqa: E402
from toolsmith.planning.execute import (  # noqa: E402
    ExecutionRecord,
    build_executor,
    plan_brief,
)
from toolsmith.planning.fill import attachments_from, fill_gaps  # noqa: E402
from toolsmith.planning.planner import plan_task  # noqa: E402
from toolsmith.planning.schema import ToolInventory  # noqa: E402
from toolsmith.policy.gate import evaluate  # noqa: E402
from toolsmith.sandbox.backends import get_sandbox  # noqa: E402
from toolsmith.ui.app import app  # noqa: E402

N = os.getenv("TOOLSMITH_PROJECT_NUMBER", "111259597572")
GITHUB_MCP = f"https://toolsmith-github-{N}.us-central1.run.app/mcp"

# Any task works -- pass one as a quoted argument and it is planned like any
# other. These are named because they land in four different places, and a
# demo that only ever shows the happy one is indistinguishable from a
# hardcoded script.
#
#   triage     read-only, on a tool already held. Runs unattended.
#   onboard    one gap that discovery closes. Asks once, then runs.
#   full       adds a step nothing can do. Refuses to ask at all.
#   audit      read plus write. Asks, because writing always asks.
TASKS = {
    "triage": (
        "Summarise the open issues on CatDidIt-Studio/Toolsmith."
    ),
    "onboard": (
        "Prepare onboarding for a new contributor to CatDidIt-Studio/Toolsmith: "
        "open an issue titled 'Onboarding checklist' with the setup steps, label "
        "it 'onboarding', and invite the user 'new-contributor' to the repository."
    ),
    "full": (
        "Prepare onboarding for a new contributor to CatDidIt-Studio/Toolsmith: "
        "open an issue titled 'Onboarding checklist' with the setup steps, label "
        "it 'onboarding', invite the user 'new-contributor' to the repository, and "
        "post a welcome note in the team chat."
    ),
    "audit": (
        "Review the open issues on CatDidIt-Studio/Toolsmith and open a new issue "
        "titled 'Weekly triage' summarising what is still unresolved."
    ),
}

HELD = Attachment(
    server_id="internal.catdidit/github-collaborators",
    url=GITHUB_MCP,
    granted_tools=("create_issue", "list_issues"),
    granted_scopes=("issues:write", "issues:read"),
)
# What the agent starts with. Deliberately partial: enough that some tasks are
# already possible, not enough that every task is.
INVENTORY = {
    "create_issue": ToolInventory(
        "create_issue",
        "Creates an issue on a GitHub repository with a title, body and optional labels.",
        ("issues:write",),
        HELD.server_id,
    ),
    "list_issues": ToolInventory(
        "list_issues",
        "Lists issues on a GitHub repository, optionally filtered by state or label. Read-only.",
        ("issues:read",),
        HELD.server_id,
    ),
}

RULE = "─" * 66


def quiet() -> None:
    """Stop a recovered failure from looking like a crash.

    Transient 503s from the model are expected and retried, and the retry
    works -- but the libraries print the whole stack on the way past. Thirty
    lines of traceback scrolling by, followed by the run continuing normally,
    reads on camera as something breaking and being ignored.

    Only the noise is suppressed. Anything that actually fails still raises,
    and a retry still says so in one line.
    """
    logging.basicConfig(level=logging.WARNING, format="  (%(message)s)")
    for name in (
        "google_adk",
        "google.adk",
        "google_genai",
        "google.genai",
        "google.adk.workflow",
        "google.adk.runners",
        "httpx",
        "mcp",
    ):
        logging.getLogger(name).setLevel(logging.CRITICAL)

    # ADK writes node failures straight to stderr around the retry, so the
    # stream itself is filtered rather than the loggers.
    sys.stderr = _Filtered(sys.stderr)


class _Filtered:
    """Drops traceback frames, keeps anything worth reading."""

    NOISE = ("Traceback (most", 'File "', "    ", "^^^", "The above exception",
             "During handling", "google.genai.errors", "google.adk.workflow",
             "raise ", "Node execution failed")

    def __init__(self, stream) -> None:
        self._stream = stream

    def write(self, text: str) -> None:
        if text.strip() and any(text.lstrip().startswith(n) or n in text[:40]
                                for n in self.NOISE):
            return
        if "is being retried" in text:
            self._stream.write("     (a model call failed and was retried)\n")
            return
        self._stream.write(text)

    def flush(self) -> None:
        self._stream.flush()


def say(*lines: str) -> None:
    print()
    for line in lines:
        print(f"  {line}")


async def take(port: int, open_browser: bool, task: str) -> int:
    sandbox, memory = get_sandbox(), get_memory()
    if not sandbox.isolated:
        say("REFUSING: this is the local sandbox, which is not isolated.",
            "Set TOOLSMITH_SANDBOX_URL to the deployed service.")
        return 1

    print(RULE)
    say(f"sandbox   {type(sandbox).__name__}  isolated",
        f"memory    {type(memory).__name__}  durable={memory.durable}")
    say("TASK", "", *[f"  {task[i:i + 62]}" for i in range(0, len(task), 62)])
    say(f"the agent holds: {', '.join(INVENTORY)}",
        "everything else it needs, it has to find and get approved")
    print(f"\n{RULE}")

    started = time.monotonic()
    say("1  working out what this takes, before anything runs ...")
    plan, _ = await plan_task(task, INVENTORY)
    for step in plan.steps:
        print(f"     {'have' if step.tool else 'GAP '}  {step.action[:56]}")

    if plan.missing:
        say(f"2  {len(plan.missing)} steps have no tool. going to look ...")
        plan.fills = await fill_gaps(
            plan.missing, sandbox=sandbox, attached_tool_names=list(INVENTORY), memory=memory
        )
        for fill in plan.fills:
            print(f"     found  {fill.tool_name}  from {fill.server.name}")
            print(f"            screened: {fill.verdict.decision}, "
                  f"granted {list(fill.verdict.granted_scopes)}")
        for step in plan.unfilled:
            print(f"     none   {step.action[:52]}")

    decision = evaluate(plan)
    approval = STORE.add(PlanApproval(plan=plan, policy=decision))
    url = f"http://127.0.0.1:{port}/plan/{approval.id}"

    if not approval.approvable:
        # Deliberate, and the more interesting outcome of the two: a task that
        # cannot finish is not one to collect permissions for.
        say(f"3  {time.monotonic() - started:.0f}s so far. nothing has run,",
            "   and nothing will -- there is a step nothing can do.",
            "",
            f"   SEE WHY:  {url}")
        if open_browser:
            webbrowser.open(url)
        record_plan(memory, plan, "unapprovable", decision.summary)
        return 0

    if decision.auto:
        # The policy said this does not need a person. Acting on that is the
        # whole point -- computing the decision and then asking anyway would
        # be the same interruption with extra steps.
        say(f"3  {time.monotonic() - started:.0f}s so far.",
            "",
            "   NOT ASKING — this task only reads, on tools already approved.",
            f"   {url}")
        approval.answer("approved")
        outcome = "approved"
    else:
        say(f"3  {time.monotonic() - started:.0f}s so far. nothing has run.",
            "",
            f"   APPROVE OR CANCEL:  {url}",
            "",
            f"   asked because: {decision.summary[:58]}")
        if open_browser:
            webbrowser.open(url)
        outcome = await approval.wait(timeout=900)
    record_plan(memory, plan, outcome, decision.summary)
    if outcome != "approved":
        say(f"4  {outcome}. nothing ran.")
        return 0

    say("4  running." if decision.auto else "4  approved. running.")
    state: dict = {}
    record_attachment(state, HELD)
    for attachment in attachments_from(plan.fills):
        record_attachment(state, attachment)

    record = ExecutionRecord()
    runner = InMemoryRunner(agent=build_executor(plan, record), app_name="demo")
    session = await runner.session_service.create_session(
        app_name="demo", user_id="demo", session_id=str(uuid.uuid4()), state=state
    )
    async for event in runner.run_async(
        user_id="demo",
        session_id=session.id,
        new_message=types.Content(role="user", parts=[types.Part(text=plan_brief(plan))]),
    ):
        for part in (event.content.parts if event.content else None) or []:
            call = getattr(part, "function_call", None)
            if call is not None:
                print(f"     calling  {call.name}")
            if part.text:
                record.text.append(part.text)

    record_execution(memory, plan, record)
    print(f"\n{RULE}")
    say(f"done in {time.monotonic() - started:.0f}s",
        f"ran        {record.calls}",
        f"refused    {record.refused or 'nothing'}",
        f"unused     {unused_grants(plan, record) or 'no granted permission went unused'}",
        "",
        f"audit trail:  http://127.0.0.1:{port}/audit")
    print(RULE)
    return 0


async def main() -> None:
    quiet()
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument(
        "--task",
        default="onboard",
        help=(
            f"one of {sorted(TASKS)}, or any task in quotes -- "
            "arbitrary tasks are planned exactly the same way"
        ),
    )
    args = parser.parse_args()

    config = uvicorn.Config(app, host="127.0.0.1", port=args.port, log_level="critical")
    server = uvicorn.Server(config)
    serving = asyncio.create_task(server.serve())
    await asyncio.sleep(1)
    try:
        await take(args.port, not args.no_browser, TASKS.get(args.task, args.task))
        say("(the server is still up — leave it for the audit page, ctrl-c to stop)")
        await serving
    finally:
        server.should_exit = True


if __name__ == "__main__":
    asyncio.run(main())
