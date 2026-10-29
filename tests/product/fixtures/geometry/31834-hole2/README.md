# Release 290 geometry: 31834, hole 2

Sanitized subset of the read-only course geometry supplied for the J4.6/J5.11 regression.
This contains no player profile, scores, shots, decisions, cookies or credentials. The test bag
is synthetic: Driver 197 m and 8I 121 m, with explicit dispersion and sample counts.

The six input files retain the real release/authority binding, selected Blue Tee, dogleg,
Green triangles and hazard components. All triangles/vertices of retained meshes are unchanged;
component numbering and compact tee-to-target summaries are preserved. The decoded export keeps
only Green, Teebox, Fairway and the meshes referenced by route-risk hazards. It omits its source
host path, foliage and unused surfaces. The compact hazard export keeps features from those
retained meshes. The lightweight courseData keeps only hole 2's route. Raw drc, Terrain.webp,
raster imagery, generated renders, prep plans and player data are unnecessary and omitted.

The protobuf's 27 `garmindlm` query values use the fixed, equal-length placeholder
`1790000000_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa`, matching the signed-release fixture convention.
The metadata SHA-256 describes those sanitized protobuf bytes; fetchedAt is zero. Release facts,
asset paths and geometry authority remain real, and the test runs without network access.

Independent investigation measurements: route 320.9 m; water 50.5–84.2 m; green route window
306.2–320.9 m. The synthetic bag reaches station 318 in two shots, on the selected physical green.
The old endpoint chord instead reports 283.8 m with water 45.3–249.9 m and rejects the route.

`tests.product.test_j5_play.ReleaseGeometryDecisionTests` exercises the real HTTP endpoint in a
fresh process, using `_real_route_probe.py`. Import-time roots point at a temporary fixture copy;
all loaders and authority checks remain real, corrected profile history is disabled, network
connections fail, and decision ledger writes stay in that temporary copy. The helper interpolates
the returned final station over the factual Blue Tee/Doglegs path and tests containment against
the selected real Green triangles. Timing samples are diagnostic, with no CI timing threshold.
