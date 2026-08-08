from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ai_caddie.geometry import batch_prodgeometry_course as batch
from ai_caddie.geometry import geometry_sync
from ai_caddie.geometry.geometry_authority import (
    authority_matches_release,
    authority_path,
    build_authority,
    cache_token,
    canonical_asset_path,
    legacy_outputs_match,
    load_authority,
    write_authority,
)


def _release(
    *, build: int = 266, release_id: str = "006-D2419-44", version: str = "220542"
) -> dict:
    return {
        "release_version": build,
        "release_id": release_id,
        "course_gen_version": 22,
        "course_name": "Fixture",
        "holes": [
            {
                "hole": 2,
                "geometry_url": (
                    "https://securemaps.garmin.cn/golf/coursegenout/prodgeometry/2000/"
                    f"gd31500/gid000001/hole02/hole02_{version}.zip?garmindlm=expires_secret"
                ),
                "raster_url": (
                    "https://birdseye.garmin.cn/birdseye/golf/raster3d/2000/"
                    f"gd31500/gid000001/hole02/gid000001_hole02_1_{version}.jpg?garmindlm=signed"
                ),
            }
        ],
    }


def _write_outputs(mesh: Path, hazard: Path, version: str) -> None:
    course_gen = int(version[:2])
    hole_version = int(version[2:])
    mesh.write_text(
        json.dumps(
            {
                "sourceDir": f"/private/Hole02_{version}",
                "hole": {
                    "GlobalId": 1,
                    "HoleNumber": 2,
                    "CourseGenVersion": course_gen,
                    "Version": hole_version,
                },
            }
        ),
        encoding="utf-8",
    )
    hazard.write_text(
        json.dumps(
            {
                "globalId": 1,
                "holeNumber": 2,
                "courseGenVersion": course_gen,
                "version": hole_version,
            }
        ),
        encoding="utf-8",
    )


