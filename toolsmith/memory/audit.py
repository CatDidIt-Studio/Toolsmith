"""Writing down what was approved, and what was actually done with it.

The useful column is not "what happened". It is the gap between the
permissions a task was granted and the ones it turned out to need. A grant
that is never exercised is the clearest possible argument for a narrower
grant next time, and it is the only honest answer to "what did it do with
that access" -- an answer that has to come from execution, not from the plan.

Recorded whether or not anyone is looking, and whether or not the run
succeeded. A refusal is the most interesting line in the log.
"""

from __future__ import annotations

from toolsmith.memory.store import AuditEntry, MemoryBank, _now
from toolsmith.planning.execute import ExecutionRecord
from toolsmith.planning.schema import TaskPlan


def record_plan(
    memory: MemoryBank, plan: TaskPlan, decision: str, why: str = ""
) -> None:
    """Record the decision, including the ones nobody made.

    An automatic approval is written down as such, with the rule that let it
    through. A gate that runs tasks silently is the blank cheque this product
    argues against -- the difference between one approval and none is only
    defensible if the ones that were skipped are still visible afterwards.
    """
    memory.record(
        AuditEntry(
            at=_now(),
            task=plan.task,
            kind=f"plan_{decision}",
            detail=why or plan.summary,
            granted_scopes=[m.scope for m in plan.footprint]
            + [m.scope for m in plan.new_footprint],
            findings=sorted(
                {
                    f.code.value
                    for fill in plan.fills
                    for f in fill.verdict.findings
                    if f.severity != "info"
                }
            ),
        )
    )


def record_execution(
    memory: MemoryBank, plan: TaskPlan, record: ExecutionRecord
) -> None:
    granted = [m.scope for m in plan.footprint] + [m.scope for m in plan.new_footprint]
    memory.record(
        AuditEntry(
            at=_now(),
            task=plan.task,
            kind="executed" if record.stayed_in_plan else "executed_with_refusals",
            detail=f"{len(record.calls)} of {len(plan.executable)} approved steps ran",
            granted_scopes=granted,
            used_tools=list(record.calls),
            refused_tools=list(record.refused),
        )
    )


def unused_grants(plan: TaskPlan, record: ExecutionRecord) -> list[str]:
    """Permissions approved for this task that no call actually needed.

    Reported rather than silently dropped. Every entry here is a grant that
    could have been smaller, and the case for asking for less next time is
    made by the record instead of by an opinion.
    """
    used_steps = {
        tool for tool, in [(t,) for _, t in plan.executable] if tool in record.calls
    }
    exercised = {
        scope
        for step, tool in plan.executable
        if tool in used_steps
        for scope in _scopes_for(plan, tool)
    }
    granted = {m.scope for m in plan.footprint} | {m.scope for m in plan.new_footprint}
    return sorted(granted - exercised)


def _scopes_for(plan: TaskPlan, tool: str) -> tuple[str, ...]:
    entry = plan.inventory.get(tool)
    if entry is not None:
        return entry.scopes
    for fill in plan.fills:
        if fill.tool_name == tool:
            return fill.granted_scopes
    return ()
