"""Drives one screening pass.

Deliberately a single, short, isolated model call. The whole product claim is
that this is cheap enough to run in-loop while a human waits -- if screening
grows into a multi-turn agent that plans and retries, it stops being a
different problem from the offline MCP eval products and starts being a worse
version of them.
"""

from __future__ import annotations

from toolsmith.agent_io import AgentOutputError, run_structured
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

    prompt = candidate.as_untrusted_block(task_summary, attached_tool_names or [])
    try:
        judged, elapsed = await run_structured(
            build_screener(as_root=True), prompt, Verdict, app_name=APP_NAME
        )
    except AgentOutputError as exc:
        # A screener that cannot produce the schema is itself a failure to
        # block on -- never fall through to "assume it's fine".
        raise ScreeningError(f"screening failed for {candidate.server_id}: {exc}") from exc

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
