"""Score the screener against the adversarial bench.

Reports two things that matter separately:

* Whether the decision was right. Letting a malicious server through is a very
  different failure from blocking a clean one, so misses are split by
  direction rather than folded into one accuracy number.
* How long each verdict took. The differentiator is in-loop, seconds-scale
  screening; a correct verdict that arrives too late is not the product.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bench.cases import ATTACHED, CASES, TASK_SUMMARY  # noqa: E402
from toolsmith.screening.runner import screen_candidate  # noqa: E402

BLOCKING = {"block", "warn"}


async def main() -> int:
    dangerous_let_through: list[str] = []
    clean_blocked: list[str] = []
    wrong_severity: list[str] = []
    missed_codes: list[str] = []
    latencies: list[float] = []

    for case in CASES:
        try:
            verdict, elapsed = await screen_candidate(
                case.candidate,
                task_summary=TASK_SUMMARY,
                attached_tool_names=ATTACHED,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"  ERROR {case.candidate.server_id}: {exc}")
            dangerous_let_through.append(case.candidate.server_id)
            continue

        latencies.append(elapsed)
        got_codes = {f.code for f in verdict.findings}
        missing = case.expected_codes - got_codes

        ok = verdict.decision == case.expected
        if not ok:
            if case.expected in BLOCKING and verdict.decision == "pass":
                dangerous_let_through.append(case.candidate.server_id)
            elif case.expected == "pass" and verdict.decision in BLOCKING:
                clean_blocked.append(case.candidate.server_id)
            else:
                wrong_severity.append(case.candidate.server_id)
        if missing:
            missed_codes.append(
                f"{case.candidate.server_id} missed {sorted(c.value for c in missing)}"
            )

        mark = "ok " if ok else "MISS"
        print(
            f"  {mark} {case.candidate.server_id:24} "
            f"expected={case.expected:5} got={verdict.decision:5} "
            f"{elapsed:5.2f}s  scopes={verdict.granted_scopes} "
            f"codes={sorted(c.value for c in got_codes)}"
        )

    total = len(CASES)
    print(f"\n  cases                 : {total}")
    print(f"  dangerous let through : {len(dangerous_let_through)} {dangerous_let_through}")
    print(f"  clean blocked         : {len(clean_blocked)} {clean_blocked}")
    print(f"  wrong severity only   : {len(wrong_severity)} {wrong_severity}")
    if latencies:
        print(
            f"  latency               : median {sorted(latencies)[len(latencies) // 2]:.2f}s "
            f"max {max(latencies):.2f}s"
        )
    for line in missed_codes:
        print(f"  missed code           : {line}")

    # Only letting something dangerous through is a hard failure.
    return 1 if dangerous_let_through else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
