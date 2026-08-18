"""A local catalogue, alongside the public registry.

Organisations do not let agents install from the open internet, and the ones
that would benefit most from this product least want that. An internal
catalogue -- vetted servers, self-hosted endpoints, things behind a VPN that
no public registry can see -- is the normal enterprise shape, so it is a
source rather than a workaround.

It is also the honest answer to a practical problem: the servers the public
registry lists for a given capability are frequently behind OAuth, dead, or
serving certificates that cannot be verified. Being able to point at one you
run yourself is what makes the rest testable.

Entries are screened exactly like public ones. Being in the catalogue means
someone chose to list it, not that it is trusted -- an internal registry is a
supply chain too, and rug-pulls do not care who is hosting.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

CATALOG_ENV = "TOOLSMITH_CATALOG"


def catalog_path() -> Path | None:
    raw = os.getenv(CATALOG_ENV)
    if not raw:
        return None
    path = Path(raw).expanduser()
    return path if path.exists() else None


def load() -> list[dict[str, Any]]:
    """Read the catalogue as registry-shaped entries.

    The file uses the same structure the public registry returns, so entries
    from either source travel through the same parser, the same triage and the
    same screening. Nothing downstream knows or cares where a candidate came
    from, which is the point -- a local origin must not be a shortcut past any
    of it.
    """
    path = catalog_path()
    if path is None:
        return []
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    return payload.get("servers", [])


def search(query: str) -> list[dict[str, Any]]:
    """Substring match over name and description, as the public registry does."""
    needle = query.strip().lower()
    if not needle:
        return []
    hits = []
    for entry in load():
        server = entry.get("server", {})
        haystack = f"{server.get('name', '')} {server.get('description', '')}".lower()
        if needle in haystack:
            hits.append(entry)
    return hits
