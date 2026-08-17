"""Drives one screening pass.

Deliberately a single, short, isolated model call. The whole product claim is
that this is cheap enough to run in-loop while a human waits -- if screening
grows into a multi-turn agent that plans and retries, it stops being a
different problem from the offline MCP eval products and starts being a worse
version of them.
"""

from __future__ import annotations

import json
import time
import uuid

from google.adk.runners import FINISH_TASK_TOOL_NAME, InMemoryRunner
from google.genai import types

from toolsmith.agents.screener import build_screener
from toolsmith.screening.candidate import Candidate
from toolsmith.screening.checks import static_findings
from toolsmith.screening.schema import Finding, FindingCode, Verdict

APP_NAME = "toolsmith-screener"


class ScreeningError(RuntimeError):
    pass


async def screen_candidate(
    candidate: Candidate,
    *,
    task_summary: str,
    attached_tool_names: list[str] | None = None,
) -> tuple[Verdict, float]:
    """Return the verdict and how long it took, in seconds.

    Latency is returned rather than logged because it is a product metric
    here, not a diagnostic: a screener that takes 30s has failed even if its
    verdict is correct.
    """
    # Computed first, and never overridden by the judge.
    static = static_findings(candidate)

    runner = InMemoryRunner(agent=build_screener(as_root=True), app_name=APP_NAME)
    user_id = "screener"
    session = await runner.session_service.create_session(
        app_name=APP_NAME, user_id=user_id, session_id=str(uuid.uuid4())
    )

    prompt = candidate.as_untrusted_block(task_summary, attached_tool_names or [])
    message = types.Content(role="user", parts=[types.Part(text=prompt)])

    started = time.monotonic()
    payload: dict | str | None = None
    async for event in runner.run_async(
        user_id=user_id, session_id=session.id, new_message=message
    ):
        for part in (event.content.parts if event.content else None) or []:
            # In task mode ADK delivers a schema-constrained result as the
            # arguments of a synthetic `finish_task` call rather than as text.
            call = getattr(part, "function_call", None)
            if call is not None and call.name == FINISH_TASK_TOOL_NAME:
                payload = dict(call.args or {})
            elif part.text:
                payload = part.text
    elapsed = time.monotonic() - started

    if payload is None:
        raise ScreeningError(f"screener returned nothing for {candidate.server_id}")

    try:
        raw = json.loads(payload) if isinstance(payload, str) else payload
        judged = Verdict.model_validate(raw)
    except Exception as exc:  # noqa: BLE001
        # A screener that cannot produce the schema is itself a failure to
        # block on -- never fall through to "assume it's fine".
        raise ScreeningError(
            f"screener output did not validate for {candidate.server_id}: {exc}"
        ) from exc

    return _merge(judged, static, candidate), elapsed


_RANK = {"info": 0, "warn": 1, "block": 2}


def _merge(judged: Verdict, static: list[Finding], candidate: Candidate) -> Verdict:
    """Combine the computed findings with the judged ones.

    Static findings win on collision: if the diff says the description changed,
    that is a fact, and a model opinion that it did not is simply wrong.
    """
    by_code: dict[FindingCode, Finding] = {f.code: f for f in judged.findings}
    for finding in static:
        current = by_code.get(finding.code)
        if current is None or _RANK[finding.severity] >= _RANK[current.severity]:
            by_code[finding.code] = finding

    findings = sorted(by_code.values(), key=lambda f: f.code.value)
    worst = max((_RANK[f.severity] for f in findings), default=0)
    decision = judged.decision
    if worst == 2:
        decision = "block"
    elif worst == 1 and decision == "pass":
        decision = "warn"

    return Verdict(
        decision=decision,
        findings=findings,
        requested_scopes=judged.requested_scopes or list(candidate.requested_scopes),
        # Nothing is granted to something we are blocking, whatever the judge
        # proposed before the static checks were folded in.
        granted_scopes=[] if decision == "block" else judged.granted_scopes,
    )
