"""The attach mechanism.

This is the piece that makes the agent's capability set mutable at runtime.
The orchestrator is constructed once, with this toolset in its `tools` list.
It starts out exposing nothing. As candidates are screened and approved, a
record lands in session state and the very next `get_tools()` call surfaces
that server's tools -- scoped down to exactly what was granted.

Two details carry the security property, and neither is a prompt instruction:

* `tool_filter` is handed to McpToolset, so a server cannot expose a tool the
  user did not approve. If a server adds `delete_repo` after approval, it is
  filtered out at listing time rather than trusted to behave.
* `_use_invocation_cache` is disabled. The base class caches the tool list per
  invocation, which is the right default for a static toolset and exactly
  wrong here -- approval happens mid-conversation and must take effect on the
  next turn, not the next invocation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.base_toolset import BaseToolset
from google.adk.tools.mcp_tool.mcp_session_manager import (
    StreamableHTTPConnectionParams,
)
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset

from toolsmith.config import ATTACHED_STATE_KEY

logger = logging.getLogger(__name__)

# Long enough for a Cloud Run instance to start from zero.
SESSION_TIMEOUT_S = 30.0


def _cause(exc: BaseException) -> str:
    """The innermost reason, without the chain that wraps it."""
    while exc.__cause__ is not None:
        exc = exc.__cause__
    return f"{type(exc).__name__}: {exc}"[:160]


@dataclass(frozen=True)
class Attachment:
    """One approved third-party MCP server.

    Written to session state only after a screener verdict and an explicit
    human approval. Nothing else may create one.
    """

    server_id: str
    url: str
    # The exact tool names the user approved. Anything else the server offers
    # is filtered out before the model ever sees it.
    granted_tools: tuple[str, ...]
    # Credential scopes minted for this attachment, for audit and for the card.
    granted_scopes: tuple[str, ...] = ()
    headers: dict[str, str] = field(default_factory=dict)

    @property
    def cache_key(self) -> str:
        return f"{self.server_id}|{','.join(sorted(self.granted_tools))}"

    @classmethod
    def from_state(cls, raw: dict[str, Any]) -> "Attachment":
        return cls(
            server_id=raw["server_id"],
            url=raw["url"],
            granted_tools=tuple(raw.get("granted_tools", ())),
            granted_scopes=tuple(raw.get("granted_scopes", ())),
            headers=dict(raw.get("headers", {})),
        )


class ToolsmithToolset(BaseToolset):
    """Exposes exactly the tools that have been screened and approved."""

    def __init__(self) -> None:
        super().__init__()
        # See module docstring: the whole point is that this list changes.
        self._use_invocation_cache = False
        self._delegates: dict[str, McpToolset] = {}

    async def get_tools(
        self, readonly_context: Optional[ReadonlyContext] = None
    ) -> list[BaseTool]:
        if readonly_context is None:
            # No context means no session state, which means nothing has been
            # approved. Failing closed is the only safe default here.
            return []

        raw = readonly_context.state.get(ATTACHED_STATE_KEY) or []
        attachments = [Attachment.from_state(r) for r in raw]

        tools: list[BaseTool] = []
        for att in attachments:
            try:
                delegate = self._delegate_for(att)
                tools.extend(await delegate.get_tools(readonly_context))
            except Exception as exc:  # noqa: BLE001
                # A misbehaving third-party server must not take down the
                # agent. Drop it and keep the rest of the capability set.
                #
                # Logged as one line rather than a stack. The traceback is
                # forty lines of someone else's library and says nothing the
                # first line does not, and a wall of it scrolling past makes
                # a handled failure look like a crash.
                logger.warning(
                    "attached server %s failed to list tools: %s",
                    att.server_id,
                    _cause(exc),
                )

        return tools

    def _delegate_for(self, att: Attachment) -> McpToolset:
        delegate = self._delegates.get(att.cache_key)
        if delegate is None:
            delegate = McpToolset(
                connection_params=StreamableHTTPConnectionParams(
                    url=att.url,
                    headers=dict(att.headers),
                    # The default is five seconds, which is the time an
                    # already-running server needs and not the time a
                    # scaled-to-zero one needs to wake up. A cold instance
                    # loses the session before it has finished starting, and
                    # the tool then looks broken rather than slow.
                    timeout=SESSION_TIMEOUT_S,
                ),
                # Framework-level least privilege.
                tool_filter=list(att.granted_tools),
                tool_name_prefix=att.server_id,
            )
            self._delegates[att.cache_key] = delegate
        return delegate

    async def close(self) -> None:
        for delegate in self._delegates.values():
            try:
                await delegate.close()
            except Exception as exc:  # noqa: BLE001
                logger.warning("failed to close delegate toolset: %s", _cause(exc))
        self._delegates.clear()


def record_attachment(state: dict[str, Any], att: Attachment) -> None:
    """Commit an approved attachment to session state.

    Call sites for this function are the audit surface: if it is called
    anywhere that is not downstream of a human approval, the security model is
    broken.
    """
    existing = list(state.get(ATTACHED_STATE_KEY) or [])
    existing.append(
        {
            "server_id": att.server_id,
            "url": att.url,
            "granted_tools": list(att.granted_tools),
            "granted_scopes": list(att.granted_scopes),
            "headers": dict(att.headers),
        }
    )
    state[ATTACHED_STATE_KEY] = existing
