"""Capability gap in, a short list of servers worth connecting to out."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from toolsmith.agent_io import AgentOutputError, run_structured
from toolsmith.agents.scout import QueryPlan, build_scout
from toolsmith.agents.triager import RelevancePick, build_triager
from toolsmith.registry.client import ServerCandidate, search
from toolsmith.registry.triage import Triaged, dedupe_by_name, triage

APP_NAME = "toolsmith-scout"


@dataclass(frozen=True)
class Discovery:
    capability: str
    queries: tuple[str, ...]
    probe: tuple[Triaged, ...]
    skipped: tuple[Triaged, ...]
    seconds: float

    @property
    def summary(self) -> str:
        return (
            f"{len(self.queries)} queries -> "
            f"{len(self.probe) + len(self.skipped)} distinct servers, "
            f"{len(self.probe)} worth connecting to"
        )


async def discover(capability: str, *, per_query: int = 25) -> Discovery:
    plan, scout_seconds = await run_structured(
        build_scout(as_root=True),
        f"Missing capability: {capability}",
        QueryPlan,
        app_name=APP_NAME,
    )

    results = await asyncio.gather(
        *(search(q, limit=per_query) for q in plan.queries),
        return_exceptions=True,
    )

    hits: list[ServerCandidate] = []
    for result in results:
        # One dead query should not sink discovery; the other terms still
        # cover the field.
        if isinstance(result, BaseException):
            continue
        hits.extend(result)

    triaged = [triage(c) for c in dedupe_by_name(hits)]
    probe = [t for t in triaged if t.should_probe]
    skipped = [t for t in triaged if not t.should_probe]

    relevant, relevance_seconds = await _filter_relevant(capability, probe)
    irrelevant = [t for t in probe if t not in relevant]
    skipped.extend(
        Triaged(
            candidate=t.candidate,
            disposition="skip",
            reasons=t.reasons + ("not relevant to the capability sought",),
        )
        for t in irrelevant
    )

    return Discovery(
        capability=capability,
        queries=tuple(plan.queries),
        probe=tuple(relevant),
        skipped=tuple(skipped),
        seconds=scout_seconds + relevance_seconds,
    )


_FENCE = "=" * 60


async def _filter_relevant(
    capability: str, candidates: list[Triaged]
) -> tuple[list[Triaged], float]:
    if not candidates:
        return [], 0.0

    # No further truncation here: the registry already ships descriptions cut
    # short with an ellipsis, so trimming again would judge on a fragment of a
    # fragment.
    listing = "\n".join(
        f"[{i}] {t.candidate.name}\n    {t.candidate.description}"
        for i, t in enumerate(candidates)
    )
    prompt = (
        f"Capability needed: {capability}\n\n"
        f"{_FENCE}\nBEGIN UNTRUSTED REGISTRY LISTING -- publisher-authored text\n{_FENCE}\n"
        f"{listing}\n"
        f"{_FENCE}\nEND UNTRUSTED REGISTRY LISTING\n{_FENCE}\n"
    )

    try:
        pick, seconds = await run_structured(
            build_triager(as_root=True), prompt, RelevancePick, app_name=APP_NAME
        )
    except AgentOutputError:
        # Failing open here means probing everything, which is noisy but not
        # unsafe: relevance never grants anything, and each candidate is still
        # screened in isolation before it can be attached.
        return candidates, 0.0

    keep = {i for i in pick.relevant if 0 <= i < len(candidates)}
    return [t for i, t in enumerate(candidates) if i in keep], seconds
