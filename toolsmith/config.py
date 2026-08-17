"""Central configuration.

Model tiers are deliberate, not incidental:

* The orchestrator holds the user's goal and credentials, so it gets the
  stronger model.
* The screener runs once per candidate, in-loop, while a human waits. The
  product thesis is that screening has to be *seconds-scale and cheap* --
  that is the whole reason this is not just another offline MCP eval -- so it
  runs on the flash-lite tier.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Credentials live outside the repo, following the per-project convention in
# ~/keys/<Project>/. A local .env may override for one-off experiments, but the
# key itself is never expected to sit next to the source.
load_dotenv(Path.home() / "keys" / "ToolSmith" / "ToolSmith.env")
load_dotenv(override=False)

# Hackathon rules require Gemini 3.5 or newer.
ORCHESTRATOR_MODEL = os.getenv("TOOLSMITH_ORCHESTRATOR_MODEL", "gemini-3.5-flash")
SCREENER_MODEL = os.getenv("TOOLSMITH_SCREENER_MODEL", "gemini-3.5-flash-lite")
SCOUT_MODEL = os.getenv("TOOLSMITH_SCOUT_MODEL", "gemini-3.5-flash-lite")

SANDBOX_REGION = os.getenv("TOOLSMITH_SANDBOX_REGION", "us-central1")
SANDBOX_SERVICE = os.getenv("TOOLSMITH_SANDBOX_SERVICE", "toolsmith-sandbox")

DEMO_REPO = os.getenv("TOOLSMITH_DEMO_REPO", "CatDidIt-Studio/Toolsmith")

# Session-state key under which approved attachments are recorded. The
# ToolsmithToolset reads only this key when deciding what to expose.
ATTACHED_STATE_KEY = "toolsmith:attached"

# Free-text coming out of the untrusted zone is capped before it is ever
# rendered. Long attacker-authored prose is itself an attack surface.
MAX_EVIDENCE_CHARS = 400
