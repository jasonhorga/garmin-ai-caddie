FROM node:24-bookworm-slim AS node-deps

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    AI_CADDIE_DATA_MODE=local_or_fixture \
    PORT=9000

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl nodejs \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY package.json package-lock.json ./
COPY --from=node-deps /app/node_modules ./node_modules

COPY ai_caddie/ ./ai_caddie/
COPY server_v2/ ./server_v2/
COPY ops/ ./ops/

EXPOSE 9000

CMD ["sh", "ops/start_api.sh"]
