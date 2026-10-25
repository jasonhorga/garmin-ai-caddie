"""Acceptance coverage for card 453's mesh-first topo pipeline (G453)."""

from __future__ import annotations

from concurrent.futures import Future
from contextlib import ExitStack
import io
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from starlette.requests import Request

from ai_caddie.geometry import batch_prodgeometry_course as batch
from ai_caddie.geometry import geometry_evidence, geometry_sync, topo_render
from ai_caddie.geometry.geometry_authority import authority_path, build_authority, write_authority
from server_v2 import main as server_main


class Card453TopoDecoupleAcceptance(unittest.TestCase):
    @staticmethod
    def _request() -> Request:
        return Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/api/v2/courses/1/holes/1/topo.png",
                "headers": [],
                "query_string": b"",
                "client": ("fixture", 1),
                "server": ("fixture", 80),
                "scheme": "http",
            }
        )

    def _paths(self, root: Path) -> tuple[Path, Path, Path]:
        mesh = root / "gid1_h01_meshes.json"
        hazard = root / "gid1_h01_hazards.json"
        authority = root / "gid1_h01_authority.json"
        mesh.write_text(json.dumps({"mesh": "v1"}), encoding="utf-8")
        return mesh, hazard, authority

    def _path_patches(self, mesh: Path, hazard: Path, authority: Path):
        return (
            patch.object(geometry_evidence, "mesh_path", return_value=mesh),
            patch.object(geometry_evidence, "hazard_path", return_value=hazard),
            patch.object(topo_render, "mesh_path", return_value=mesh),
            patch.object(topo_render, "authority_path", return_value=authority),
            patch("ai_caddie.courses.course_reference.courseview_release_info", return_value=None),
        )

    def test_mesh_only_is_ready_for_topo_but_not_obstacle_coverage(self) -> None:
        with TemporaryDirectory() as tmp:
            mesh, hazard, authority = self._paths(Path(tmp))
            patches = self._path_patches(mesh, hazard, authority)
            with patches[0], patches[1], patches[2], patches[3], patches[4], patch.object(
                topo_render, "render_hole_topo_cached", return_value=b"\x89PNG\r\n"
            ):
                topo = geometry_evidence.geometry_coverage_for_hole(
                    1, 1, require_current_authority=True, require_hazards=False
                )
                full = geometry_evidence.geometry_coverage_for_hole(
                    1, 1, require_current_authority=True, require_hazards=True
                )
                obstacle_map = geometry_evidence.build_hole_map_dto(1, 1)
                response = server_main.course_hole_topo_png(
                    self._request(), global_id=1, hole=1, v=None, r=None
                )

        self.assertEqual(topo["coverage"], "ready")
        self.assertEqual(topo["fullCoverage"], "partial")
        self.assertEqual(full["coverage"], "partial")
        self.assertIsNone(full["geometryRevision"])
        self.assertEqual(obstacle_map["coverage"], "partial")
        self.assertEqual(response.status_code, 200)

    def test_mesh_only_default_coverage_keeps_caddie_geometry_unready(self) -> None:
        with TemporaryDirectory() as tmp:
            mesh, hazard, authority = self._paths(Path(tmp))
            with patch.object(geometry_evidence, "mesh_path", return_value=mesh), patch.object(
                geometry_evidence, "hazard_path", return_value=hazard
            ):
                default = geometry_evidence.geometry_coverage_for_hole(1, 1)
        self.assertEqual(default["coverage"], "partial")
        self.assertTrue(default["requiresHazards"])

    def test_hazard_arrival_does_not_change_topo_identity(self) -> None:
        with TemporaryDirectory() as tmp:
            mesh, hazard, authority = self._paths(Path(tmp))
            patches = self._path_patches(mesh, hazard, authority)
            with patches[2], patches[3]:
                before = topo_render.cache_identity(1, 1)
                hazard.write_text(json.dumps({"hazards": []}), encoding="utf-8")
                after = topo_render.cache_identity(1, 1)
        self.assertEqual(before, after)

    def test_route_identity_change_changes_topo_identity(self) -> None:
        with TemporaryDirectory() as tmp:
            mesh, hazard, authority = self._paths(Path(tmp))
            release = {
                "release_version": 1,
                "release_id": "release-1",
                "course_gen_version": 22,
                "holes": [
                    {
                        "hole": 1,
                        "geometry_url": "https://example/hole01_220543.zip",
                        "raster_url": "https://example/route.jpg",
                        "routeIdentity": "route-a",
                    }
                ],
            }
            write_authority(
                authority,
                build_authority(
                    global_id=1,
                    local_hole=1,
                    release=release,
                    hole=release["holes"][0],
                    release_source="cache",
                    geometry_zip_sha256="a" * 64,
                ),
            )
            patches = self._path_patches(mesh, hazard, authority)
            with patches[2], patches[3]:
                before = topo_render.cache_identity(1, 1)
                changed = json.loads(authority.read_text(encoding="utf-8"))
                changed["routeIdentity"] = "route-b"
                write_authority(authority, changed)
                after = topo_render.cache_identity(1, 1)
        self.assertNotEqual(before, after)

    def test_filling_only_hazards_keeps_bound_topo_identity(self) -> None:
        with TemporaryDirectory() as tmp:
            mesh, hazard, authority = self._paths(Path(tmp))
            release = {
                "release_version": 1,
                "release_id": "release-1",
                "course_gen_version": 22,
                "holes": [
                    {
                        "hole": 1,
                        "geometry_url": "https://example/hole01_220543.zip",
                        "raster_url": "https://example/route.jpg",
                        "routeIdentity": "route-a",
                    }
                ],
            }
            write_authority(
                authority,
                build_authority(
                    global_id=1,
                    local_hole=1,
                    release=release,
                    hole=release["holes"][0],
                    release_source="cache",
                    geometry_zip_sha256="a" * 64,
                ),
            )
            patches = self._path_patches(mesh, hazard, authority)
            with patches[2], patches[3]:
                before = topo_render.cache_identity(1, 1)
                hazard.write_text(json.dumps({"globalId": 1, "holeNumber": 1}), encoding="utf-8")
                after = topo_render.cache_identity(1, 1)
        self.assertEqual(before, after)

    def test_mesh_identity_change_rejects_old_revision(self) -> None:
        with TemporaryDirectory() as tmp:
            mesh, hazard, authority = self._paths(Path(tmp))
            patches = self._path_patches(mesh, hazard, authority)
            with patches[2], patches[3]:
                old_revision = topo_render.cache_identity(1, 1)
                mesh.write_text(json.dumps({"mesh": "v2-new-release"}), encoding="utf-8")
                new_revision = topo_render.cache_identity(1, 1)
            with patch(
                "ai_caddie.geometry.geometry_evidence.geometry_coverage_for_hole",
                return_value={"coverage": "ready", "geometryRevision": new_revision},
            ), patch.object(topo_render, "render_hole_topo_cached") as render:
                with self.assertRaises(HTTPException) as raised:
                    server_main.course_hole_topo_png(
                        self._request(),
                        global_id=1,
                        hole=1,
                        v=topo_render.STYLE_VERSION,
                        r=old_revision,
                    )
        self.assertNotEqual(old_revision, new_revision)
        self.assertEqual(raised.exception.status_code, 409)
        render.assert_not_called()

    def test_topo_and_green_do_not_refresh_release_on_request(self) -> None:
        coverage = {
            "coverage": "ready",
            "geometryRevision": "revision-1",
        }
        with patch(
            "ai_caddie.geometry.geometry_evidence.geometry_coverage_for_hole",
            return_value=coverage,
        ) as probe, patch(
            "ai_caddie.courses.course_reference.courseview_release_info",
            side_effect=AssertionError("request path must not fetch Garmin release"),
        ) as release_info, patch.object(
            topo_render, "render_hole_topo_cached", return_value=b"topo"
        ), patch.object(
            topo_render, "render_hole_green_detail_cached", return_value=b"green"
        ):
            topo = server_main.course_hole_topo_png(
                self._request(), global_id=1, hole=1, v=None, r=None
            )
            green = server_main.course_hole_green_detail_png(
                self._request(),
                global_id=1,
                hole=1,
                x=1,
                y=1,
                width=100,
                height=100,
                size=1280,
                v=None,
                g=None,
                r=None,
            )
        self.assertEqual(topo.status_code, 200)
        self.assertEqual(green.status_code, 200)
        self.assertEqual(probe.call_count, 2)
        for call in probe.call_args_list:
            self.assertFalse(call.kwargs["refresh_release"])
            self.assertFalse(call.kwargs["require_hazards"])
        release_info.assert_not_called()

        # The endpoint path is also forbidden from reaching the Garmin release loader.  This
        # lower-level spy catches an accidental refresh hidden behind course-reference helpers.
        with TemporaryDirectory() as tmp:
            mesh, hazard, _authority = self._paths(Path(tmp))
            with patch.object(geometry_evidence, "mesh_path", return_value=mesh), patch.object(
                geometry_evidence, "hazard_path", return_value=hazard
            ), patch(
                "ai_caddie.courses.course_reference.load_release_pb"
            ) as garmin_loader:
                geometry_evidence.geometry_coverage_for_hole(
                    1, 1, require_current_authority=True, refresh_release=False,
                    require_hazards=False,
                )
            garmin_loader.assert_not_called()

    def test_install_queues_topo_before_hazards_then_builds_real_vector_cache(self) -> None:
        self._assert_install_vector_cache()

    def test_warm_install_rebuilds_missing_vector_cache(self) -> None:
        self._assert_install_vector_cache(rebuild_warm=True)

    def test_hazard_loaders_refresh_after_deferred_publication(self) -> None:
        from ai_caddie.caddie import analysis, mobile_live

        with TemporaryDirectory() as tmp:
            mesh, hazard, _authority = self._paths(Path(tmp))
            with (patch.object(analysis, "hazard_path", return_value=hazard),
                  patch.object(analysis, "mesh_path", return_value=mesh),
                  patch.object(mobile_live, "hazard_path", return_value=hazard)):
                # Prime both LRUs in the supplementation window. No cache_clear follows.
                self.assertFalse(analysis.load_geometry(1, 1)["hasHazards"])
                self.assertEqual(mobile_live._load_mobile_hazards(1, 1), {})
                facts = {"tees": [{"position": [0, 0], "target_distance_m": 300}],
                         "hazards": [{"kind": "water"}]}

                def assert_facts():
                    geometry = analysis.load_geometry(1, 1)
                    mobile = mobile_live._load_mobile_hazards(1, 1)
                    self.assertTrue(geometry["hasHazards"])
                    self.assertEqual(geometry["hazards"]["tees"], facts["tees"])
                    self.assertEqual(mobile["tees"], facts["tees"])
                    self.assertEqual(mobile["hazards"], facts["hazards"])
                    self.assertIs(analysis.load_geometry(1, 1), geometry)
                    self.assertIs(mobile_live._load_mobile_hazards(1, 1), mobile)

                hazard.write_text(json.dumps(facts))
                assert_facts()
                # Same inode/size, changed mtime: distance corrections must refresh too.
                stat = hazard.stat()
                facts["tees"][0]["target_distance_m"] = 301
                hazard.write_text(json.dumps(facts))
                os.utime(hazard, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
                self.assertEqual(hazard.stat().st_size, stat.st_size)
                assert_facts()
                # Keep mtime fixed while size changes, proving both signature fields matter.
                stat = hazard.stat()
                facts["hazards"].append({"kind": "bunker"})
                hazard.write_text(json.dumps(facts))
                os.utime(hazard, ns=(stat.st_atime_ns, stat.st_mtime_ns))
                assert_facts()

    def _assert_install_vector_cache(self, *, rebuild_warm: bool = False) -> None:
        from ai_caddie.courses import vector_prep
        from server_v2 import course_install
        events = []
        obstacle_release, obstacle_entered = Event(), Event()

        class ImmediateTopoPool:
            def submit_keyed(self, key, fn, *args, **kwargs):
                return self.submit(fn, *args, **kwargs)

            def submit(self, fn, *args, **kwargs):
                events.append("queue_topo")
                future = Future()
                future.set_result(fn(*args))
                return future

        with TemporaryDirectory() as tmp, ExitStack() as stack:
            root = Path(tmp)
            out = root / "output" / "prodgeometry"
            hazards = root / "output" / "hazards"
            mesh = out / "gid123_h01_meshes.json"
            hazard = hazards / "gid123_h01_hazards.json"
            cache = root / "vectors"
            release = {
                "release_version": 1, "release_id": "release-1", "course_gen_version": 22,
                "holes": [{"hole": 1, "geometry_url": "https://example/hole01_220543.zip"}],
            }
            def run(cmd, **kwargs):
                if "--json" in cmd:
                    return True, '{"zipPasswordWorks": true}'
                target = Path(cmd[cmd.index("--out") + 1])
                if "--stats" in cmd:
                    def rectangle(name, x0, y0, x1, y1):
                        return {"name": name, "positions": [[-x0, 0, y0], [-x1, 0, y0], [-x1, 0, y1], [-x0, 0, y1]],
                                "faces": [[0, 1, 2], [0, 2, 3]]}
                    target.write_text(json.dumps({
                        "sourceDir": "Hole01_220543",
                        "hole": {"GlobalId": 123, "HoleNumber": 1, "CourseGenVersion": 22, "Version": 543,
                                 "RefLat": 47, "RefLon": 12,
                                 "TeeLocations": [{"Sets": [2], "X": 0, "Y": 0}],
                                 "Doglegs": [{"Line": [{"X": 0, "Y": 0}, {"X": 0, "Y": 300}]}]},
                        "meshes": [rectangle("Fairway.drc", -12, 10, 12, 290),
                                   rectangle("Green.drc", -10, 290, 10, 310)],
                    }))
                    Path(cmd[cmd.index("--stats") + 1]).write_text("{}")
                    return True, '{"meshCount": 2}'
                if "ai_caddie.geometry.export_prodgeometry_hazards" in cmd:
                    obstacle_entered.set()
                    self.assertTrue(obstacle_release.wait(5))
                    events.append("obstacle_done")
                target.write_text("{}")
                return True, "ok"
            for obj, name, value in (
                (batch, "ROOT", root), (batch, "PROD_ROOT", root / "prod"),
                (batch, "OUT_ROOT", out), (batch, "HAZARD_ROOT", hazards),
                (batch, "run", run), (batch, "fetch_bytes", lambda _: b"encrypted"),
                (geometry_sync, "mesh_path", lambda *_: mesh),
                (geometry_sync, "hazard_path", lambda *_: hazard),
                (geometry_sync, "distances_path", lambda *_: out / "gid123_h01_tee_distances.json"),
                (geometry_sync, "_release_for_update", lambda *a, **k: (release, "cache")),
                (geometry_sync, "_player_profile_id", lambda: "fixture"),
                (geometry_evidence, "mesh_path", lambda *_: mesh),
                (geometry_evidence, "hazard_path", lambda *_: hazard),
                (vector_prep, "_CACHE_DIR", cache),
                (vector_prep.course_prep.hole_render, "mesh_path", lambda *_: mesh),
                (vector_prep.prep_cache, "MESH_DIR", out),
                (vector_prep.prep_cache, "HAZARD_DIR", hazards),
                (server_main, "_TOPO_PIPELINE_POOL", ImmediateTopoPool()),
            ):
                stack.enter_context(patch.object(obj, name, value))
            stack.enter_context(patch.dict(os.environ, {"AI_CADDIE_COURSE_INSTALL_DIR": str(root / "jobs")}))
            stack.enter_context(patch.object(course_install, "_launch"))
            stack.enter_context(patch("ai_caddie.courses.course_reference.courseview_release_info", return_value=release))
            stack.enter_context(patch("ai_caddie.courses.courseview_core.load_cached_course_data", return_value=None))
            stack.enter_context(patch("ai_caddie.caddie.analysis.tee_set_for_box", return_value=2))
            stack.enter_context(patch.object(vector_prep.course_prep.course_reference, "load_course_par", return_value=None))
            def render(*a, **k):
                events.append("topo_rendered")
                return b"PNG"
            stack.enter_context(patch.object(topo_render, "render_hole_topo_cached", side_effect=render))
            state = course_install.enqueue(global_id=123, tee_box="blue", loop_key="123:all", player_id="owner",
                refs=[{"globalId": 123, "localHole": 1}], requested={123: [1]}, ready={})
            try:
                server_main.run_course_install_job(state["jobId"])
                self.assertTrue(obstacle_entered.wait(2))
                self.assertIn("topo_rendered", events)
                self.assertFalse(hazard.exists())
                self.assertEqual(list(cache.rglob("*.json")), [])
                pending = geometry_evidence.geometry_coverage_for_hole(123, 1)
                self.assertEqual(pending["missingData"][0]["state"], "pending")
                workers = [w for k, w in batch._DERIVATIVE_JOBS.items() if k[2] == str(mesh)]
                obstacle_release.set()
                for worker in workers:
                    worker.join(5)
                    self.assertFalse(worker.is_alive())
                files = list(cache.rglob("h01-*.json"))
                self.assertEqual(len(files), 1)
                stored = json.loads(files[0].read_text())
                self.assertTrue(stored["hole"]["map"]["overlay"]["surfaces"])
                self.assertIsNotNone(vector_prep.cached_vector_hole(123, 1, build_if_missing=False))
                self.assertLess(events.index("topo_rendered"), events.index("obstacle_done"))
                final = course_install.state_for_worker(state["jobId"])
                self.assertEqual(final["phase"], "ready")
                if rebuild_warm:
                    files[0].unlink()
                    # A fresh install journal reuses the installed hole, without an exporter.
                    state = course_install.enqueue(global_id=123, tee_box="blue", loop_key="123:front",
                        player_id="owner", refs=[{"globalId": 123, "localHole": 1}],
                        requested={123: [1]}, ready={})
                    events.clear()
                    with patch.object(batch, "run", side_effect=AssertionError("warm install must reuse geometry")):
                        server_main.run_course_install_job(state["jobId"])
                    self.assertEqual(events, ["queue_topo", "topo_rendered"])
                    self.assertEqual(len(list(cache.rglob("h01-*.json"))), 1)
                    self.assertIsNotNone(vector_prep.cached_vector_hole(123, 1, build_if_missing=False))
            finally:
                obstacle_release.set()
                for worker in [w for k, w in batch._DERIVATIVE_JOBS.items() if k[2] == str(mesh)]:
                    worker.join(5)

    def test_deferred_hazard_export_failure_keeps_mesh_and_topo_coverage(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            prod = root / "data" / "prodgeometry"
            out = root / "output" / "prodgeometry"
            hazards = root / "output" / "prodgeometry_hazards"
            zip_file = prod / "1" / "hole01_220543.zip"
            zip_file.parent.mkdir(parents=True)
            zip_file.write_bytes(b"encrypted")

            def run(cmd, **_kwargs):
                if "--json" in cmd:
                    return True, json.dumps({"zipPasswordWorks": True})
                if "--stats" in cmd:
                    mesh_path = Path(cmd[cmd.index("--out") + 1])
                    stats_path = Path(cmd[cmd.index("--stats") + 1])
                    mesh_path.write_text(
                        json.dumps(
                            {
                                "sourceDir": "Hole01_220543",
                                "hole": {"GlobalId": 1, "HoleNumber": 1, "CourseGenVersion": 22, "Version": 543},
                            }
                        ),
                        encoding="utf-8",
                    )
                    stats_path.write_text("{}", encoding="utf-8")
                    return True, json.dumps({"meshCount": 1})
                if "measure_prodgeometry_distances" in cmd:
                    out_path = Path(cmd[cmd.index("--out") + 1])
                    out_path.write_text("{}", encoding="utf-8")
                    return True, "distance ok"
                raise RuntimeError("hazard exporter failed")

            def run_deferred_job(
                course_id, hole_number, mesh_file, distance_target, hazard_target, *, release_identity=None
            ):
                write_authority(authority_path(mesh_file), {
                    "schema": "garmin-prodgeometry-authority-v1", "globalId": course_id,
                    "localHole": hole_number, **(release_identity or {}),
                })
                identity, digest, descriptor = batch._derivative_snapshot(
                    mesh_file, release_identity=release_identity
                )
                batch._run_derivatives(
                    course_id,
                    hole_number,
                    mesh_file,
                    distance_target,
                    hazard_target,
                    identity,
                    digest,
                    descriptor,
                )

            with patch.object(batch, "ROOT", root), patch.object(batch, "PROD_ROOT", prod), patch.object(
                batch, "OUT_ROOT", out
            ), patch.object(batch, "HAZARD_ROOT", hazards), patch.object(batch, "run", side_effect=run), patch.object(
                batch, "_start_derivative_job", side_effect=run_deferred_job
            ) as start_job:
                result = batch.process_hole(
                    course_id=1,
                    hole={"hole": 1, "geometry_url": "https://example/hole01_220543.zip"},
                    profile_id="fixture",
                    snapshot=None,
                    skip_overlay=True,
                    force_download=False,
                    defer_derivatives=True,
                )

            mesh = out / "gid1_h01_meshes.json"
            self.assertTrue(result["ok"])
            self.assertTrue(result["mesh_ready"])
            start_job.assert_called_once()
            self.assertTrue(mesh.is_file())
            with patch.object(geometry_evidence, "mesh_path", return_value=mesh), patch.object(
                geometry_evidence, "hazard_path", return_value=hazards / "gid1_h01_hazards.json"
            ):
                topo = geometry_evidence.geometry_coverage_for_hole(1, 1, require_hazards=False)
                full = geometry_evidence.geometry_coverage_for_hole(1, 1, require_hazards=True)
                obstacle_map = geometry_evidence.build_hole_map_dto(1, 1)
        self.assertEqual(topo["coverage"], "ready")
        self.assertEqual(full["coverage"], "partial")
        failure = next(row for row in full["missingData"] if row["label"] == "hazards")
        self.assertEqual(failure["state"], "failed")
        self.assertEqual(failure["failureCount"], 1)
        self.assertEqual(failure["lastErrorType"], "RuntimeError")
        self.assertIn(failure, obstacle_map["missingData"])
        self.assertEqual(obstacle_map["coverage"], "partial")

    def test_old_derivative_worker_is_discarded_after_mesh_replacement(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            mesh = root / "mesh.json"
            distance = root / "distance.json"
            hazard = root / "hazard.json"
            mesh.write_text("old-mesh", encoding="utf-8")
            identity, digest, descriptor = batch._derivative_snapshot(
                mesh,
                release_identity={"geometryAssetPath": "/old/hole.zip"},
            )
            mesh.write_text("new-mesh", encoding="utf-8")

            def export(cmd, **_kwargs):
                Path(cmd[cmd.index("--out") + 1]).write_text("stale", encoding="utf-8")
                return True, "ok"

            with patch.object(batch, "run", side_effect=export):
                batch._run_derivatives(
                    1, 1, mesh, distance, hazard, identity, digest, descriptor
                )

            self.assertFalse(distance.exists())
            self.assertFalse(hazard.exists())

    def test_cached_mesh_requeues_missing_derivatives_after_worker_failure(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            mesh, hazard, authority = self._paths(root)
            release = {
                "release_version": 1,
                "release_id": "release-1",
                "course_gen_version": 22,
                "holes": [{
                    "hole": 1,
                    "geometry_url": "https://example/hole01_220543.zip",
                    "raster_url": "https://example/route-1.jpg",
                }],
            }
            write_authority(
                authority_path(mesh),
                build_authority(
                    global_id=1,
                    local_hole=1,
                    release=release,
                    hole=release["holes"][0],
                    release_source="cache",
                    geometry_zip_sha256="a" * 64,
                ),
            )
            with patch.object(geometry_sync, "mesh_path", return_value=mesh), patch.object(
                geometry_sync, "hazard_path", return_value=hazard
            ), patch.object(
                geometry_sync, "_release_for_update", return_value=(release, "cache")
            ), patch.object(geometry_sync, "_schedule_missing_derivatives") as retry:
                result = geometry_sync.ensure_prodgeometry(1, 1)

        self.assertEqual(result["status"], "cached")
        retry.assert_called_once()

    def test_failed_derivative_export_uses_exponential_backoff(self) -> None:
        starts: list[object] = []
        clock = [100.0]

        class CapturedExecutor:
            def submit_keyed(self, key, target, *args, **kwargs):
                from concurrent.futures import Future
                future = Future()
                def execute():
                    future.set_running_or_notify_cancel()
                    try:
                        target(*args)
                        future.set_result(None)
                    except BaseException as exc:
                        future.set_exception(exc)
                        raise
                from types import SimpleNamespace
                starts.append(SimpleNamespace(target=execute, args=()))
                return future

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            mesh = root / "mesh.json"
            distance = root / "distance.json"
            hazard = root / "hazard.json"
            mesh.write_text("mesh", encoding="utf-8")
            with patch.object(batch, "_DERIVATIVE_POOL", CapturedExecutor()), patch.object(
                batch.time, "monotonic", side_effect=lambda: clock[0]
            ), patch.object(batch.time, "time", side_effect=lambda: clock[0]), patch.object(
                batch, "run", return_value=(False, "export failed")):

                self.assertTrue(
                    batch.schedule_missing_derivatives(
                        1,
                        1,
                        mesh_file=mesh,
                        distance_target=distance,
                        hazard_target=hazard,
                    )
                )
                # Run the captured worker synchronously so its failure records the backoff state.
                starts[0].target(*starts[0].args)
                batch.schedule_missing_derivatives(
                    1,
                    1,
                    mesh_file=mesh,
                    distance_target=distance,
                    hazard_target=hazard,
                )
                self.assertEqual(len(starts), 1)
                # Retry state survives loss of the in-memory registry (process restart).
                batch._DERIVATIVE_FAILURES.clear()
                batch.schedule_missing_derivatives(1, 1, mesh_file=mesh,
                    distance_target=distance, hazard_target=hazard)
                self.assertEqual(len(starts), 1)
                clock[0] = 130.1
                batch.schedule_missing_derivatives(
                    1,
                    1,
                    mesh_file=mesh,
                    distance_target=distance,
                    hazard_target=hazard,
                )
                self.assertEqual(len(starts), 2)
                starts[1].target(*starts[1].args)
                from ai_caddie.geometry.geometry_authority import load_derivatives_status
                status = load_derivatives_status(mesh)
                self.assertEqual(status["failureCount"], 2)
                self.assertAlmostEqual(status["retryAfterEpoch"] - clock[0], 60)
                identity = batch._derivative_snapshot(mesh)[0]
                key = batch._derivative_key(1, 1, mesh, distance, hazard, identity)
                for _ in range(25):
                    batch._record_derivative_result(key, success=False)
                # C34: no attempt cap; the backoff ceiling is 6 h = 6 * 3600 s.
                self.assertEqual(load_derivatives_status(mesh)["retryAfterEpoch"] - clock[0], 21600)

    def test_pending_package_mesh_revision_does_not_rebind_ready_install(self):
        from ai_caddie.caddie import mobile_live
        from server_v2 import course_install
        from ai_caddie.geometry.geometry_authority import write_derivatives_status
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            mesh, hazard, authority = self._paths(root)
            release = {"release_version": 1, "release_id": "one", "course_gen_version": 22,
                       "holes": [{"hole": 1, "geometry_url": "https://example/hole01_220543.zip"}]}
            write_authority(authority, build_authority(global_id=1, local_hole=1, release=release,
                hole=release["holes"][0], release_source="cache", geometry_zip_sha256="a" * 64))
            with (patch.object(geometry_evidence, "mesh_path", return_value=mesh),
                  patch.object(geometry_evidence, "hazard_path", return_value=hazard),
                  patch.object(geometry_sync, "mesh_path", return_value=mesh),
                  patch.object(geometry_sync, "hazard_path", return_value=hazard),
                  patch.object(geometry_sync, "distances_path", return_value=root / "distances.json"),
                  patch("ai_caddie.courses.course_reference.courseview_release_info", return_value=release),
                  patch.dict(os.environ, {"AI_CADDIE_COURSE_INSTALL_DIR": str(root / "jobs")}),
                  patch.object(course_install, "_launch") as launch):
                package_rows = mobile_live._package_holes({"globalId": 1}, {}, course_key="fixture", hole_numbers=[1])
                row = package_rows[0]
                self.assertEqual(row["geometryCoverage"], "partial")
                self.assertTrue(row["geometryRevision"])
                self.assertEqual(row["geometryAuthorityObservation"], "current")
                kwargs = dict(global_id=1, tee_box="blue", loop_key="1:all", player_id="owner",
                    refs=[{**row, "globalId": 1, "localHole": 1}], requested={1: [1]}, ready={})
                state = course_install.enqueue(**kwargs)
                course_install.update(state["jobId"], global_id=1, local_hole=1, geometry="ready",
                    geometry_revision=row["geometryRevision"], topo="ready", topo_revision=row["geometryRevision"])
                before = course_install.state_for_worker(state["jobId"])
                launch.reset_mock()
                for status in ("pending", "failed"):
                    write_derivatives_status(mesh, {"status": status, "failureCount": 2, "lastErrorType": "RuntimeError"})
                    result = course_install.enqueue(**kwargs)
                    # C34: the missing obstacle export keeps the job open (no live plan exists),
                    # but the installed mesh/topo are neither rebound nor re-rendered.
                    self.assertEqual(result["phase"], "queued")
                    self.assertEqual(result["holes"][0]["topoRevision"], row["geometryRevision"])
                    after = course_install.state_for_worker(state["jobId"])
                    self.assertEqual(after["generation"], before["generation"])
                    self.assertEqual(after["workRevision"], before["workRevision"])
                    self.assertEqual(after["holes"]["1:1"]["derivatives"], "queued")
                launch.assert_called_with(state["jobId"])

    def test_startup_reports_pending_while_obstacles_are_missing(self):
        from server_v2 import map_startup
        from ai_caddie.caddie.round_loops import CourseShape
        with TemporaryDirectory() as tmp:
            mesh, hazard, authority = self._paths(Path(tmp))
            with (patch.object(map_startup, "courseview_release_info", return_value={"holes": 9}),
                  patch.object(map_startup, "ensure_startup_course_data"),
                  patch("ai_caddie.caddie.mobile_live.course_shape_from_release", return_value=CourseShape(9, "venue")),
                  patch("ai_caddie.geometry.geometry_sync.ensure_prodgeometry", return_value={"ok": True}),
                  patch("ai_caddie.courses.course_reference.courseview_release_info", return_value=None),
                  patch("ai_caddie.caddie.analysis.tee_set_for_box", return_value=2),
                  patch.object(geometry_evidence, "mesh_path", return_value=mesh),
                  patch.object(geometry_evidence, "hazard_path", return_value=hazard)):
                result = map_startup.prepare_priority_hole([(1, "all")])
                self.assertFalse(result["drawable"])
                self.assertTrue(result["pending"])

    def test_release_without_new_course_data_retains_bound_route_identity(self):
        from ai_caddie.geometry.geometry_authority import cache_token
        route_a = [(47.0, 12.0), (47.003, 12.0)]
        route_b = [(47.0, 12.0), (47.004, 12.0)]
        with TemporaryDirectory() as tmp:
            mesh, hazard, authority = self._paths(Path(tmp))
            release = {"release_version": 1, "holes": [{"hole": 1,
                       "geometry_url": "https://example/hole01_220543.zip"}]}
            manifest = build_authority(global_id=1, local_hole=1, release=release,
                hole=release["holes"][0], release_source="cache", geometry_zip_sha256="a" * 64)
            write_authority(authority, manifest)
            def token():
                return cache_token(global_id=1, local_hole=1, mesh_file=mesh, hazard_file=hazard)
            with patch("ai_caddie.courses.courseview_core.load_cached_hole_route", return_value=route_a) as route:
                before = token()
                # Simulate a process restart + authority rebind before new courseData arrives.
                write_authority(authority, {**manifest, "releaseVersion": 2})
                route.return_value = None
                self.assertEqual(token(), before)
                route.return_value = route_a
                self.assertEqual(token(), before)
                route.return_value = route_b
                self.assertNotEqual(token(), before)

    def test_mesh_sha256_cache_uses_mtime_and_size_fingerprint(self) -> None:
        with TemporaryDirectory() as tmp:
            mesh = Path(tmp) / "mesh.json"
            mesh.write_bytes(b"aaaa")
            with patch.object(io, "open", wraps=io.open) as opened:
                first = batch.file_sha256(mesh)
                second = batch.file_sha256(mesh)
            self.assertEqual(first, second)
            self.assertEqual(opened.call_count, 1)

            stat = mesh.stat()
            replacement = mesh.with_suffix(".replacement")
            replacement.write_bytes(b"bbbb")
            os.utime(replacement, ns=(stat.st_atime_ns, stat.st_mtime_ns))
            replacement.replace(mesh)
            changed = batch.file_sha256(mesh)
        self.assertNotEqual(first, changed)


if __name__ == "__main__":
    unittest.main()
