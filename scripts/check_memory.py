"""Prove that a server which rewrites itself after approval is caught.

This check exists because the rug-pull detection was, for most of this
project's life, code that could not run. It compares a tool's description
against the one seen before, and nothing in the pipeline ever supplied a
"before" -- the parameter defaulted to None and no caller passed it. It
passed every test, because the only things that set it were test cases
setting it directly.

So the question here is not whether the comparison works. It is whether the
system remembers across sessions well enough for the comparison to have
anything to do.

Two runs. The first sees a server and records it. The second sees the same
server after its description has changed, and must notice.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from toolsmith.memory.store import LocalMemory, ToolMemory  # noqa: E402
from toolsmith.planning.fill import fill_gap  # noqa: E402
from toolsmith.planning.schema import PlannedStep  # noqa: E402
from toolsmith.sandbox.backends import get_sandbox  # noqa: E402
from toolsmith.screening.schema import FindingCode  # noqa: E402

STEP = PlannedStep(
    action="Invite the new contributor to the repository",
    needs="invite a user to a GitHub repository",
)


async def main() -> int:
    memory = LocalMemory(Path(tempfile.mkdtemp()) / "memory.json")
    sandbox = get_sandbox()
    print(f"  sandbox {type(sandbox).__name__}, memory {type(memory).__name__}\n")

    first = await fill_gap(STEP, sandbox=sandbox, memory=memory)
    if first is None:
        print("  no candidate found; cannot test drift")
        return 1
    codes = {f.code for f in first.verdict.findings}
    print(f"  run 1: {first.tool_name} -> {first.verdict.decision}")
    print(f"         drift reported: {FindingCode.DESCRIPTION_CHANGED_SINCE_SEEN in codes}")
    if FindingCode.DESCRIPTION_CHANGED_SINCE_SEEN in codes:
        print("  FAIL: drift on first sight means the comparison is meaningless")
        return 1

    # The server rewrites itself. Simulated by changing what we remember,
    # which is the same comparison from the other side and does not require
    # redeploying a service mid-test.
    remembered = memory.recall_tool(first.server.name, first.tool_name)
    if remembered is None:
        print("  FAIL: nothing was remembered, so nothing can be compared later")
        return 1
    print(f"  remembered: {remembered.description[:64]!r}")

    memory.remember_tool(
        ToolMemory(
            server_id=remembered.server_id,
            tool_name=remembered.tool_name,
            description="Invites a user to a repository as a collaborator.",
            first_seen=remembered.first_seen,
            approved_at=remembered.first_seen,
        )
    )

    second = await fill_gap(STEP, sandbox=sandbox, memory=memory)
    if second is None:
        print("\n  run 2: blocked outright — drift treated as disqualifying")
        return 0
    codes = {f.code for f in second.verdict.findings}
    drifted = FindingCode.DESCRIPTION_CHANGED_SINCE_SEEN in codes
    print(f"\n  run 2: {second.tool_name} -> {second.verdict.decision}")
    print(f"         drift reported: {drifted}")
    for finding in second.verdict.findings:
        if finding.code is FindingCode.DESCRIPTION_CHANGED_SINCE_SEEN:
            print(f"         {finding.evidence[:200]}")

    print(f"\n  {'PASS' if drifted else 'FAIL'}: a rewritten description "
          f"{'was' if drifted else 'was NOT'} noticed across sessions")
    return 0 if drifted else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
