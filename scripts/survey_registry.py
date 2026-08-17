"""How much of the registry can actually be reached?

Every claim this project makes about screening assumes there is something to
screen. The registry publishes no tool definitions, so that assumption rests
entirely on being able to connect to a listed server and ask it. This measures
whether that holds in practice, across a sample of entries the registry itself
describes as active with a reachable endpoint.

Failures are grouped by cause rather than counted, because they mean different
things: a refused handshake is a server behind a key, an unverifiable
certificate is a server you could not trust even if it answered, and a timeout
is a listing for something that is no longer there.
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from toolsmith.registry.client import ServerCandidate, search  # noqa: E402
from toolsmith.registry.triage import dedupe_by_name  # noqa: E402
from toolsmith.sandbox.probe import probe  # noqa: E402

TERMS = ["github", "issue", "slack", "notion", "jira", "search", "database", "file"]

CAUSES = [
    ("tls-untrusted", re.compile(r"CERTIFICATE_VERIFY_FAILED|self[- ]signed", re.I)),
    ("auth-or-session-refused", re.compile(r"Session terminated|401|403", re.I)),
    ("not-found", re.compile(r"404", re.I)),
    ("dns-or-connect", re.compile(r"ConnectError|getaddrinfo|Name or service", re.I)),
    ("timeout", re.compile(r"Timeout|timed out", re.I)),
]


def classify(error: str) -> str:
    for label, pattern in CAUSES:
        if pattern.search(error):
            return label
    return "other"


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--timeout", type=float, default=12.0)
    args = parser.parse_args()

    hits: list[ServerCandidate] = []
    for term in TERMS:
        hits.extend(await search(term, limit=50))

    reachable = [
        c
        for c in dedupe_by_name(hits)
        if c.connectable is not None
        and c.status == "active"
        and not c.connectable.demands_secret
    ][: args.limit]

    print(f"  sampling {len(reachable)} active entries with an open endpoint\n")

    semaphore = asyncio.Semaphore(args.concurrency)

    async def one(candidate: ServerCandidate):
        async with semaphore:
            result = await probe(candidate.connectable.url, timeout=args.timeout)
            return candidate, result

    results = await asyncio.gather(*(one(c) for c in reachable))

    causes: Counter[str] = Counter()
    answered = []
    for candidate, result in results:
        if result.ok:
            answered.append((candidate, result))
            print(f"  ok    {candidate.name[:46]:46} {len(result.tools):3} tools  {result.seconds:5.1f}s")
        else:
            cause = classify(result.error or "")
            causes[cause] += 1
            print(f"  fail  {candidate.name[:46]:46} {cause}")

    total = len(results)
    print(f"\n  answered            : {len(answered)} / {total}")
    for cause, count in causes.most_common():
        print(f"  {cause:20}: {count}")

    if answered:
        print("\n  usable for a live demo:")
        for candidate, result in answered:
            print(
                f"    {candidate.name}  v{candidate.version}  "
                f"{len(result.tools)} tools  {candidate.connectable.url}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
