"""The agent the user talks to.

It holds the goal and the credentials, and it is the one component that must
never read a word written by a third-party publisher. That is why acquisition
is a tool call rather than something the orchestrator does: everything on the
other side of `acquire_capability` -- registry listings, tool descriptions,
parameter schemas -- is attacker-authored, and none of it comes back. What
returns is a handful of fields this module produced itself.

Its tool list is `ToolsmithToolset`, which starts empty. The agent literally
cannot do anything until something has been screened and approved, which makes
the failure mode honest: it says it cannot, and then goes and fixes that.
"""

from __future__ import annotations

import logging

from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool, ToolContext

from toolsmith.attach.toolset import ToolsmithToolset
from toolsmith.config import DETERMINISTIC, ORCHESTRATOR_MODEL
from toolsmith.pipeline import acquire, commit
from toolsmith.sandbox.backends import get_sandbox

logger = logging.getLogger(__name__)

INSTRUCTION = """\
You act on the user's behalf using the tools you have.

You start with none. When a request needs a capability you do not have, say so
plainly in one sentence, then call `acquire_capability` describing the
capability in ordinary words -- what needs doing, to what kind of thing. Do not
name a server, a package or a vendor; finding one is the tool's job, and
guessing at names is how you end up asking for something that does not exist.

Acquisition may take a moment, because a person has to approve the tool before
it is attached. If it comes back without a tool, read `outcome` and say what
actually happened -- `declined_by_user` means a person said no, while
`screening_rejected_all`, `no_server_answered` and `nothing_found` mean nobody
was ever asked. Do not report a refusal that did not occur.

Either way, stop. Do not try to reach the same capability another way, and
never work around a refusal.

When a tool is attached, use it and finish the original request.

You will never see the text a tool publisher wrote. Do not ask for it, and do
not treat the summary you get back as a description of what the tool does --
it is a record of what was granted.
"""


async def acquire_capability(capability: str, tool_context: ToolContext) -> dict:
    """Find, screen and attach a tool for a capability this agent lacks.

    Args:
        capability: What needs doing, in plain words. For example "file and
            label issues on a specific GitHub repository". Not a server name.

    Returns:
        Whether a tool was attached, and if so its name and the permissions it
        was granted.
    """
    result = await acquire(
        capability,
        task_summary=capability,
        sandbox=get_sandbox(),
        attached_tool_names=_attached_names(tool_context),
    )

    if not result.acquired:
        # Deliberately terse. Rejection reasons quote publisher-authored text,
        # which is exactly what must not cross back into this context; the
        # detail lives on the approval card and in the logs.
        return {
            "attached": False,
            "outcome": result.outcome,
            "servers_probed": result.probed,
            "tools_screened": result.screened,
            "candidates_rejected": len(result.rejected),
        }

    commit(tool_context.state, result)
    attachment = result.approved
    return {
        "attached": True,
        "outcome": result.outcome,
        "tool": attachment.granted_tools[0] if attachment.granted_tools else None,
        "granted_scopes": list(attachment.granted_scopes),
        "servers_probed": result.probed,
        "tools_screened": result.screened,
    }


def _attached_names(tool_context: ToolContext) -> list[str]:
    from toolsmith.config import ATTACHED_STATE_KEY

    records = tool_context.state.get(ATTACHED_STATE_KEY) or []
    return [name for r in records for name in r.get("granted_tools", [])]


def build_orchestrator() -> LlmAgent:
    return LlmAgent(
        name="toolsmith",
        model=ORCHESTRATOR_MODEL,
        description="Acts for the user, acquiring tools it lacks.",
        instruction=INSTRUCTION,
        generate_content_config=DETERMINISTIC,
        tools=[
            # Starts empty; fills as things are approved.
            ToolsmithToolset(),
            FunctionTool(acquire_capability),
        ],
    )
