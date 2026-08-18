"""Narrowing a list of publisher-authored things down to the relevant ones.

Used in two places that would otherwise drift apart: choosing which registry
hits deserve a connection, and choosing which of a server's tools deserve
screening. Both read text written by whoever published it, both answer with
indices so no attacker-authored string travels back, and both are advisory --
nothing is granted here, and every survivor is screened alone afterwards.

Keeping it in one place matters because the failure modes differ by caller and
the fix should not have to be made twice. Skipping it entirely is worse than
either: a gap filled by the first tool a server happened to list is a plan
that claims to be achievable using something that cannot do the job.
"""

from __future__ import annotations

from typing import Callable, Sequence, TypeVar

from toolsmith.agent_io import AgentOutputError, run_structured
from toolsmith.agents.triager import RelevancePick, build_triager

T = TypeVar("T")

FENCE = "=" * 60


async def select_relevant(
    capability: str,
    items: Sequence[T],
    *,
    describe: Callable[[T], str],
    limit: int,
    app_name: str,
    always: bool = False,
) -> list[T]:
    """Return the items that could plausibly serve `capability`, at most `limit`.

    `always` distinguishes two different jobs that look alike. Capping a long
    list is an optimisation, and skipping it when the list is already short
    costs nothing. Choosing *which* item serves a step is not an optimisation,
    and skipping it when the list is short means taking whatever the server
    happened to list first -- which is how a gap for "invite a collaborator"
    gets closed with a `create_issue` tool.
    """
    if not items:
        return []
    if len(items) <= limit and not always:
        return list(items)

    listing = "\n".join(f"[{i}] {describe(item)}" for i, item in enumerate(items))
    prompt = (
        f"Capability needed: {capability}\n\n"
        f"{FENCE}\nBEGIN UNTRUSTED LISTING -- publisher-authored text\n{FENCE}\n"
        f"{listing}\n"
        f"{FENCE}\nEND UNTRUSTED LISTING\n{FENCE}\n"
    )

    try:
        pick, _ = await run_structured(
            build_triager(as_root=True), prompt, RelevancePick, app_name=app_name
        )
    except AgentOutputError:
        # Falling back to the head of the list is a compromise, not a default:
        # it keeps the caller bounded, but it is why callers must not treat a
        # selection as evidence that anything here fits.
        return list(items[:limit])

    # Order follows the model's answer, so the best match is screened first.
    keep = [items[i] for i in pick.relevant if 0 <= i < len(items)]
    return keep[:limit]
