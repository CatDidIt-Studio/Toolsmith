"""Run a real screening pass and serve the resulting approval card.

Not a mock. The verdict on screen is produced by the same screener the bench
scores, so what the card renders is whatever screening actually decided --
including when that is unflattering.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import uvicorn  # noqa: E402

from bench.cases import ATTACHED, CASES, TASK_SUMMARY  # noqa: E402
from toolsmith.approval.model import STORE, ApprovalRequest, Provenance  # noqa: E402
from toolsmith.screening.runner import screen_candidate  # noqa: E402
from toolsmith.ui.app import app  # noqa: E402

CAPABILITY = "file and label issues on the Toolsmith repository"


async def seed(case_ids: list[str]) -> None:
    by_id = {c.candidate.server_id: c for c in CASES}
    for case_id in case_ids:
        case = by_id.get(case_id)
        if case is None:
            print(f"  ! no bench case named {case_id!r}")
            continue

        verdict, elapsed = await screen_candidate(
            case.candidate, task_summary=TASK_SUMMARY, attached_tool_names=ATTACHED
        )
        request = STORE.add(
            ApprovalRequest(
                capability=CAPABILITY,
                tool=case.candidate,
                verdict=verdict,
                endpoint=f"https://server.example/{case.candidate.server_id}/mcp",
                provenance=Provenance(
                    server_name=case.candidate.server_id,
                    version="1.0.3",
                    publisher=case.candidate.publisher,
                    signed=case.candidate.signed,
                    registry_status="active",
                    repository_url="https://github.com/example/mcp-server",
                    published_at="2026-07-02T09:11:00Z",
                    updated_at=(
                        "2026-08-14T18:40:00Z"
                        if case.candidate.previous_description
                        else "2026-07-02T09:11:00Z"
                    ),
                ),
            )
        )
        print(
            f"  {case_id:28} {verdict.decision:5} {elapsed:4.2f}s  "
            f"http://127.0.0.1:8000/approve/{request.id}"
        )
        await asyncio.sleep(4.2)  # free tier: 15 requests per minute


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cases",
        nargs="+",
        default=["gh-issues-overscope", "gh-issues-clean", "gh-issues-injected"],
        help="bench case ids to screen and queue for approval",
    )
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    asyncio.run(seed(args.cases))
    print(f"\n  serving on http://127.0.0.1:{args.port}\n")
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
