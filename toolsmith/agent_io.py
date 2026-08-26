"""Running an isolated agent and getting a typed object back.

Both Scout and the screener are the same shape: one shot, no tools, a forced
output schema, nothing carried between calls. This is that shape, in one
place, so the isolation properties do not drift apart between them.

ADK delivers a schema-constrained result in task mode as the arguments of a
synthetic `finish_task` call rather than as message text, which is the part
worth remembering -- reading `part.text` finds nothing and looks like the
model returned an empty response.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import TypeVar

from google.adk.agents import LlmAgent
from google.adk.runners import FINISH_TASK_TOOL_NAME, InMemoryRunner
from google.genai import types
from pydantic import BaseModel

from toolsmith.config import FALLBACK_MODELS

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class AgentOutputError(RuntimeError):
    pass


async def run_structured(
    agent: LlmAgent, prompt: str, schema: type[T], *, app_name: str
) -> tuple[T, float]:
    """Run `agent` on `prompt` and validate its output as `schema`.

    Retries inside the agent handle a model that is slow or briefly refusing.
    This handles the other case: a model that is out of capacity, where trying
    the same one again just fails again more slowly. Falling back to a
    different model is safe here because every agent using this answers a
    closed question with a fixed schema -- there is no conversation to lose and
    no state to reconcile.

    The fallback is recorded, not hidden. Which model produced a verdict is
    worth knowing afterwards.
    """
    models = [agent.model, *FALLBACK_MODELS]
    last: Exception | None = None

    for model in models:
        agent.model = model
        try:
            return await _run_once(agent, prompt, schema, app_name=app_name)
        except AgentOutputError:
            # A schema violation is the model doing the wrong thing, not the
            # service being unavailable. Another model will not fix it, and
            # retrying hides a real defect behind a slower failure.
            raise
        except Exception as exc:  # noqa: BLE001
            last = exc
            if model != models[-1]:
                logger.warning(
                    "%s unavailable on %s (%s); falling back",
                    agent.name, model, type(exc).__name__,
                )

    raise AgentOutputError(f"{agent.name} failed on every model: {last}")


async def _run_once(
    agent: LlmAgent, prompt: str, schema: type[T], *, app_name: str
) -> tuple[T, float]:
    runner = InMemoryRunner(agent=agent, app_name=app_name)
    user_id = agent.name
    session = await runner.session_service.create_session(
        app_name=app_name, user_id=user_id, session_id=str(uuid.uuid4())
    )
    message = types.Content(role="user", parts=[types.Part(text=prompt)])

    started = time.monotonic()
    payload: dict | str | None = None
    async for event in runner.run_async(
        user_id=user_id, session_id=session.id, new_message=message
    ):
        for part in (event.content.parts if event.content else None) or []:
            call = getattr(part, "function_call", None)
            if call is not None and call.name == FINISH_TASK_TOOL_NAME:
                payload = dict(call.args or {})
            elif part.text:
                payload = part.text
    elapsed = time.monotonic() - started

    if payload is None:
        raise AgentOutputError(f"{agent.name} returned nothing")

    try:
        raw = json.loads(payload) if isinstance(payload, str) else payload
        return schema.model_validate(raw), elapsed
    except Exception as exc:  # noqa: BLE001
        raise AgentOutputError(
            f"{agent.name} output did not validate as {schema.__name__}: {exc}"
        ) from exc
