#!/usr/bin/env bash
# Garmin 自动同步(cron 入口):自愈登录(xvfb 有头 Chromium 过 Turnstile)→ 增量拉取
# 记分卡/击球/几何/球场 par → 同步成功后预热 stats 三窗口缓存。
#
# 设计给 2c/2GB 小机器:flock 防重入;可用内存不足直接跳过本轮(下个时段再试);
# 日志固定截尾防膨胀。crontab 示例(UTC 机器,每小时一次 → 北京时间每小时的 :37):
#   37 * * * * /home/ubuntu/claude-web-data/repo/garmin-ai-caddie/ops/auto_sync.sh
# 「打开即用」:提频到每小时,让新球局个把小时内自动进来、复盘即备好。多数是轻量增量拉;
# 只有 cookie 过期才触发较重的 xvfb 自愈。若实测过重,退回每 2–3 小时(37 */2 * * *)或
# 只白天时段。真改 cron 是部署动作(homeserver 上手动),本文件只改注释示例。见设计 §8-②。
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
  # 「打开即用」:数据落地后准备最近一盘(预热其球洞图 topo → 复盘打开即秒开)。best-effort。
  curl -sf -o /dev/null -m 300 -X POST "$API/api/v2/history/prepare-recent" || true
  echo "$(date -Is) done" >>"$LOG"
else
  echo "$(date -Is) SYNC FAILED — see lines above" >>"$LOG"
  tail -n 2000 "$LOG" >"$LOG.tmp" && mv "$LOG.tmp" "$LOG"
  exit 1
fi
tail -n 2000 "$LOG" >"$LOG.tmp" && mv "$LOG.tmp" "$LOG"
