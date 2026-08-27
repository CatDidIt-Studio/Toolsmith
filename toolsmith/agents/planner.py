"""Works out what a task will take, before any of it is done.

This runs on the trusted side. Its input is the user's own request and the
inventory of tools already attached -- and those descriptions have been
through screening and approval already, which is what makes them safe to
read here. Nothing unscreened reaches this agent.

It is asked to be complete rather than optimistic. A planner that quietly
omits the step it has no tool for produces a plan that looks achievable and
fails halfway, which is worse than saying so up front -- the whole point of
planning before acting is that "this cannot be done, and here is what is
missing" arrives while it is still cheap.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent

from toolsmith.config import RETRY, DETERMINISTIC, ORCHESTRATOR_MODEL
from toolsmith.planning.schema import DraftPlan

INSTRUCTION = """\
You are given a task and the tools an agent currently holds. Work out every
step the task actually requires, and which held tool would perform each one.

Break the task down by what has to happen to the outside world, not by how you
would phrase it. "Open an issue and add a label" is two steps if labelling is
a separate call, one if the same tool does both. Reading counts: if a step has
to fetch something from somewhere before it can act, that is a step.

Thinking is not a step. Summarising, drafting, deciding, comparing, choosing
wording, working out what to write -- the agent does all of that itself, with
no tool and no permission. Listing those as steps invents a capability gap
that nothing can ever fill, and a plan carrying one looks impossible when it
is not. A step exists only where something outside the agent has to be read
or changed.

The test is whether it touches something the agent does not already have in
front of it. Fetching a file is a step. Reading a file that a previous step
already returned is not.

For each step, name the held tool that performs it in `tool`. Match on what the
tool does, not on what it is called. If no held tool does it, leave `tool`
null and describe the missing capability in `needs`, in plain words -- the kind
of thing needed, not a product or vendor name.

Never assign a tool that does not appear in the inventory, and never assign one
that almost fits. A step matched to the wrong tool becomes a failure in the
middle of the job, after permission was already granted for it. Leaving it
unmatched is how the user finds out in time.

Include the steps you have no tool for. A plan that omits them looks
achievable and is not, and being told the task is impossible now is worth more
than discovering it halfway through.
"""


def build_planner(*, as_root: bool = False) -> LlmAgent:
    return LlmAgent(
        name="planner",
        model=ORCHESTRATOR_MODEL,
        description="Decomposes a task into steps and matches them to held tools.",
        instruction=INSTRUCTION,
        tools=[],
        generate_content_config=DETERMINISTIC,
        retry_config=RETRY,
        include_contents="none",
        output_schema=DraftPlan,
        mode="task" if as_root else "single_turn",
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
    )
