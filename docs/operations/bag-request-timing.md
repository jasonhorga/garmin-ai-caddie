# Bag request timing

Both bag GET routes keep their existing authorization and response contracts:
`/api/v2/history/clubs/bag` and `/api/v2/players/{player_id}/clubs/bag`.
Their authorization checks and disk reads/projections use a separate, four-slot
AnyIO limiter so course/startup work occupying the default worker pool cannot
queue an already-saved bag behind it. This does not isolate CPU starvation, GIL
contention, disk stalls or a slow identity database; those can still take time.
No extra bag or credential cache is introduced.

Send `X-AI-Caddie-Request-ID` to correlate the response header, server timing
record and the existing mobile client timing upload. Server timing starts
before the authorization middleware. The following explicit spans are in
`Server-Timing` and the persisted record's `stages` (milliseconds):

| Span | Boundary |
| --- | --- |
| `auth_gate` | Existing middleware authorization check, including any credential lookup |
| `auth_player` | Existing `current_player_id` dependency resolution |
| `bag_read_projection` | Saved bag load, projection and response model construction |
| `<span>_worker_queue` | Submission until the corresponding worker starts, including limiter wait and worker scheduling |

`response` and `total` are inclusive server intervals through response readiness,
before body transport, not additional execution stages to sum with the spans.
Response encoding and middleware overhead remain
outside the explicit spans. A denied request has only the stages it reached;
no response header can be delivered after transport cancellation. A server task
cancellation is recorded as status 499 with a `cancelled` stage. Client-side
cancellation is distinct even when the server goes on to finish a 200 response.

An authenticated administrator can request
`GET /api/v2/admin/timing?request_id=<request-id>&include_client=true`.
The default query shape is unchanged. The optional `client_timing` joins on
both request ID and route template, exposes `client_total_ms`, and reports
`outcome` as `response`, `cancelled`, `error`, `missing` or `ambiguous`.
Duplicate IDs are ambiguous; missing records are never inferred from timestamps.
Client cancellations (`cancelled` or URL error `url_-999`, for example), server
499s, other client errors and mismatched statuses have no subtracted interval.

For paired responses with matching statuses, `outside_server_timing_ms` is the
signed client total minus server total. It includes any client scheduling,
ingress, transfer and difference in measurement boundaries. It is **not network
time** and may be negative. Client records without a server counterpart remain
in the client timing files; the server query cannot invent their server stages.
