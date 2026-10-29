"""J4/4.2: the manual start/next-hole latency probe reports successful requests truthfully."""
import argparse
import asyncio
import unittest

import httpx

from tests.perf.c135_concurrency import Sample, _sample, _summarize


class ConcurrencyProbeTests(unittest.IsolatedAsyncioTestCase):
    async def test_fast_package_is_timed_when_it_completes_not_when_cold_package_finishes(self):
        async def respond(request):
            if request.url.path.endswith("/package"):
                self.assertEqual(request.url.params.get("background_geometry"), "true")
            if request.url.params.get("map_only") == "false":
                await asyncio.sleep(0.2)
            return httpx.Response(200, json={})

        args = argparse.Namespace(global_id=1, round_id="live-1-existing", tee_box="blue",
                                  latitude=0, longitude=0, radius_km=50, self_host=True,
                                  prefetch=False, install_pressure=False)
        async with httpx.AsyncClient(base_url="http://fixture", transport=httpx.MockTransport(respond)) as client:
            sample = await _sample(client, args, 0)
        self.assertLess(sample.timings["package_map_only"], sample.timings["package_cold"] / 2)

    async def test_external_sample_only_reads_the_existing_package(self):
        seen = []

        def respond(request):
            seen.append(request.url)
            return httpx.Response(200, json={})

        args = argparse.Namespace(global_id=1, round_id="live-1-existing", tee_box="blue",
                                  latitude=0, longitude=0, radius_km=50, self_host=False,
                                  prefetch=False, install_pressure=False)
        async with httpx.AsyncClient(base_url="http://fixture", transport=httpx.MockTransport(respond)) as client:
            await _sample(client, args, 0)
        packages = [url for url in seen if url.path.endswith("/package")]
        self.assertEqual(len(packages), 1)
        self.assertEqual(packages[0].params["round_id"], "live-1-existing")
        self.assertEqual(packages[0].params["map_only"], "true")
        self.assertNotIn("background_geometry", packages[0].params)
        install = next(url for url in seen if url.path.endswith("/install/status"))
        self.assertEqual(install.params["loops"], "1:front,1:back")

    def test_failed_routes_have_no_quantile_and_keep_the_original_error_detail(self):
        samples = [Sample("existing", {"topo": 3.0, "package": 900.0},
                          {"topo": 404, "package": 200}, {"topo": '{"detail":"missing"}'}, {})]
        result = _summarize(samples)
        self.assertIsNone(result["topo"]["p95Ms"])
        self.assertEqual(result["topo"]["failed"], 1)
        self.assertEqual(result["topo"]["errors"], ['{"detail":"missing"}'])
        self.assertEqual(result["package"]["p50Ms"], 900.0)

    async def test_serial_idle_probes_do_not_compete_and_include_existing_personal_package(self):
        active = peak = 0
        seen = []

        async def respond(request):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            seen.append(request.url)
            await asyncio.sleep(0.001)
            active -= 1
            return httpx.Response(200, json={})

        args = argparse.Namespace(global_id=1, round_id="live-1-existing", tee_box="blue",
                                  latitude=0, longitude=0, radius_km=50, self_host=True,
                                  prefetch=False, install_pressure=False, serial_idle=True)
        async with httpx.AsyncClient(base_url="http://fixture", transport=httpx.MockTransport(respond)) as client:
            sample = await _sample(client, args, 0)
        self.assertEqual(peak, 1)
        personal = [url for url in seen if url.path.endswith("/package")
                    and url.params["map_only"] == "false"
                    and url.params["round_id"] == args.round_id]
        self.assertEqual(len(personal), 1)
        self.assertIn("package_personal_cached", sample.timings)
