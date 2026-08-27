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
from google.adk.workflow._retry_config import RetryConfig
from google.genai import types

# Credentials live outside the repo, following the per-project convention in
# ~/keys/<Project>/. A local .env may override for one-off experiments, but the
# key itself is never expected to sit next to the source.
load_dotenv(Path.home() / "keys" / "ToolSmith" / "ToolSmith.env")
load_dotenv(override=False)

# Deployment addresses, so nothing has to be exported by hand before a run.
# Loaded last and without override, so a real environment variable and a local
# .env both still win.
load_dotenv(Path(__file__).parent / "deployed.env", override=False)

# Hackathon rules require Gemini 3.5 or newer.
ORCHESTRATOR_MODEL = os.getenv("TOOLSMITH_ORCHESTRATOR_MODEL", "gemini-3.5-flash")
SCREENER_MODEL = os.getenv("TOOLSMITH_SCREENER_MODEL", "gemini-3.5-flash-lite")
SCOUT_MODEL = os.getenv("TOOLSMITH_SCOUT_MODEL", "gemini-3.5-flash-lite")

SANDBOX_REGION = os.getenv("TOOLSMITH_SANDBOX_REGION", "us-central1")
SANDBOX_SERVICE = os.getenv("TOOLSMITH_SANDBOX_SERVICE", "toolsmith-sandbox")

DEMO_REPO = os.getenv("TOOLSMITH_DEMO_REPO", "CatDidIt-Studio/Toolsmith")

# Every isolated agent in this system answers a closed question -- which
# search terms, which candidates are relevant, is this entry safe -- and none
# of them benefit from sampling variety. Left at the default temperature,
# discovery returned a different candidate set on repeated runs against an
# unchanged registry, which is both a bad security property and a bad thing to
# stake a live demo on.
DETERMINISTIC = types.GenerateContentConfig(temperature=0.0)

# Transient upstream failures are the biggest threat to an unedited live run:
# a 503 mid-take cannot be edited out, and the submission asks for one
# continuous execution. Every isolated agent here answers a closed question and
# is safe to retry, so retrying is strictly better than failing.
RETRY = RetryConfig(
    max_attempts=4,
    initial_delay=1.0,
    max_delay=12.0,
    backoff_factor=2.0,
    jitter=0.3,
)

# Tried in order when a model is unavailable rather than merely slow. These are
# separate capacity pools, so a spike on one is often not a spike on the other.
FALLBACK_MODELS = [
    m.strip()
    for m in os.getenv("TOOLSMITH_FALLBACK_MODELS", "gemini-3.6-flash").split(",")
    if m.strip()
]

# Session-state key under which approved attachments are recorded. The
# ToolsmithToolset reads only this key when deciding what to expose.
ATTACHED_STATE_KEY = "toolsmith:attached"

# Free-text coming out of the untrusted zone is capped before it is ever
# rendered. Long attacker-authored prose is itself an attack surface.
MAX_EVIDENCE_CHARS = 400
