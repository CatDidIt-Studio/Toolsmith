"""The approval surface.

Every competitor to this idea puts tool installation behind a developer
settings screen. That is the wrong shape for the moment that matters: the
person deciding whether to hand a credential to a stranger's server is doing
it mid-task, in a few seconds, and needs the trade-off rendered rather than
the configuration.

So this is one page, one decision, and no navigation.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from toolsmith.approval.model import STORE
from toolsmith.memory.store import get_memory

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def tidy_evidence(text: str) -> str:
    """Make a quoted fragment readable without changing what it says.

    Evidence is verbatim by design -- it is what stops the screener reporting
    findings it cannot support -- but the screener often quotes out of a JSON
    payload, so the raw string arrives carrying escaped quotes and literal
    backslash-n. Rendering that as-is makes the most important line on the
    card look broken. Only escaping is undone here; no words are touched.
    """
    cleaned = text.replace("\\n", "\n").replace('\\"', '"').replace("\\'", "'")
    lines = [line.strip() for line in cleaned.splitlines()]
    return "\n".join(line for line in lines if line)


TEMPLATES.env.filters["tidy"] = tidy_evidence

app = FastAPI(title="Toolsmith")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    pending = STORE.pending()
    if len(pending) == 1:
        one = pending[0]
        route = "plan" if hasattr(one, "plan") else "approve"
        return RedirectResponse(f"/{route}/{one.id}", status_code=303)
    return TEMPLATES.TemplateResponse(
        request, "index.html", {"requests": STORE.all()}
    )


@app.get("/audit", response_class=HTMLResponse)
async def audit(request: Request) -> HTMLResponse:
    memory = get_memory()
    return TEMPLATES.TemplateResponse(
        request,
        "audit.html",
        {"entries": memory.trail(limit=50), "durable": memory.durable},
    )


@app.get("/plan/{plan_id}", response_class=HTMLResponse)
async def plan_card(request: Request, plan_id: str) -> HTMLResponse:
    approval = STORE.get(plan_id)
    if approval is None:
        raise HTTPException(status_code=404, detail="no such plan")
    return TEMPLATES.TemplateResponse(request, "plan.html", {"a": approval})


@app.post("/plan/{plan_id}")
async def decide_plan(plan_id: str, decision: str = Form(...)) -> RedirectResponse:
    approval = STORE.get(plan_id)
    if approval is None:
        raise HTTPException(status_code=404, detail="no such plan")
    if decision not in ("approved", "denied"):
        raise HTTPException(status_code=400, detail="decision must be approved or denied")
    try:
        approval.answer(decision)  # type: ignore[arg-type]
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return RedirectResponse(f"/plan/{plan_id}", status_code=303)


@app.get("/approve/{request_id}", response_class=HTMLResponse)
async def card(request: Request, request_id: str) -> HTMLResponse:
    approval = STORE.get(request_id)
    if approval is None:
        raise HTTPException(status_code=404, detail="no such approval request")
    return TEMPLATES.TemplateResponse(request, "card.html", {"a": approval})


@app.post("/approve/{request_id}")
async def decide(request_id: str, decision: str = Form(...)) -> RedirectResponse:
    approval = STORE.get(request_id)
    if approval is None:
        raise HTTPException(status_code=404, detail="no such approval request")
    if decision not in ("approved", "denied"):
        raise HTTPException(status_code=400, detail="decision must be approved or denied")
    try:
        approval.answer(decision)  # type: ignore[arg-type]
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return RedirectResponse(f"/approve/{request_id}", status_code=303)
