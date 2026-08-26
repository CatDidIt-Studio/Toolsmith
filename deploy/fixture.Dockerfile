# The demo's MCP servers, deployed rather than run on a laptop.
#
# The sandbox runs on Cloud Run, so anything it is meant to probe has to be
# reachable from there -- a server on localhost is only reachable by a
# sandbox that is not isolated, which is the arrangement this exists to
# avoid. Deploying them keeps the demo honest: every connection in it is a
# real network hop between real services.
#
# One image, several personas, chosen by environment. FIXTURE_PERSONA=honest
# serves the tool a plan can be completed with; the others misbehave in
# specific, documented ways and do nothing when called.
FROM python:3.12-slim

WORKDIR /app
RUN pip install --no-cache-dir "mcp>=1.24,<2" "uvicorn[standard]"

COPY fixtures/ fixtures/

ENV PYTHONUNBUFFERED=1 FIXTURE_PERSONA=honest
EXPOSE 8080
CMD ["sh", "-c", "\
  if [ \"$FIXTURE_PERSONA\" = github ]; then \
    python fixtures/github_like.py --port ${PORT:-8080}; \
  else \
    python fixtures/adversarial.py --persona $FIXTURE_PERSONA --port ${PORT:-8080}; \
  fi"]
