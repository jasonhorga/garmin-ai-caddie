# NAS VM Tunnel Deployment

Use this path when the backend VM is reachable only from the home LAN.
Do not expose SSH through a home proxy or router rule. The VM should make an outbound
connection to a tunnel provider, and the iPhone/TestFlight build should use the
resulting public HTTPS API origin.

## Target Shape

- AI Caddie API listens only on the VM: `127.0.0.1:9000`.
- Cloudflare Tunnel or Tailscale Funnel publishes that local port as
  `https://<api-host>`.
- GitHub repo variable `AI_CADDIE_API_BASE_URL` is set to that HTTPS origin.
- The manual `Phase 6 Readiness` workflow probes the public URL with
  `AI_CADDIE_ADMIN_TOKEN`.

## VM API Service

Run these commands on the VM, not on the NAS host. Keep the VM isolated from
important NAS shares until the deployment is proven. The bootstrap script keeps
the Docker API port bound to `127.0.0.1`, creates `.env`, generates
`AI_CADDIE_ADMIN_TOKEN` when needed, starts the API, and runs the local private
smoke.
Internally, it runs `docker compose up -d --build api` and
`ops/smoke_private_trial.sh http://127.0.0.1:9000`.

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git openssl docker.io
# Depending on the Ubuntu/Debian source, the Compose v2 package can be either:
sudo apt-get install -y docker-compose-plugin || sudo apt-get install -y docker-compose-v2
sudo systemctl enable --now docker

curl -fsSL https://raw.githubusercontent.com/jasonhorga/garmin-ai-caddie/integration/v2/ops/bootstrap_nas_vm_api.sh \
  -o /tmp/bootstrap_nas_vm_api.sh
bash /tmp/bootstrap_nas_vm_api.sh --install-system
```

The compose API stores private runtime state in the `ai-caddie-private` Docker
volume mounted at `/var/lib/ai-caddie`. That volume contains downloaded Garmin
data, session material, generated output, logs, and backups. Do not put `.env`
or that volume into git.

Save the generated `AI_CADDIE_ADMIN_TOKEN` in a password manager and configure
the same value as the GitHub repo secret `AI_CADDIE_ADMIN_TOKEN`. Do not send it
in chat.

## Cloudflare Tunnel

Use a named Cloudflare Tunnel for a stable TestFlight backend URL. A quick
`trycloudflare.com` URL is fine for a short smoke test, but it can change after
restart and should not be baked into a TestFlight build.

On the VM:

```bash
# Install cloudflared first with the package for this VM's OS.
sudo cloudflared tunnel login
sudo cloudflared tunnel create ai-caddie
sudo cloudflared tunnel route dns ai-caddie ai-caddie.example.com
```

Create `/etc/cloudflared/config.yml` with the tunnel ID printed by
`cloudflared tunnel create`:

```yaml
tunnel: <tunnel-uuid>
credentials-file: /root/.cloudflared/<tunnel-uuid>.json

ingress:
  - hostname: ai-caddie.example.com
    service: http://127.0.0.1:9000
  - service: http_status:404
```

Then install and start the service:

```bash
sudo cloudflared service install
sudo systemctl enable --now cloudflared
curl -fsS https://ai-caddie.example.com/api/v2/health
```

The URL to use in GitHub is the origin only:

```text
https://ai-caddie.example.com
```

Do not include `/api/v2/...`, query strings, credentials, or tokens in
`AI_CADDIE_API_BASE_URL`.

## Tailscale Funnel

Use this only if the VM is already in the right tailnet and Funnel is enabled
for the tailnet. The backend still listens on `127.0.0.1:9000`; Tailscale
publishes it as a public HTTPS Funnel URL.

On the VM:

```bash
sudo tailscale up
sudo tailscale serve --bg --https=443 http://127.0.0.1:9000
sudo tailscale funnel --bg 443
curl -fsS https://<machine>.<tailnet>.ts.net/api/v2/health
```

If the local `tailscale` version uses slightly different Funnel flags, run
`tailscale serve --help` and `tailscale funnel --help` on the VM and keep the
same target service: `http://127.0.0.1:9000`.

## GitHub Wiring

After the public HTTPS origin works:

```bash
gh variable set AI_CADDIE_API_BASE_URL --body https://<api-host>
```

Run the manual `Phase 6 Readiness` workflow with:

- `api_base_url`: leave blank to use `AI_CADDIE_API_BASE_URL`
- `probe_backend`: `true`
- `fail_when_incomplete`: `false` until Beta Review and install gates are done

For a connected TestFlight upload, run `iOS TestFlight (CD)` with
`api_base_url` blank only after `AI_CADDIE_API_BASE_URL` is set to the same
origin. If you need to avoid another upload, configure the backend URL in the
iPhone app runtime Backend screen and record the source as
`testflight_backend_screen` in the Phase 6 readiness run.

## Access Boundary

This route does not require Codex or GitHub Actions to SSH into the VM. If you
later add a GitHub self-hosted runner on the VM, do not allow public pull
request workflows to target that runner. Use manual workflows and runner labels
that are not referenced from normal CI.