class GeometryAuthorityTests(unittest.TestCase):
    def test_asset_identity_drops_regional_host_and_expiring_signature(self) -> None:
        cn = "https://securemaps.garmin.cn/a/hole02_220542.zip?garmindlm=one"
        com = "https://securemaps.garmin.com/a/hole02_220542.zip?garmindlm=two"
        self.assertEqual(canonical_asset_path(cn), "/a/hole02_220542.zip")
        self.assertEqual(canonical_asset_path(cn), canonical_asset_path(com))

    def test_legacy_pair_must_prove_same_embedded_asset_version(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            mesh = root / "gid1_h02_meshes.json"
            hazard = root / "gid1_h02_hazards.json"
            _write_outputs(mesh, hazard, "220542")
            release = _release()
            expected = build_authority(
                global_id=1,
                local_hole=2,
                release=release,
                hole=release["holes"][0],
                release_source="live",
            )
            self.assertTrue(
                legacy_outputs_match(expected, mesh_file=mesh, hazard_file=hazard)
            )
            expected["geometryAssetVersion"] = "220543"
            self.assertFalse(
                legacy_outputs_match(expected, mesh_file=mesh, hazard_file=hazard)
            )

    def test_derivative_token_changes_when_geometry_asset_changes(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            mesh = root / "gid1_h02_meshes.json"
            hazard = root / "gid1_h02_hazards.json"
            _write_outputs(mesh, hazard, "220542")
            release = _release()
            first = build_authority(
                global_id=1,
                local_hole=2,
                release=release,
                hole=release["holes"][0],
                release_source="live",
                geometry_zip_sha256="a" * 64,
            )
            sidecar = authority_path(mesh)
            write_authority(sidecar, first)
            token_a = cache_token(
                global_id=1,
                local_hole=2,
                mesh_file=mesh,
                hazard_file=hazard,
                sidecar=sidecar,
            )
            second_release = _release(version="220543")
            second = build_authority(
                global_id=1,
                local_hole=2,
                release=second_release,
                hole=second_release["holes"][0],
                release_source="live",
                geometry_zip_sha256="b" * 64,
            )
            write_authority(sidecar, second)
            token_b = cache_token(
                global_id=1,
                local_hole=2,
                mesh_file=mesh,
                hazard_file=hazard,
                sidecar=sidecar,
            )
            self.assertNotEqual(token_a, token_b)

    def test_derivative_token_changes_when_release_binding_changes(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            mesh = root / "gid1_h02_meshes.json"
            hazard = root / "gid1_h02_hazards.json"
            _write_outputs(mesh, hazard, "220542")
            first_release = _release(build=266, release_id="006-D2419-44")
            first = build_authority(
                global_id=1,
                local_hole=2,
                release=first_release,
                hole=first_release["holes"][0],
                release_source="cache",
            )
            sidecar = authority_path(mesh)
            write_authority(sidecar, first)
            token_a = cache_token(
                global_id=1,
                local_hole=2,
                mesh_file=mesh,
                hazard_file=hazard,
                sidecar=sidecar,
            )

            refreshed = _release(build=267, release_id="006-D2419-45")
            second = build_authority(
                global_id=1,
                local_hole=2,
                release=refreshed,
                hole=refreshed["holes"][0],
                release_source="live",
            )
            self.assertFalse(
                authority_matches_release(
                    first,
                    global_id=1,
                    local_hole=2,
                    mesh_file=mesh,
                    hazard_file=hazard,
                    release=refreshed,
                )
            )
            write_authority(sidecar, second)
            token_b = cache_token(
                global_id=1,
                local_hole=2,
                mesh_file=mesh,
                hazard_file=hazard,
                sidecar=sidecar,
            )
            self.assertNotEqual(token_a, token_b)


class GeometrySyncAuthorityTests(unittest.TestCase):
    def _paths(self, root: Path) -> tuple[Path, Path]:
        return root / "gid1_h02_meshes.json", root / "gid1_h02_hazards.json"

    def test_existing_legacy_output_is_bound_without_redownload_when_version_matches(
        self,
    ) -> None:
        with TemporaryDirectory() as tmp:
            mesh, hazard = self._paths(Path(tmp))
            _write_outputs(mesh, hazard, "220542")
            release = _release()
            with (
                patch.object(geometry_sync, "mesh_path", return_value=mesh),
                patch.object(geometry_sync, "hazard_path", return_value=hazard),
                patch.object(
                    geometry_sync, "_release_for_update", return_value=(release, "live")
                ),
                patch.object(geometry_sync, "process_hole") as process,
            ):
                result = geometry_sync.ensure_prodgeometry(1, 2)

            self.assertEqual(result["status"], "cached")
            self.assertEqual(result["authorityState"], "bound")
            process.assert_not_called()
            self.assertEqual(
                load_authority(authority_path(mesh))["geometryAssetVersion"], "220542"
            )

    def test_new_geometry_asset_rebuilds_and_rebinds_outputs(self) -> None:
        with TemporaryDirectory() as tmp:
            mesh, hazard = self._paths(Path(tmp))
            _write_outputs(mesh, hazard, "220542")
            old_release = _release()
            old = build_authority(
                global_id=1,
                local_hole=2,
                release=old_release,
                hole=old_release["holes"][0],
                release_source="cache",
            )
            write_authority(authority_path(mesh), old)
            new_release = _release(build=267, version="220543")

            def rebuild(**_kwargs):
                _write_outputs(mesh, hazard, "220543")
                return {"ok": True, "geometry_zip_sha256": "c" * 64, "steps": {}}

            with (
                patch.object(geometry_sync, "mesh_path", return_value=mesh),
                patch.object(geometry_sync, "hazard_path", return_value=hazard),
                patch.object(
                    geometry_sync,
                    "_release_for_update",
                    return_value=(new_release, "live"),
                ),
                patch.object(
                    geometry_sync, "process_hole", side_effect=rebuild
                ) as process,
            ):
                result = geometry_sync.ensure_prodgeometry(1, 2, profile_id="player")

            self.assertEqual(result["status"], "downloaded")
            process.assert_called_once()
            bound = load_authority(authority_path(mesh))
            self.assertEqual(bound["releaseVersion"], 267)
            self.assertEqual(bound["geometryAssetVersion"], "220543")
            self.assertEqual(bound["geometryZipSha256"], "c" * 64)

    def test_release_metadata_refresh_reuses_identical_geometry_asset(self) -> None:
        with TemporaryDirectory() as tmp:
            mesh, hazard = self._paths(Path(tmp))
            _write_outputs(mesh, hazard, "220542")
            old_release = _release()
            write_authority(
                authority_path(mesh),
                build_authority(
                    global_id=1,
                    local_hole=2,
                    release=old_release,
                    hole=old_release["holes"][0],
                    release_source="cache",
                ),
            )
            refreshed = _release(build=267, release_id="006-D2419-45")
            with (
                patch.object(geometry_sync, "mesh_path", return_value=mesh),
                patch.object(geometry_sync, "hazard_path", return_value=hazard),
                patch.object(
                    geometry_sync,
                    "_release_for_update",
                    return_value=(refreshed, "live"),
                ),
                patch.object(geometry_sync, "process_hole") as process,
            ):
                result = geometry_sync.ensure_prodgeometry(1, 2)

            self.assertEqual(result["status"], "cached")
            process.assert_not_called()
            self.assertEqual(
                load_authority(authority_path(mesh))["releaseVersion"], 267
            )


class AtomicGeometryInstallTests(unittest.TestCase):
    def test_failed_rebuild_leaves_previous_canonical_outputs_untouched(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            prod = root / "data" / "prodgeometry"
            out = root / "output" / "prodgeometry"
            hazards = root / "output" / "hazards"
            old_files = {
                out / "gid1_h02_meshes.json": "old-mesh",
                out / "gid1_h02_stats.json": "old-stats",
                out / "gid1_h02_tee_distances.json": "old-distances",
                hazards / "gid1_h02_hazards.json": "old-hazards",
            }
            for path, value in old_files.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(value, encoding="utf-8")
            zip_file = prod / "1" / "hole02_220543.zip"
            zip_file.parent.mkdir(parents=True)
            zip_file.write_bytes(b"encrypted")

            calls = 0

            def run(cmd, **_kwargs):
                nonlocal calls
                calls += 1
                if calls == 1:
                    return True, json.dumps(
                        {"zipPasswordWorks": True, "passwordLength": 10}
                    )
                if calls == 2:
                    out_path = Path(cmd[cmd.index("--out") + 1])
                    stats_path = Path(cmd[cmd.index("--stats") + 1])
                    out_path.write_text("new-mesh", encoding="utf-8")
                    stats_path.write_text("new-stats", encoding="utf-8")
                    return True, json.dumps({"meshCount": 9})
                raise RuntimeError("distance export failed")

            with (
                patch.object(batch, "ROOT", root),
                patch.object(batch, "PROD_ROOT", prod),
                patch.object(batch, "OUT_ROOT", out),
                patch.object(batch, "HAZARD_ROOT", hazards),
                patch.object(batch, "run", side_effect=run),
            ):
                result = batch.process_hole(
                    course_id=1,
                    hole={
                        "hole": 2,
                        "geometry_url": "https://example/hole02_220543.zip",
                    },
                    profile_id="player",
                    snapshot=None,
                    skip_overlay=True,
                    force_download=False,
                )

            self.assertFalse(result["ok"])
            for path, value in old_files.items():
                self.assertEqual(path.read_text(encoding="utf-8"), value)


if __name__ == "__main__":
    unittest.main()
