# Remote Development Migration Notes

This repo is safe to move through GitHub, but the working AI Caddie environment
also depends on ignored private data and caches. Do not commit those files.

## 1. Code

Clone the repo on the remote server:

```bash
git clone git@github.com:jasonhorga/garmin-ai-caddie.git
cd garmin-ai-caddie
git checkout testing-sandbox
```

Install runtime dependencies:

```bash
uv sync
npm ci
```

Required tools:

- Python via `uv` for the Web app, Garmin import, analysis, tests.
- Node.js/npm for Draco/prodgeometry decoding.
- JDK is optional and only needed for old IMG/mkgmap research tools.

## 2. Private Local Data

These paths are intentionally ignored by git and must be copied separately if
the remote server should behave like the local machine:

```text
.garmin_tokens/
clubs.json
data/
output/hole_overlays/
output/prodgeometry/
output/prodgeometry_overlay/
output/satellite_cache/
logs/
downloads/
```

Suggested copy command from the local machine:

```bash
rsync -av \
  .garmin_tokens clubs.json data output/hole_overlays output/prodgeometry \
  output/prodgeometry_overlay output/satellite_cache logs downloads \
  USER@REMOTE:/path/to/garmin-ai-caddie/
```

After copying auth files:

```bash
chmod 700 .garmin_tokens
chmod 600 .garmin_tokens/*
```

## 3. Garmin Auth on a Remote Server

The current Garmin web auth flow is local-browser based. On a headless remote
server, it usually cannot read the browser session automatically.

Practical options:

1. Keep Garmin sync/auth on the local Mac and rsync `data/` plus `.garmin_tokens/`
   to the remote server when needed.
2. Use a remote desktop/browser on the server, log in to `connect.garmin.cn`,
   then run:

```bash
uv run python garmin_auth.py
uv run python fetch.py --refresh-auth
```

3. Manually copy cookie/CSRF into `.garmin_tokens/` on the server.

Do not expose Garmin cookies or `.garmin_tokens/` through logs, GitHub, or a
public Web endpoint.

## 4. Run the Web App

For private development, bind to localhost on the remote server:

```bash
tmux new-session -d -s ai-caddie 'cd /path/to/garmin-ai-caddie && uv run python ai_caddie_web.py --host 127.0.0.1 --port 8765'
```

Use SSH port forwarding from the local machine:

```bash
ssh -L 8765:127.0.0.1:8765 USER@REMOTE
open http://127.0.0.1:8765
```

Avoid `--host 0.0.0.0` unless the server is behind authentication and firewall
rules. The current app is a private local tool, not a public SaaS surface.

## 5. Verification After Migration

Run:

```bash
uv run python -m py_compile ai_caddie_web.py ai_caddie/data.py ai_caddie/analysis.py fetch.py
uv run python -m unittest discover -s tests -v
curl http://127.0.0.1:8765/api/status
curl 'http://127.0.0.1:8765/api/overlay-geojson?source=garmin&id=<scorecard_id>&hole=1'
```

Expected signs:

- `/api/status` lists Garmin rounds.
- `/api/overlay-geojson` returns `raster.available: true` for rounds with shot
  map data.
- Satellite endpoint includes `size=2600`.
- The browser can open the Web app through the SSH tunnel.

## 6. Recommended Workflow

Use GitHub for code and `rsync` for private data:

```bash
# code
git pull

# private data from local Mac when needed
rsync -av USER@LOCAL:/Users/jason/workspace/garmin/data/ data/
```

Before pushing code from the remote server:

```bash
git status --short
uv run python -m unittest discover -s tests -v
```

Check that ignored private paths remain ignored:

```bash
git status --ignored --short .garmin_tokens data output logs downloads clubs.json
```
