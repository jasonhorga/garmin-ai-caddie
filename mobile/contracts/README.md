# Mobile decision distance contract

`POST /api/v2/caddie/decision` accepts an open `context` object. Its optional
`distanceToPinSource` string describes the provenance of `context.distanceToPin_m`.
The request model publishes this field in OpenAPI; it is not a required field or a
closed enum, so older clients and future source strings remain accepted.

| `distanceToPinSource` | Planning distance |
|---|---|
| Omitted or `null` | Trust the supplied valid `distanceToPin_m` (legacy behaviour), except a tee request with a CoursePrep `canonicalShotPlan`: use its installed route before the phone number. |
| `manual` | Trust the supplied valid number. |
| `map_target` | Trust the supplied valid number to the chosen target/flag. |
| `gps_auto` | Prefer the valid remaining route measured from the actual ball. |
| `fallback` or any unknown value | Prefer that same remaining route. |

A valid supplied distance is finite, positive and within the existing golf-distance
limit. If the preferred number is unavailable, use a valid remaining route. If the
preferred route is unavailable, use the supplied valid number. Existing yardage and
installed-plan fallbacks still apply when neither exists. Source strings are case
sensitive; clients send the lowercase values above.

The provenance affects the total distance used for per-shot recommendations and
sequences. It does not replace the physical route: hazard intervals, `routeLocal`,
`routeEvidence.routeLength_m`, `holeRemaining_m` and route-based landing interpolation
still describe the ball-to-green remaining polyline. A valid route may be zero at
its endpoint; the shot recommendation retains the existing 1 m minimum.

Example request context:

```json
{
  "distanceToPin_m": 70,
  "distanceToPinSource": "gps_auto",
  "currentLocation": {"latitude": 0, "longitude": 0}
}
```

If that ball's remaining polyline is 100 m, automatic/fallback planning uses 100 m;
manual, map-target and legacy planning use 70 m. A manual value is never inferred
from the numerical agreement of GPS and supplied distance. Existing iOS clients do
not send the source yet; their supplied numbers therefore retain legacy priority.
