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

from fastapi import FastAPI
from pydantic import BaseModel, Field

from toolsmith.sandbox.probe import probe

app = FastAPI(title="toolsmith-sandbox")


class ProbeRequest(BaseModel):
    endpoint: str
    # Passed through for servers that refuse to list without one. Nothing here
    # is stored, logged, or reused.
    headers: dict[str, str] = Field(default_factory=dict)


@app.post("/probe")
async def run_probe(request: ProbeRequest) -> dict:
    result = await probe(request.endpoint, headers=request.headers or None)
    return result.as_dict()


@app.get("/healthz")
async def healthz() -> dict:
    return {"ok": True}
