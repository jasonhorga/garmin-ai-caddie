# Private Trial Deployment

The recommended trial path is staged and reversible.

## Staging First

Use a Render-style API service and a Vercel-style web frontend for early testing. Keep Garmin session material and AI provider keys in the platform secret manager. Do not upload private raw data unless the deployment is locked down and intentionally configured for it.

Machine-readable starting points are committed:

- API: `render.yaml`
- Web: `web_v2/vercel.json`

Required API environment for private staging:

- `AI_CADDIE_SECURITY_PROFILE=private`
- `AI_CADDIE_ADMIN_TOKEN=<random private token>`
- `AI_CADDIE_DATA_MODE=local_or_fixture`

## NAS Or Private Server

A NAS or private server is suitable once local use is stable:

- Run the FastAPI service on `127.0.0.1:9000` behind a reverse proxy or VPN.
- Keep `AI_CADDIE_SECURITY_PROFILE=private` enabled so protected routes fail closed if `AI_CADDIE_ADMIN_TOKEN` is accidentally removed.
- Keep `data/`, `.garmin_tokens/`, and backups on encrypted storage when possible.
- Use `ops/backup_data.sh` before changing sync or import workflows.
- Expose only HTTPS if using a public IP or port forwarding.

## SSH Tunnel Development

For remote development:

```bash
ssh -L 9000:127.0.0.1:9000 -L 5173:127.0.0.1:5173 user@server
```

Then open:

- API: `http://127.0.0.1:9000`
- Web: `http://127.0.0.1:5173`

## Offline-First Mobile Caveat

The iOS and Watch app path should cache a live round package before play. During a round, GPS and score/club input must continue without network. The backend sync can run after the phone regains network access.
