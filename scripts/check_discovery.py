"""Measure how repeatable discovery is against an unchanged registry.

Worth measuring rather than assuming, because the submission video has to be
an unedited live run: if the candidate set moves between runs, the demo can
find a different field on the day than it found in rehearsal.

The finding so far is that it does move, and that turning the temperature down
to zero does not stop it -- Gemini 3.x still varies its query plan run to run.
What is stable is the core: the servers that clearly serve the capability show
up every time, and the marginal ones flicker. So the honest position is not
"discovery is deterministic" but "the core is, and nothing downstream should
depend on a marginal candidate appearing."
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from toolsmith.registry.discovery import discover  # noqa: E402

DEFAULT_CAPABILITY = (
    "file and label issues on a specific GitHub repository, "
    "and invite a collaborator to it"
)


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--capability", default=DEFAULT_CAPABILITY)
    args = parser.parse_args()

    selections: list[set[str]] = []
    plans: list[tuple[str, ...]] = []

    for i in range(args.runs):
        discovery = await discover(args.capability)
        names = {t.candidate.name for t in discovery.probe}
        selections.append(names)
        plans.append(tuple(sorted(discovery.queries)))
        print(f"  run {i + 1}: {discovery.summary}  ({discovery.seconds:.2f}s)")
        print(f"         queries {list(discovery.queries)}")
        # Stay under the free tier's per-minute request budget.
        await asyncio.sleep(4)

    counts = Counter(name for run in selections for name in run)
    always = [n for n, c in counts.items() if c == args.runs]

    print(f"\n  distinct servers ever selected : {len(counts)}")
    for name, count in counts.most_common():
        print(f"    {count}/{args.runs}  {name}")
    print(f"\n  stable core                    : {len(always)}")
    print(f"  identical query plan every run : {len(set(plans)) == 1}")

    # A stable core of nothing means downstream has nothing to rely on.
    return 0 if always else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
