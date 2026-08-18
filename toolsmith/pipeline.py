"""Capability acquisition, end to end.

Deliberately plain code rather than an agent loop. The order of these steps is
the security property -- probe before screening because there is nothing to
screen until you connect, screen before showing a card because a card without
a verdict is just an install prompt, and a card before attaching because
nothing gets a credential without a person saying so. A model that could
reorder or skip a step could be argued into skipping the right one.

So judgment stays with the models, at three named points: which search terms,
which candidates are worth a connection, and whether a tool definition is
safe. The sequence stays here.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from toolsmith.agent_io import AgentOutputError, run_structured
from toolsmith.agents.triager import RelevancePick, build_triager
from toolsmith.approval.model import STORE, ApprovalRequest, Provenance
from toolsmith.attach.toolset import Attachment, record_attachment
from toolsmith.registry.discovery import discover
from toolsmith.registry.triage import Triaged
from toolsmith.relevance import select_relevant
from toolsmith.sandbox.backends import Sandbox
from toolsmith.screening.checks import probe_findings
from toolsmith.screening.runner import screen_candidate
from toolsmith.screening.schema import Verdict

logger = logging.getLogger(__name__)

# How many servers we are willing to open a connection to for one capability.
# Every probe is a first contact, so this is a safety budget, not a
# performance one.
MAX_PROBES = 4
# How many tools from a single server get screened. A server offering fifty
# tools is not offering fifty answers to this question.
#
# This cap exists for latency as much as safety. Screening every tool on every
# probed server would be dozens of model calls per acquisition, which would
# quietly turn seconds-scale in-loop screening into exactly the minutes-scale
# batch job this is supposed to be an alternative to. So the tool list is
# narrowed first, by the same cheap relevance pass used on registry hits, and
# only the survivors are screened.
MAX_TOOLS_PER_SERVER = 3
_FENCE = "=" * 60


@dataclass
class Rejected:
    server: str
    stage: str
    reason: str


@dataclass
class Acquisition:
    capability: str
    approved: Attachment | None = None
    request: ApprovalRequest | None = None
    rejected: list[Rejected] = field(default_factory=list)
    probed: int = 0
    screened: int = 0

    @property
    def acquired(self) -> bool:
        return self.approved is not None

    @property
    def outcome(self) -> str:
        """Why acquisition ended the way it did.

        Worth distinguishing carefully, because the agent narrates this to the
        user and the difference is not cosmetic. "A person declined this" and
        "nothing was found worth showing anyone" are very different statements,
        and reporting the first when the second happened invents a decision the
        user never made.
        """
        if self.approved is not None:
            return "attached"
        if any(r.stage == "approval" for r in self.rejected):
            return "declined_by_user"
        if self.screened:
            return "screening_rejected_all"
        if self.probed:
            return "no_server_answered"
        return "nothing_found"


async def acquire(
    capability: str,
    *,
    task_summary: str,
    sandbox: Sandbox,
    attached_tool_names: list[str] | None = None,
    approval_timeout: float | None = 300.0,
) -> Acquisition:
    """Find, screen and -- if a person agrees -- attach one capability."""
    result = Acquisition(capability=capability)

    if not sandbox.isolated:
        logger.warning(
            "acquiring with a non-isolated sandbox; first contact will happen "
            "in this process"
        )

    discovery = await discover(capability)
    logger.info("discovery: %s", discovery.summary)

    for triaged in discovery.probe[:MAX_PROBES]:
        candidate_server = triaged.candidate
        remote = candidate_server.connectable
        if remote is None:
            continue

        probe = await sandbox.run(remote.url)
        result.probed += 1

        transport_problems = probe_findings(probe)
        blocking = [f for f in transport_problems if f.severity == "block"]
        if blocking:
            result.rejected.append(
                Rejected(candidate_server.name, "probe", blocking[0].evidence)
            )
            continue

        for tool in await _select_tools(capability, probe.tools):
            candidate = tool.to_candidate(
                server_id=candidate_server.name,
                # The endpoint declares which secrets it wants before it will
                # answer; that is the closest thing to a scope request the MCP
                # ecosystem currently has.
                requested_scopes=[h.name for h in remote.headers if h.secret],
                publisher=_publisher(candidate_server.name),
                signed=False,
            )

            verdict, _ = await screen_candidate(
                candidate,
                task_summary=task_summary,
                attached_tool_names=attached_tool_names or [],
            )
            result.screened += 1

            verdict = _fold(verdict, transport_problems)
            if verdict.blocked:
                result.rejected.append(
                    Rejected(candidate_server.name, "screening", tool.name)
                )
                continue

            request = STORE.add(
                ApprovalRequest(
                    capability=capability,
                    tool=candidate,
                    verdict=verdict,
                    endpoint=remote.url,
                    provenance=Provenance(
                        server_name=candidate_server.name,
                        version=candidate_server.version,
                        repository_url=candidate_server.repository_url,
                        publisher=_publisher(candidate_server.name),
                        signed=False,
                        registry_status=candidate_server.status,
                        published_at=candidate_server.published_at,
                        updated_at=candidate_server.updated_at,
                    ),
                )
            )
            result.request = request

            decision = await request.wait(timeout=approval_timeout)
            if decision != "approved":
                result.rejected.append(
                    Rejected(candidate_server.name, "approval", decision)
                )
                return result

            attachment = Attachment(
                server_id=candidate_server.name,
                url=remote.url,
                granted_tools=(tool.name,),
                granted_scopes=tuple(verdict.granted_scopes),
            )
            result.approved = attachment
            return result

    return result


async def _select_tools(capability: str, tools) -> list:
    return await select_relevant(
        capability,
        tools,
        describe=lambda t: f"{t.name}: {t.description[:300]}",
        limit=MAX_TOOLS_PER_SERVER,
        app_name="toolsmith-tools",
    )


def _fold(verdict: Verdict, extra) -> Verdict:
    """Carry non-blocking probe observations onto the verdict shown to the user."""
    if not extra:
        return verdict
    return verdict.model_copy(update={"findings": list(verdict.findings) + list(extra)})


def _publisher(server_name: str) -> str:
    # Registry names are namespaced: "ai.smithery/foo", "io.github.someone/bar".
    return server_name.split("/", 1)[0] if "/" in server_name else server_name


def commit(state: dict, acquisition: Acquisition) -> None:
    """Write an approved attachment into session state.

    Separate from `acquire` on purpose. Acquisition decides; this is the only
    thing that changes what the agent can do, and keeping it to one call site
    keeps that surface auditable.
    """
    if acquisition.approved is None:
        return
    record_attachment(state, acquisition.approved)
