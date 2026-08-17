"""First contact with an unvetted MCP server.

The registry publishes no tool information, so the descriptions and parameter
schemas that screening actually judges do not exist until someone connects and
asks. That connection is the risky act this whole product is arranged around,
which is why it happens here -- in code that holds no credentials, returns
data rather than objects, and is meant to run somewhere disposable.

What comes back is untrusted in the strongest sense: strings chosen by whoever
published the server, arriving in the shape they chose. Nothing here
interprets them. Probing collects; screening judges.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from toolsmith.screening.candidate import Candidate

# Caps, because a hostile server controls the size of everything it returns.
MAX_TOOLS = 60
MAX_DESCRIPTION_CHARS = 4000
DEFAULT_TIMEOUT_S = 20.0


@dataclass(frozen=True)
class ProbedTool:
    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)

    def to_candidate(
        self,
        *,
        server_id: str,
        requested_scopes: list[str],
        publisher: str | None = None,
        signed: bool = False,
        previous_description: str | None = None,
    ) -> Candidate:
        return Candidate(
            server_id=server_id,
            tool_name=self.name,
            description=self.description,
            input_schema=self.input_schema,
            requested_scopes=requested_scopes,
            publisher=publisher,
            signed=signed,
            previous_description=previous_description,
        )


@dataclass(frozen=True)
class ProbeResult:
    endpoint: str
    ok: bool
    tools: tuple[ProbedTool, ...] = ()
    error: str | None = None
    seconds: float = 0.0
    server_name: str | None = None
    server_version: str | None = None
    # True when two consecutive listings disagreed. A server that answers
    # differently the second time is deciding what to show based on something,
    # and whatever that something is, it is not in the tool definitions we
    # would have screened.
    unstable_listing: bool = False
    truncated: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "endpoint": self.endpoint,
            "ok": self.ok,
            "error": self.error,
            "seconds": self.seconds,
            "server_name": self.server_name,
            "server_version": self.server_version,
            "unstable_listing": self.unstable_listing,
            "truncated": self.truncated,
            "tools": [
                {"name": t.name, "description": t.description, "input_schema": t.input_schema}
                for t in self.tools
            ],
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ProbeResult":
        return cls(
            endpoint=raw["endpoint"],
            ok=bool(raw["ok"]),
            tools=tuple(
                ProbedTool(
                    name=t.get("name", ""),
                    description=t.get("description", "") or "",
                    input_schema=t.get("input_schema") or {},
                )
                for t in raw.get("tools", [])
            ),
            error=raw.get("error"),
            seconds=float(raw.get("seconds", 0.0)),
            server_name=raw.get("server_name"),
            server_version=raw.get("server_version"),
            unstable_listing=bool(raw.get("unstable_listing")),
            truncated=bool(raw.get("truncated")),
        )


def _collect(tools: list[Any]) -> tuple[tuple[ProbedTool, ...], bool]:
    truncated = len(tools) > MAX_TOOLS
    collected = tuple(
        ProbedTool(
            name=(t.name or "")[:200],
            description=(t.description or "")[:MAX_DESCRIPTION_CHARS],
            input_schema=t.inputSchema if isinstance(t.inputSchema, dict) else {},
        )
        for t in tools[:MAX_TOOLS]
    )
    return collected, truncated


def _signature(tools: tuple[ProbedTool, ...]) -> list[tuple[str, str]]:
    return sorted((t.name, t.description) for t in tools)


async def probe(
    endpoint: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT_S,
) -> ProbeResult:
    """Connect, list tools twice, and report what came back.

    Listing twice is cheap and catches a server that varies its answer between
    calls -- the shape a rug-pull takes when it is trying to survive being
    looked at rather than merely being republished.
    """
    started = time.monotonic()
    try:
        async with streamablehttp_client(endpoint, headers=headers, timeout=timeout) as (
            read,
            write,
            _,
        ):
            async with ClientSession(read, write) as session:
                init = await session.initialize()
                first, truncated = _collect((await session.list_tools()).tools)
                second, _ = _collect((await session.list_tools()).tools)

                info = getattr(init, "serverInfo", None)
                return ProbeResult(
                    endpoint=endpoint,
                    ok=True,
                    tools=first,
                    seconds=time.monotonic() - started,
                    server_name=getattr(info, "name", None),
                    server_version=getattr(info, "version", None),
                    unstable_listing=_signature(first) != _signature(second),
                    truncated=truncated,
                )
    except Exception as exc:  # noqa: BLE001
        # A server that will not answer is not screened as safe. It is simply
        # unusable, and saying so is the whole result.
        return ProbeResult(
            endpoint=endpoint,
            ok=False,
            error=_describe(exc),
            seconds=time.monotonic() - started,
        )


def _describe(exc: BaseException) -> str:
    """Say what actually went wrong.

    The MCP client runs its transport inside an anyio task group, so almost
    every failure surfaces as `ExceptionGroup: unhandled errors in a TaskGroup
    (1 sub-exception)` -- which is indistinguishable between a dead host, a
    refused auth handshake and a wrong transport. Those are three different
    findings, so the group is unwrapped to the causes underneath.
    """
    causes: list[str] = []

    def walk(e: BaseException) -> None:
        if isinstance(e, BaseExceptionGroup):
            for sub in e.exceptions:
                walk(sub)
        else:
            causes.append(f"{type(e).__name__}: {e}".strip().rstrip(":"))

    walk(exc)
    # Preserve order while dropping repeats; a fan-out failure often reports
    # the same cause several times.
    seen: set[str] = set()
    unique = [c for c in causes if not (c in seen or seen.add(c))]
    return "; ".join(unique)[:500] or f"{type(exc).__name__}"
