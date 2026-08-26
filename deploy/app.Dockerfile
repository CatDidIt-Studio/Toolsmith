# The agent and its approval surface.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY toolsmith/ toolsmith/
COPY fixtures/ fixtures/
COPY bench/ bench/
COPY scripts/ scripts/

ENV PYTHONUNBUFFERED=1
EXPOSE 8080
CMD ["sh", "-c", "uvicorn toolsmith.ui.app:app --host 0.0.0.0 --port ${PORT:-8080}"]
