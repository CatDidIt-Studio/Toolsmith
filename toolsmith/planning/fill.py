"""Finding something for the steps nothing can do yet.

A plan with a gap is a refusal. This turns it into a question, by going out
and looking for a tool that would close it -- and screening whatever it finds
before that tool appears anywhere near the card.

The result still lands in a single approval. The user is agreeing to two
things at once, though, and the card must not blur them: run this task, and
attach these tools to do it. So a filled gap keeps its screening verdict and
its provenance attached, and its permissions are marked as new rather than
folded into the totals.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from toolsmith.planning.schema import PlannedStep
from toolsmith.relevance import select_relevant
from toolsmith.registry.client import ServerCandidate
from toolsmith.registry.discovery import discover
from toolsmith.sandbox.backends import Sandbox
from toolsmith.screening.candidate import Candidate
from toolsmith.screening.checks import probe_findings
from toolsmith.screening.runner import screen_candidate
from toolsmith.screening.schema import Verdict

logger = logging.getLogger(__name__)

# A gap is worth a few connections, not a search of the whole registry. Every
# probe is a first contact with unvetted code, and the user is waiting.
MAX_PROBES_PER_GAP = 3
MAX_TOOLS_PER_SERVER = 3


@dataclass
class GapFill:
    """A screened candidate that would close one gap."""

    step: PlannedStep
    candidate: Candidate
    verdict: Verdict
    server: ServerCandidate
    endpoint: str
    tool_name: str

    @property
    def granted_scopes(self) -> tuple[str, ...]:
        return tuple(self.verdict.granted_scopes)


async def fill_gap(
    step: PlannedStep, *, sandbox: Sandbox, attached_tool_names: list[str] | None = None
) -> GapFill | None:
    """Look for one tool that closes this step, screened and ready to show."""
    capability = step.needs or step.action
    discovery = await discover(capability)

    for triaged in discovery.probe[:MAX_PROBES_PER_GAP]:
        server = triaged.candidate
        remote = server.connectable
        if remote is None:
            continue

        probe = await sandbox.run(remote.url)
        if any(f.severity == "block" for f in probe_findings(probe)):
            continue

        # Screen the tools that could plausibly do this step, not whichever
        # ones the server happened to list first. Without this a gap for
        # "invite a collaborator" gets filled by a server's `create_issue`,
        # and the plan then claims to be achievable using a tool that cannot
        # perform the step.
        relevant = await select_relevant(
            capability,
            probe.tools,
            describe=lambda t: f"{t.name}: {t.description[:300]}",
            limit=MAX_TOOLS_PER_SERVER,
            app_name="toolsmith-fill",
            always=True,
        )
        if not relevant:
            # Nothing here serves the step. A server matching the search is
            # not a server that can do the job, and closing the gap with
            # something irrelevant would make the plan claim to be achievable
            # when it is not.
            continue

        for tool in relevant:
            candidate = tool.to_candidate(
                server_id=server.name,
                requested_scopes=[h.name for h in remote.headers if h.secret],
                publisher=server.name.split("/", 1)[0],
                signed=False,
            )
            verdict, _ = await screen_candidate(
                candidate,
                task_summary=capability,
                attached_tool_names=attached_tool_names or [],
            )
            if verdict.blocked:
                continue
            return GapFill(
                step=step,
                candidate=candidate,
                verdict=verdict,
                server=server,
                endpoint=remote.url,
                tool_name=tool.name,
            )

    return None


async def fill_gaps(
    steps: list[PlannedStep],
    *,
    sandbox: Sandbox,
    attached_tool_names: list[str] | None = None,
) -> list[GapFill]:
    """Close what can be closed, concurrently.

    Gaps are independent, and a plan with three of them should not take three
    times as long to price. A gap that cannot be filled simply stays a gap --
    a failure here is an answer, not an error.
    """
    if not steps:
        return []

    async def one(step: PlannedStep) -> GapFill | None:
        try:
            return await fill_gap(
                step, sandbox=sandbox, attached_tool_names=attached_tool_names
            )
        except Exception:
            logger.exception("gap fill failed for %r", step.action)
            return None

    results = await asyncio.gather(*(one(step) for step in steps))
    return [fill for fill in results if fill is not None]


def attachments_from(fills: list[GapFill]) -> list["Attachment"]:
    """Turn approved fills into attachments the executor can actually use.

    This is the only place a screened candidate becomes something the agent
    holds, and it runs after approval rather than after screening. A candidate
    that passed screening has been judged safe to *offer*; it is the person
    saying yes that makes it safe to attach, and keeping those two steps apart
    is the difference between a card and a notification.

    Each one is granted only the tool that closed its step. A server offering
    forty tools does not get forty tools attached because one of them was
    useful.
    """
    from toolsmith.attach.toolset import Attachment

    return [
        Attachment(
            server_id=fill.server.name,
            url=fill.endpoint,
            granted_tools=(fill.tool_name,),
            granted_scopes=fill.granted_scopes,
        )
        for fill in fills
    ]
