"""C67: default test writes must stay outside the checkout, including locks."""
from io import BytesIO
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from ai_caddie.caddie import decision, mobile_live
from ai_caddie.core import data as disk
from ai_caddie.courses import course_reference, vector_prep
from ai_caddie.geometry import batch_prodgeometry_course as batch
from ai_caddie.geometry import overlay_prodgeometry_on_raster as overlay, topo_render
from tests.check_isolation import repository_artifacts


ROOT = Path(__file__).resolve().parents[1]


class OfflineFollowupTests(unittest.TestCase):
    def setUp(self):
        before = repository_artifacts()
        self.addCleanup(lambda: self.assertEqual(repository_artifacts(), before))

    def assertDisposable(self, path):
        path = Path(path).resolve()
        cache = course_reference._courseview_dir().parents[1]
        self.assertFalse(path.is_relative_to(ROOT), str(path))
        self.assertTrue(path.is_relative_to(cache), str(path))
        return path

    def test_default_cache_is_in_system_temporary_directory(self):
        cache = self.assertDisposable(course_reference._courseview_dir())
        self.assertTrue(cache.is_relative_to(Path(tempfile.gettempdir()).resolve()))
        self.assertEqual(disk.ROOT, ROOT, "fixture/source root must stay intact")

    def test_default_raster_vector_and_topo_writes_are_disposable(self):
        self.assertDisposable(overlay.RASTER_CACHE)
        self.assertDisposable(vector_prep._CACHE_DIR)
        self.assertDisposable(topo_render.cache_dir())
        png = BytesIO()
        Image.new("RGB", (2, 2)).save(png, format="PNG")
        with patch.object(overlay.urllib.request, "urlopen", return_value=BytesIO(png.getvalue())):
            self.assertEqual(overlay.fetch_raster("https://fixture.invalid/c67.png").size, (2, 2))
        with (
            patch.object(vector_prep.prep_cache, "_requested_geometry_sig", return_value=()),
            patch.object(vector_prep.prep_cache, "_course_data_sig", return_value=()),
            patch.object(vector_prep.course_prep, "precise_route_seed_hole", return_value={"hole": 1}),
        ):
            self.assertEqual(vector_prep.cached_vector_hole(
                2147483600, 1, tee_set=2,
                coverage={"coverage": "ready", "geometryRevision": "c67-fixture"},
            ), {"hole": 1})
        with patch.object(topo_render, "_render_cold", return_value=png.getvalue()):
            self.assertEqual(topo_render.render_hole_topo_cached(2147483600, 1), png.getvalue())

    def test_default_batch_export_including_staging_is_disposable(self):
        # This root anchors relative_to() AND the otherwise hard-coded staging path.
        self.assertDisposable(batch.ROOT)
        # geometry_sync / batch.main create the publish directories for the worker.
        batch.HAZARD_ROOT.mkdir(parents=True, exist_ok=True)
        stages = []

        def fake_run(cmd, **kwargs):
            if "--stats" in cmd:
                output = Path(cmd[cmd.index("--out") + 1])
                stages.append(output)
                self.assertDisposable(output)
                output.write_text("{}")
                Path(cmd[cmd.index("--stats") + 1]).write_text("{}")
            elif "--out" in cmd:
                Path(cmd[cmd.index("--out") + 1]).write_text("{}")
            return True, json.dumps({"zipPasswordWorks": True, "meshCount": 1})

        with patch.object(batch, "fetch_bytes", return_value=b"fixture-zip"), \
                patch.object(batch, "run", side_effect=fake_run):
            row = batch.process_hole(
                course_id=2147483600, hole={"hole": 1, "geometry_url": "https://fixture.invalid/hole01_1.zip"},
                profile_id="fixture", snapshot=None, skip_overlay=True, force_download=True,
            )
        self.assertTrue(row["ok"], row)
        self.assertTrue(stages)
        self.assertFalse(stages[0].exists(), "batch staging was not cleaned")

    def test_batch_exporter_child_can_import_sources_from_disposable_cwd(self):
        ok, output = batch.run([
            sys.executable, "-c",
            "import os; from ai_caddie.geometry import measure_prodgeometry_distances as m; "
            "print(os.getcwd()); print(m.__file__)",
        ])
        self.assertTrue(ok, output)
        cwd, source = output.strip().splitlines()
        self.assertEqual(Path(cwd), batch.ROOT)
        self.assertTrue(Path(source).is_relative_to(ROOT))

    def test_default_decision_and_mobile_event_locks_are_disposable(self):
        from server_v2 import caddie, mobile
        self.assertDisposable(caddie.DECISION_LEDGER_ROOT)
        self.assertDisposable(mobile.MOBILE_ROOT)
        record = decision.store_decision({"decisionId": "c67-fixture", "sourceRef": "fixture-round:1"})
        self.assertEqual(record["decisionId"], "c67-fixture")
        ledger = decision.decision_ledger_file(decision.evidence_root(disk.OWNER_ID))
        self.assertDisposable(ledger)
        self.assertTrue(ledger.exists())
        for player in (disk.OWNER_ID, "c67-member"):
            self.assertDisposable(mobile_live.mobile_event_log(player_id=player))
            self.assertDisposable(mobile_live.mobile_event_ack_store(player_id=player))
            self.assertEqual(mobile_live.round_events("c67-empty", player_id=player), [])
        self.assertTrue(list(mobile.MOBILE_ROOT.rglob("*.lock")), "probe must exercise real lock creation")

    def test_explicit_roots_and_topo_override_keep_their_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(mobile_live.mobile_event_log(root), root / "data/mobile_events/events.jsonl")
            self.assertEqual(decision.decision_ledger_file(root), root / "data/decisions/decisions.jsonl")
            with patch.dict("os.environ", {"AI_CADDIE_TOPO_CACHE_DIR": tmp}):
                self.assertTrue(topo_render.cache_dir().is_relative_to(root))
