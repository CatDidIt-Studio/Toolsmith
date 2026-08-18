"""Client for the official MCP registry.

What the registry gives you is worth being precise about, because it shapes
the whole pipeline: server name, a server-level description, a version, a
repository link, connection details, and publish/update timestamps.

It does not give you tool definitions. There is no tool name, no parameter
schema, no per-tool description anywhere in the record.

That matters more than it sounds. Prompt injection lives in tool descriptions,
and tool descriptions are only visible after you connect to the server and
call `tools/list`. So the material you most need to screen cannot be obtained
without doing the exact thing screening is meant to make safe -- which is why
first contact happens inside the sandbox rather than in the agent's process.

Anything that searches a registry and attaches the winner is, structurally,
attaching on the strength of metadata nobody verified.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

from toolsmith.registry import catalog

logger = logging.getLogger(__name__)

REGISTRY_BASE = "https://registry.modelcontextprotocol.io/v0"
DEFAULT_TIMEOUT = 15.0


@dataclass(frozen=True)
class RemoteHeader:
    name: str
    description: str = ""
    required: bool = False
    secret: bool = False


@dataclass(frozen=True)
class Remote:
    transport: str
    url: str
    headers: tuple[RemoteHeader, ...] = ()

    @property
    def demands_secret(self) -> bool:
        return any(h.secret for h in self.headers)


@dataclass(frozen=True)
class ServerCandidate:
    """A registry hit. Tier-1 material only -- nothing here is tool-level."""

    name: str
    description: str
    version: str
    repository_url: str | None
    remotes: tuple[Remote, ...]
    status: str
    published_at: str | None
    updated_at: str | None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def connectable(self) -> Remote | None:
        """The remote we could actually reach, if any.

        Registry entries that ship only as installable packages have no
        endpoint to probe, so they cannot be screened at tool level without
        executing someone's package -- a much larger ask than opening a
        connection, and out of scope here.
        """
        for remote in self.remotes:
            if remote.transport in ("streamable-http", "sse"):
                return remote
        return None

    @property
    def republished_since_publish(self) -> bool:
        """Cheap drift signal available without connecting."""
        return bool(
            self.published_at and self.updated_at and self.updated_at != self.published_at
        )


def _parse(entry: dict[str, Any]) -> ServerCandidate:
    server = entry.get("server", {})
    meta = (entry.get("_meta") or {}).get(
        "io.modelcontextprotocol.registry/official", {}
    )

    remotes: list[Remote] = []
    for raw_remote in server.get("remotes") or []:
        headers = tuple(
            RemoteHeader(
                name=h.get("name", ""),
                description=h.get("description", ""),
                required=bool(h.get("isRequired")),
                secret=bool(h.get("isSecret")),
            )
            for h in (raw_remote.get("headers") or [])
        )
        remotes.append(
            Remote(
                transport=raw_remote.get("type", ""),
                url=raw_remote.get("url", ""),
                headers=headers,
            )
        )

    repository = server.get("repository") or {}
    return ServerCandidate(
        name=server.get("name", ""),
        description=server.get("description", ""),
        version=server.get("version", ""),
        repository_url=repository.get("url"),
        remotes=tuple(remotes),
        status=meta.get("status", "unknown"),
        published_at=meta.get("publishedAt"),
        updated_at=meta.get("updatedAt"),
        raw=entry,
    )


async def search(query: str, *, limit: int = 10) -> list[ServerCandidate]:
    """Search every configured source. Returns candidates in source order.

    No ranking is applied here on purpose. Deciding which candidate deserves a
    connection is a screening decision, and screening should see the field as
    the sources present it rather than a list this module has already quietly
    filtered.

    Local catalogue entries come first because they are the ones an operator
    chose to list, not because they are trusted -- they are parsed, triaged
    and screened on exactly the same path as anything off the public registry.
    """
    entries = list(catalog.search(query))

    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.get(
                f"{REGISTRY_BASE}/servers", params={"search": query, "limit": limit}
            )
            response.raise_for_status()
            entries.extend(response.json().get("servers", []))
    except Exception:
        # A public registry that is down should not take the local catalogue
        # with it. Losing a source narrows the field; it does not break
        # discovery.
        logger.warning("public registry unreachable for query %r", query)

    return [_parse(entry) for entry in entries]
