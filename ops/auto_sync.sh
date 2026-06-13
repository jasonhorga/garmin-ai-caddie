#!/usr/bin/env bash
# Garmin 自动同步(cron 入口):自愈登录(xvfb 有头 Chromium 过 Turnstile)→ 增量拉取
# 记分卡/击球/几何/球场 par → 同步成功后预热 stats 三窗口缓存。
#
# 设计给 2c/2GB 小机器:flock 防重入;可用内存不足直接跳过本轮(下个时段再试);
# 日志固定截尾防膨胀。crontab 示例(UTC 机器,北京时间 13:37 / 21:37 各一次):
#   37 5  * * * /home/ubuntu/claude-web-data/repo/garmin-ai-caddie/ops/auto_sync.sh
#   37 13 * * * /home/ubuntu/claude-web-data/repo/garmin-ai-caddie/ops/auto_sync.sh
#
# 依赖:dependency-group `auth`(playwright)— `uv run --group auth` 自动装;
# 凭据在 .garmin_tokens/garmin_login.json(勿外传);xvfb-run 需已安装。
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG="${AI_CADDIE_SYNC_LOG:-$HOME/garmin-auto-sync.log}"
LOCK="${AI_CADDIE_SYNC_LOCK:-/tmp/garmin-auto-sync.lock}"
UV_BIN="${UV_BIN:-$(command -v uv || echo "$HOME/.local/bin/uv")}"
MIN_MB="${AI_CADDIE_SYNC_MIN_MB:-500}"
GEOMETRY_LIMIT="${AI_CADDIE_SYNC_GEOMETRY_LIMIT:-40}"
API="${AI_CADDIE_API_BASE:-http://127.0.0.1:9000}"

exec 9>"$LOCK"
if ! flock -n 9; then
  echo "$(date -Is) skip: another sync holds the lock" >>"$LOG"
  exit 0
fi

avail="$(free -m | awk 'NR==2{print $7}')"
if [ "$avail" -lt "$MIN_MB" ]; then
  echo "$(date -Is) skip: only ${avail}MB available (<${MIN_MB}MB, browser-unsafe)" >>"$LOG"
  exit 0
fi

cd "$REPO"
echo "$(date -Is) sync start (${avail}MB free)" >>"$LOG"
if AI_CADDIE_AUTH_REFRESH=playwright "$UV_BIN" run --group auth python -m ai_caddie.pipeline \
    --shots --geometry-limit "$GEOMETRY_LIMIT" >>"$LOG" 2>&1; then
  echo "$(date -Is) sync ok — warming stats windows" >>"$LOG"
  for w in all last10 12m; do
    curl -sf -o /dev/null -m 180 "$API/api/v2/history/stats?window=$w" || true
  done
  echo "$(date -Is) done" >>"$LOG"
else
  echo "$(date -Is) SYNC FAILED — see lines above" >>"$LOG"
  tail -n 2000 "$LOG" >"$LOG.tmp" && mv "$LOG.tmp" "$LOG"
  exit 1
fi
tail -n 2000 "$LOG" >"$LOG.tmp" && mv "$LOG.tmp" "$LOG"
