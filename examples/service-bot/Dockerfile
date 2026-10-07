# syntax=docker/dockerfile:1
# Optional container for the service bot; the project runs the same without Docker.
# Build context is the repository root: docker compose -f examples/service-bot/compose.yaml up --build
# Another base or registry mirror: --build-arg PYTHON_IMAGE=mirror.gcr.io/library/python:3.13-slim
ARG PYTHON_IMAGE=python:3.13-slim
FROM ${PYTHON_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

COPY packages/python /src/library
COPY examples/service-bot /src/service-bot
# Behind a TLS-inspecting proxy pass its CA: docker build --secret id=ca,src=/path/ca.pem ...
RUN --mount=type=secret,id=ca,required=false \
    if [ -f /run/secrets/ca ]; then export PIP_CERT=/run/secrets/ca; fi \
 && pip install "/src/library[aiogram]" /src/service-bot \
 && useradd --create-home --uid 10001 bot \
 && mkdir /data && chown bot /data

USER bot
# SQLite database and its OS lock live on this volume; one container per database.
VOLUME /data
CMD ["telegram-service-example", "--database", "/data/service.sqlite"]
