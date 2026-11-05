# One image for the three MQTT services; docker-compose.yml picks the command.
# Same base image and Python version as the REST image. Build context = repo root.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends iproute2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY mqtt-version/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY common/ common/
COPY mqtt-version/mqtt_services/ mqtt_services/
