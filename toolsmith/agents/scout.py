"""Turns a capability gap into registry queries.

Worth being clear about which side of the trust boundary this sits on. Scout
reads the orchestrator's abstracted description of what capability is missing
-- trusted input -- and emits search terms. It never reads registry output;
parsing hits is code, and judging them is the screener's job. So this agent
gets no attacker-controlled text and needs no isolation beyond a schema.

The reason it needs a model at all is that the official registry does not do
semantic search. It matches substrings, so "github issue" returns nothing
while "github" returns fifty results and "issue" returns six. Turning a stated
need into the handful of single tokens that actually hit is a language problem
with no clean rule behind it.
"""

from __future__ import annotations

from typing import Literal

from google.adk.agents import LlmAgent
from pydantic import BaseModel, Field

from toolsmith.config import DETERMINISTIC, SCOUT_MODEL


class QueryPlan(BaseModel):
    queries: list[str] = Field(min_length=1, max_length=6)


INSTRUCTION = """\
You turn a missing capability into search terms for the MCP server registry.

The registry does not understand phrases. It matches substrings against server
names and descriptions, so a multi-word query almost always returns nothing
while a single word returns plenty. Word forms are not interchangeable either:
"issue" and "issues" return different result sets.

Produce single words only. No phrases, no quotes, no operators.

Cover the need from more than one angle, because publishers name things
inconsistently: the platform or vendor ("github", "slack"), the object being
acted on ("issue", "ticket"), and the singular and plural of anything central
to the task. Prefer terms a publisher would plausibly put in a server name.

Between four and six terms is usually right. Fewer misses whole corners of the
registry; more mostly returns the same servers again.
"""


def build_scout(*, as_root: bool = False) -> LlmAgent:
    return LlmAgent(
        name="scout",
        model=SCOUT_MODEL,
        description="Translates a capability gap into registry search terms.",
        instruction=INSTRUCTION,
        tools=[],
        generate_content_config=DETERMINISTIC,
        include_contents="none",
        output_schema=QueryPlan,
        mode="task" if as_root else "single_turn",
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
    )
