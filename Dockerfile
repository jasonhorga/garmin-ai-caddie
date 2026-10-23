# Application-only API image. Dockerfile.deps is built first as
# garmin-ai-caddie-deps:<content-hash>; this stage then copies source on top so
# code changes never invalidate the dependency image.
# Dockerfile.deps pins ghcr.io/astral-sh/uv:python3.12-bookworm-slim and
# node:24-bookworm-slim, runs `uv sync --frozen --no-dev` and
# `npm ci --omit=dev`, and installs postgresql-client before this stage.
ARG DEPS_IMAGE
FROM ${DEPS_IMAGE} AS runtime

WORKDIR /app

COPY ai_caddie/ ./ai_caddie/
COPY contracts/canonical/ ./contracts/canonical/
COPY mobile/contracts/ ./mobile/contracts/
COPY server_v2/ ./server_v2/
COPY ops/ ./ops/
COPY alembic.ini ./
COPY migrations/ ./migrations/

EXPOSE 9000

CMD ["sh", "ops/start_api.sh"]
