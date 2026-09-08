# Public API Ingress Operation - 2026-09-07

This operation publishes the homeserver candidate API for the `PHONE-REGRESSION`
Native CI and internal TestFlight gate. It does not replace the homeserver API,
its database, its Docker volume, or the existing Tailscale Funnel routes.

## Resources

| Resource | Owner | Purpose | Created | Expiry / cleanup |
| --- | --- | --- | --- | --- |
| Cloudflare quick tunnel `suggests-kilometers-normal-insertion.trycloudflare.com` | Codex / Garmin AI Caddie | Temporary public HTTPS ingress to the candidate API and Build 52 | 2026-09-07 14:10 UTC | Keep through physical device validation; stop the exact tmux session during cleanup. No uptime guarantee. |
| Homeserver tmux session `codex-aicaddie-quicktunnel-http2-20260907` | Codex / Garmin AI Caddie | Runs `cloudflared --protocol http2` against `http://127.0.0.1:39055` | 2026-09-07 14:10 UTC | Creator owns shutdown; do not kill other tmux sessions |
| Homeserver -> Tokyo reverse SSH forward on Tokyo loopback `127.0.0.1:39056` | Codex / Garmin AI Caddie | Carries the candidate API to the Tokyo Caddy experiment | pre-existing for this operation | Stop only the named forward during cleanup |
| Tokyo Caddy container `aicaddie-ingress-20260907` | Codex / Garmin AI Caddie | Candidate HTTPS/HTTP ingress experiment | pre-existing for this operation | Remove only during explicit cleanup; does not receive quick-tunnel traffic |

## Protected resources

The homeserver API container, PostgreSQL container and named data volumes,
existing Tailscale Funnel/Serve configuration, Garmin session material, and
other projects' processes are outside this operation's cleanup scope.

## Gate

The quick-tunnel origin is written into the Build 52 TestFlight binary only after an
external probe confirms HTTPS, the health schema, the exact backend revision,
and an authenticated readiness response. The Lightsail `443/tcp` firewall is
still closed; the Caddy experiment remains documented but is not the active
release ingress. A failed experiment must be removed or explicitly recorded
before another route is attempted.

## Handoff status

At `2026-09-07T21:43:49Z`, the older HTTP/3 quick-tunnel session
`codex-aicaddie-quicktunnel-20260907` was stopped. The HTTP/2 session listed
above remains alive for Build 52 physical validation; its health endpoint still
reports backend revision `caf3afad55e31c3b98a378e0d1cf4c2c5fb5a737`.
