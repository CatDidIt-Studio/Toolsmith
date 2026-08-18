"""Drive the orchestrator against a request it cannot serve.

Starts the approval server alongside the agent, because the agent will block
waiting for a person: acquisition is not something it can finish on its own,
by design.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import uvicorn  # noqa: E402
from google.adk.runners import InMemoryRunner  # noqa: E402
from google.genai import types  # noqa: E402

from toolsmith.agents.orchestrator import build_orchestrator  # noqa: E402
from toolsmith.ui.app import app  # noqa: E402

APP_NAME = "toolsmith"
DEFAULT_REQUEST = (
    "Open an issue on the CatDidIt-Studio/Toolsmith repository titled "
    "'Onboarding checklist' listing the setup steps for a new contributor."
)


async def drive(request: str, port: int) -> None:
    runner = InMemoryRunner(agent=build_orchestrator(), app_name=APP_NAME)
    session = await runner.session_service.create_session(
        app_name=APP_NAME, user_id="tyler", session_id=str(uuid.uuid4())
    )
    message = types.Content(role="user", parts=[types.Part(text=request)])

    print(f"\n  user: {request}\n")
    print(f"  approval cards at http://127.0.0.1:{port}/\n")

    async for event in runner.run_async(
        user_id="tyler", session_id=session.id, new_message=message
    ):
        for part in (event.content.parts if event.content else None) or []:
            if part.text:
                print(f"  {event.author}: {part.text.strip()}")
            call = getattr(part, "function_call", None)
            if call is not None:
                print(f"  -> calls {call.name}({dict(call.args or {})})")
            response = getattr(part, "function_response", None)
            if response is not None:
                print(f"  <- {response.name} returned {response.response}")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", default=DEFAULT_REQUEST)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    config = uvicorn.Config(app, host="127.0.0.1", port=args.port, log_level="warning")
    server = uvicorn.Server(config)
    serving = asyncio.create_task(server.serve())
    try:
        await drive(args.request, args.port)
    finally:
        server.should_exit = True
        await serving


if __name__ == "__main__":
    asyncio.run(main())
