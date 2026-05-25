#!/usr/bin/env bash
set -euo pipefail

AI_CADDIE_DATA_MODE=local_or_fixture uv run uvicorn server_v2.main:app --host 127.0.0.1 --port 9000
