"""Where first contact happens.

One interface, two backends, and the difference between them is the entire
security claim -- so it is stated rather than buried.

`CloudRunSandbox` sends the endpoint to a disposable Cloud Run instance which
connects, lists, and dies. The agent's process never opens a socket to the
third-party server, and the instance holds no credentials, so a hostile server
gets a short-lived container with nothing in it.

`LocalSandbox` connects from this process. It provides no isolation at all,
which is fine while developing against servers you already trust and is
exactly the thing this product exists to stop people doing. It refuses to run
unless it has been asked for explicitly.
"""

from __future__ import annotations

import logging
import os
from typing import Protocol

import httpx

from toolsmith.config import SANDBOX_REGION, SANDBOX_SERVICE
from toolsmith.sandbox.probe import DEFAULT_TIMEOUT_S, ProbeResult, probe

logger = logging.getLogger(__name__)


class Sandbox(Protocol):
    async def run(
        self, endpoint: str, *, headers: dict[str, str] | None = None
    ) -> ProbeResult: ...

    @property
    def isolated(self) -> bool: ...


class LocalSandbox:
    """Development only. Connects from the agent's own process."""

    isolated = False

    def __init__(self, *, acknowledged: bool = False) -> None:
        if not acknowledged:
            raise RuntimeError(
                "LocalSandbox performs no isolation: it opens a connection to a "
                "third-party server from this process. Pass acknowledged=True if "
                "that is genuinely what you want, or use CloudRunSandbox."
            )

    async def run(
        self, endpoint: str, *, headers: dict[str, str] | None = None
    ) -> ProbeResult:
        logger.warning("probing %s WITHOUT isolation (local sandbox)", endpoint)
        return await probe(endpoint, headers=headers)


class CloudRunSandbox:
    """Probes from a throwaway Cloud Run instance."""

    isolated = True

    def __init__(self, service_url: str, *, timeout: float = DEFAULT_TIMEOUT_S + 15) -> None:
        self.service_url = service_url.rstrip("/")
        self.timeout = timeout

    async def run(
        self, endpoint: str, *, headers: dict[str, str] | None = None
    ) -> ProbeResult:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.service_url}/probe",
                    json={"endpoint": endpoint, "headers": headers or {}},
                )
                response.raise_for_status()
                return ProbeResult.from_dict(response.json())
        except Exception as exc:  # noqa: BLE001
            # The sandbox being unreachable must never read as "the server was
            # fine". No probe means no tool definitions, which means nothing to
            # screen and nothing to attach.
            return ProbeResult(
                endpoint=endpoint,
                ok=False,
                error=f"sandbox unreachable: {type(exc).__name__}: {exc}"[:500],
            )


def get_sandbox() -> Sandbox:
    """Cloud Run when configured, local only when explicitly allowed.

    Defaults matter here. If this fell back to the local backend whenever the
    service URL was missing, a misconfigured deploy would quietly start
    connecting to unvetted servers from the agent's own process -- the failure
    would look like everything working.
    """
    service_url = os.getenv("TOOLSMITH_SANDBOX_URL")
    if service_url:
        return CloudRunSandbox(service_url)

    if os.getenv("TOOLSMITH_ALLOW_LOCAL_SANDBOX") == "1":
        return LocalSandbox(acknowledged=True)

    raise RuntimeError(
        "No sandbox configured. Set TOOLSMITH_SANDBOX_URL to the deployed "
        f"probe service (expected service {SANDBOX_SERVICE!r} in {SANDBOX_REGION}), "
        "or set TOOLSMITH_ALLOW_LOCAL_SANDBOX=1 to probe from this process "
        "without isolation while developing."
    )
