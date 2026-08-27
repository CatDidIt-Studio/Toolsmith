"""The disposable probe service.

Deployed to Cloud Run and called by the agent with nothing but an endpoint. It
connects to the third-party MCP server, lists its tools, returns them as JSON,
and is torn down. It is given no credentials, no database, and no access to
anything the agent holds, so compromising it yields a container that can list
tools -- which is what it was already doing.

Kept deliberately small. Every capability added here is a capability an
attacker gets for free.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from pydantic import BaseModel, Field

from toolsmith.sandbox.probe import probe

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("sandbox")

# The transport libraries narrate every leg of an MCP session -- the POST, the
# negotiated version, the session id, the DELETE. In Cloud Run's log that
# buries the two lines worth reading under six that are not, and this log is
# the only record that first contact happened here rather than inside the
# agent. Quiet everything that is not this service speaking.
for _noisy in ("httpx", "httpcore", "mcp", "uvicorn.access"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

app = FastAPI(title="toolsmith-sandbox")


class ProbeRequest(BaseModel):
    endpoint: str
    # Passed through for servers that refuse to list without one. Nothing here
    # is stored, logged, or reused.
    headers: dict[str, str] = Field(default_factory=dict)


@app.post("/probe")
async def run_probe(request: ProbeRequest) -> dict:
    """Probe one server and say so.

    The endpoint, the outcome and the shape of what came back -- nothing the
    server wrote. Tool descriptions are the attacker-controlled part, and a
    log line is read by people and shipped to systems that were not expecting
    someone else's prose.

    Logged because this is the only record that first contact happened
    somewhere disposable rather than inside the agent. Without it, the claim
    is architecture on a slide.
    """
    logger.info("probing %s", request.endpoint)
    result = await probe(request.endpoint, headers=request.headers or None)
    if result.ok:
        logger.info(
            "  ok  %d tools in %.2fs%s",
            len(result.tools),
            result.seconds,
            "  UNSTABLE LISTING" if result.unstable_listing else "",
        )
    else:
        logger.info("  refused  %s", (result.error or "")[:120])
    return result.as_dict()


@app.get("/healthz")
async def healthz() -> dict:
    return {"ok": True}
