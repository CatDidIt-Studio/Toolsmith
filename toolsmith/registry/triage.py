"""Tier-1 triage: what can be decided before connecting to anything.

Screening splits in two because the registry does, and the split is not
cosmetic. Everything here is derived from metadata the registry hands over for
free -- status, versions, timestamps, declared credential requirements. None
of it requires opening a connection to a server nobody has vetted.

Tier 2, where tool descriptions and parameter schemas live, requires exactly
that connection. So triage exists to make sure the list of servers we are
willing to connect to is as short and as defensible as possible, because every
entry on it is a first contact with untrusted code.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from toolsmith.registry.client import ServerCandidate

Disposition = Literal["probe", "skip"]


@dataclass(frozen=True)
class Triaged:
    candidate: ServerCandidate
    disposition: Disposition
    reasons: tuple[str, ...]

    @property
    def should_probe(self) -> bool:
        return self.disposition == "probe"


def triage(candidate: ServerCandidate) -> Triaged:
    reasons: list[str] = []
    skip = False

    if candidate.status == "deprecated":
        reasons.append("registry marks this server deprecated")
        skip = True
    elif candidate.status != "active":
        reasons.append(f"registry status is {candidate.status!r}")

    if candidate.connectable is None:
        # Package-only entries would have to be installed and executed to see
        # their tools. That is a much larger trust decision than opening a
        # connection, and this agent does not make it.
        reasons.append("no reachable endpoint; package-only entry")
        skip = True

    if candidate.republished_since_publish:
        reasons.append("republished since first publication")

    remote = candidate.connectable
    if remote is not None and remote.demands_secret:
        secrets = ", ".join(h.name for h in remote.headers if h.secret)
        reasons.append(f"requires a secret before it will answer: {secrets}")

    return Triaged(
        candidate=candidate,
        disposition="skip" if skip else "probe",
        reasons=tuple(reasons),
    )


def dedupe_by_name(candidates: list[ServerCandidate]) -> list[ServerCandidate]:
    """Collapse repeated names, preferring an entry we can actually reach.

    The registry carries several versions of the same server, and newer is not
    automatically better: `com.mcparmory/github` publishes v1.0.3 with a remote
    endpoint and v1.0.4 and v1.0.6 without one. Taking the highest version
    would silently discard the only version that can be screened at all.
    """
    best: dict[str, ServerCandidate] = {}
    for candidate in candidates:
        current = best.get(candidate.name)
        if current is None:
            best[candidate.name] = candidate
            continue
        if current.connectable is None and candidate.connectable is not None:
            best[candidate.name] = candidate
        elif (current.connectable is None) == (candidate.connectable is None):
            if candidate.version > current.version:
                best[candidate.name] = candidate
    return list(best.values())
