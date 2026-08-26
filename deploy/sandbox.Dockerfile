# The probe service: connects to unvetted MCP servers so the agent does not.
#
# Kept minimal on purpose. This container is the thing a hostile server gets
# to talk to, so every dependency and every credential it does not have is
# one less thing available to whoever finds a way in. It holds no keys, has no
# database, and does one thing: open a connection, list tools, return JSON.
FROM python:3.12-slim

WORKDIR /app

# Only what the probe path needs -- not the agent, the planner or the UI.
RUN pip install --no-cache-dir \
    "mcp>=1.24,<2" \
    "fastapi" \
    "uvicorn[standard]" \
    "pydantic>=2" \
    "httpx" \
    "python-dotenv"

COPY toolsmith/__init__.py toolsmith/__init__.py
COPY toolsmith/config.py toolsmith/config.py
COPY toolsmith/screening/__init__.py toolsmith/screening/__init__.py
COPY toolsmith/screening/candidate.py toolsmith/screening/candidate.py
COPY toolsmith/sandbox/ toolsmith/sandbox/
COPY sandbox_worker/ sandbox_worker/

ENV PYTHONUNBUFFERED=1
EXPOSE 8080
CMD ["sh", "-c", "uvicorn sandbox_worker.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
