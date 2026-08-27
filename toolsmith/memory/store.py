"""What Toolsmith remembers between sessions.

This exists because one of the checks did not work without it. Rug-pull
detection compares a tool's description against the one that was approved
before -- and nothing was ever filling in "before". `previous_description`
had a default of None and no caller in the pipeline passed it, so the check
was live code that could not fire outside the test corpus.

A server that quietly rewrites itself after approval is the failure this
product most needs to catch, and catching it is not a matter of judgement.
It requires having seen the entry the first time. So memory is not a
component added for completeness; it is the half of a check that was
missing.

Two backends, one interface. Firestore is the real one and survives a
restart. The local file is for development, and says so rather than
pretending.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

logger = logging.getLogger(__name__)

TOOLS = "seen_tools"
ATTACHMENTS = "attachments"
AUDIT = "audit"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ToolMemory:
    """A tool definition as it was when we last looked at it."""

    server_id: str
    tool_name: str
    description: str
    first_seen: str = field(default_factory=_now)
    last_seen: str = field(default_factory=_now)
    approved_at: str | None = None

    @property
    def key(self) -> str:
        return f"{self.server_id}::{self.tool_name}".replace("/", "__")


@dataclass
class AuditEntry:
    """One thing that happened, in a form somebody could review afterwards.

    Granted and used are recorded separately on purpose. A permission that was
    approved and never exercised is the most useful thing an audit can show --
    it is the evidence for narrowing the grant next time, and the answer to
    "what did it actually do with that access".
    """

    at: str
    task: str
    kind: str
    detail: str = ""
    granted_scopes: list[str] = field(default_factory=list)
    used_tools: list[str] = field(default_factory=list)
    refused_tools: list[str] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)


class MemoryBank(Protocol):
    @property
    def durable(self) -> bool: ...
    def recall_tool(self, server_id: str, tool_name: str) -> ToolMemory | None: ...
    def remember_tool(self, memory: ToolMemory) -> None: ...
    def record(self, entry: AuditEntry) -> None: ...
    def trail(self, limit: int = 50) -> list[AuditEntry]: ...


class LocalMemory:
    """A JSON file. Development only, and not shared between machines."""

    durable = False

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or Path(os.getenv("TOOLSMITH_MEMORY_FILE", ".toolsmith-memory.json"))
        self._data: dict[str, Any] = {TOOLS: {}, AUDIT: []}
        if self.path.exists():
            try:
                self._data = json.loads(self.path.read_text())
            except (OSError, json.JSONDecodeError):
                logger.warning("memory file unreadable, starting empty: %s", self.path)

    def _flush(self) -> None:
        self.path.write_text(json.dumps(self._data, indent=2))

    def recall_tool(self, server_id: str, tool_name: str) -> ToolMemory | None:
        raw = self._data[TOOLS].get(ToolMemory(server_id, tool_name, "").key)
        return ToolMemory(**raw) if raw else None

    def remember_tool(self, memory: ToolMemory) -> None:
        self._data[TOOLS][memory.key] = asdict(memory)
        self._flush()

    def record(self, entry: AuditEntry) -> None:
        self._data[AUDIT].append(asdict(entry))
        self._flush()

    def trail(self, limit: int = 50) -> list[AuditEntry]:
        return [AuditEntry(**e) for e in self._data[AUDIT][-limit:]][::-1]


class FirestoreMemory:
    """Persistent, and shared by every instance of the agent."""

    durable = True

    def __init__(self, project: str | None = None, prefix: str = "toolsmith") -> None:
        from google.cloud import firestore

        self._db = firestore.Client(project=project) if project else firestore.Client()
        self._prefix = prefix

    def _col(self, name: str):
        return self._db.collection(f"{self._prefix}_{name}")

    def recall_tool(self, server_id: str, tool_name: str) -> ToolMemory | None:
        key = ToolMemory(server_id, tool_name, "").key
        snapshot = self._col(TOOLS).document(key).get()
        return ToolMemory(**snapshot.to_dict()) if snapshot.exists else None

    def remember_tool(self, memory: ToolMemory) -> None:
        self._col(TOOLS).document(memory.key).set(asdict(memory))

    def record(self, entry: AuditEntry) -> None:
        self._col(AUDIT).add(asdict(entry))

    def trail(self, limit: int = 50) -> list[AuditEntry]:
        from google.cloud import firestore

        docs = (
            self._col(AUDIT)
            .order_by("at", direction=firestore.Query.DESCENDING)
            .limit(limit)
            .stream()
        )
        return [AuditEntry(**d.to_dict()) for d in docs]


def get_memory() -> MemoryBank:
    """Firestore when configured, a local file otherwise.

    Unlike the sandbox, falling back here is safe and so it is allowed. A
    missing memory means drift cannot be detected against past sessions, which
    is a weaker product -- not a silently unsafe one, the way a sandbox
    fallback would be.
    """
    project = os.getenv("TOOLSMITH_FIRESTORE_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT")
    if project:
        try:
            return FirestoreMemory(project)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Firestore unavailable (%s); using local memory", exc)
    return LocalMemory()
