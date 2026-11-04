# One image for all three REST services; docker-compose.yml picks the command.
# Build context is the repository root, so the shared common/ package is included.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# iproute2 provides `tc`, used in Phase 3 to inject network delay and packet loss.
RUN apt-get update \
    && apt-get install -y --no-install-recommends iproute2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY rest-version/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY common/ common/
COPY rest-version/services/ services/
