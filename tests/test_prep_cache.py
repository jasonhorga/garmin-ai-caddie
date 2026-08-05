"""prep_cache: fingerprint-keyed cache for course_prep (the ~19s /courses/{id}/prep build).

Locks in: a 2nd identical request is a cache HIT (build runs once); a different player or a
changed fingerprint (new sync / regenerated geometry) forces a rebuild — so 备战 is instant while
inputs are unchanged but never serves stale prep after a sync. unittest on purpose (CI uses
`python -m unittest discover`, which ignores pytest fixtures).
"""

from __future__ import annotations

import os
import tempfile
import threading
import time
import unittest
from pathlib import Path

from ai_caddie.courses import prep_cache


class PrepCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        prep_cache.clear()
        self._orig_fingerprint = prep_cache._fingerprint

    def tearDown(self) -> None:
        prep_cache._fingerprint = self._orig_fingerprint
        prep_cache.clear()

    def test_hit_miss_on_player_and_fingerprint(self) -> None:
        calls: list[int] = []
        prep_cache._fingerprint = lambda gid, *_: ("fp1",)

        def build() -> dict:
            calls.append(1)
            return {"build": len(calls)}

        def call(player: str = "me") -> dict:
            return prep_cache.cached_course_prep(
                global_id=31794, requested=[1, 2, 3], render=True,
                include_shots=False, player_id=player, build=build,
            )

        first = call()
        second = call()
        self.assertEqual(len(calls), 1, "2nd identical request must be a cache hit")
        self.assertIs(first, second)

        # Different player → different key → rebuild (owner ladder/scatter must never be reused).
        call(player="guest")
        self.assertEqual(len(calls), 2)

        # Fingerprint change (a sync landed new shots / geometry regenerated) → rebuild same key.
        prep_cache._fingerprint = lambda gid, *_: ("fp2",)
        call()
        self.assertEqual(len(calls), 3)

        # Back to a stable fingerprint → hits again (no rebuild).
        call()
        self.assertEqual(len(calls), 3)

    def test_dir_sig_detects_in_place_edit_of_a_non_newest_file(self) -> None:
        # Mirror of stats_cache: the old (count, newest-mtime) sig missed an in-place edit
        # to a non-newest file (count + newest-mtime unchanged) and could serve stale prep.
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (older := d / "a.json").write_text("{}")
            (newer := d / "b.json").write_text("{}")
            os.utime(older, ns=(1_000_000_000, 1_000_000_000))  # mtime = 1s
            os.utime(newer, ns=(5_000_000_000, 5_000_000_000))  # mtime = 5s (newest)
            before = prep_cache._dir_sig(d)
            os.utime(older, ns=(3_000_000_000, 3_000_000_000))  # 1s -> 3s, still < newest(5s)
            after = prep_cache._dir_sig(d)
            self.assertEqual(before[0], after[0], "file count must be unchanged (the trap)")
            self.assertNotEqual(before, after, "in-place edit of a non-newest file must change the sig")

    def test_course_data_sig_tracks_only_the_selected_course_authority(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            original = prep_cache._COURSEVIEW_DIR
            prep_cache._COURSEVIEW_DIR = directory
            self.addCleanup(setattr, prep_cache, "_COURSEVIEW_DIR", original)

            before = prep_cache._course_data_sig(31795)
            (directory / "31795_releases.pb").write_bytes(b"release")
            after_release = prep_cache._course_data_sig(31795)
            (directory / "31795_course_data_88_medium-plus.json").write_text("{}")
            after_map = prep_cache._course_data_sig(31795)
            (directory / "99999_course_data_1_medium-plus.json").write_text("{}")

            self.assertNotEqual(before, after_release)
            self.assertNotEqual(after_release, after_map)
            self.assertEqual(prep_cache._course_data_sig(31795), after_map)

    def test_singleflight_same_key_cold_cache_builds_once(self) -> None:
        # Thundering-herd guard: N concurrent first-requests for the SAME uncached key must
        # run the ~19s build exactly once; the late arrivals wait and read the cached result.
        prep_cache._fingerprint = lambda gid, *_: ("fp",)
        calls_lock = threading.Lock()
        calls = {"n": 0}
        build_started = threading.Event()
        let_finish = threading.Event()

        def build() -> dict:
            with calls_lock:
                calls["n"] += 1
            build_started.set()      # inflight is registered by now; signal the leader is busy
            let_finish.wait(timeout=5)  # hold the build open so the 2nd caller arrives mid-build
            return {"built": True}

        results: dict[str, object] = {}

        def call(tag: str) -> None:
            results[tag] = prep_cache.cached_course_prep(
                global_id=31794, requested=[1, 2, 3], render=True,
                include_shots=False, player_id="me", build=build,
            )

        leader = threading.Thread(target=call, args=("leader",))
        leader.start()
        self.assertTrue(build_started.wait(timeout=5), "leader build should start")
        waiter = threading.Thread(target=call, args=("waiter",))
        waiter.start()
        time.sleep(0.05)         # let the waiter reach the inflight wait (assertion holds regardless)
        let_finish.set()
        leader.join(timeout=5)
        waiter.join(timeout=5)
        self.assertFalse(leader.is_alive() or waiter.is_alive(), "no thread may deadlock")
        self.assertEqual(calls["n"], 1, "same-key concurrent first-requests must build ONCE")
        self.assertIs(results["leader"], results["waiter"], "both callers get the one cached result")

    def test_singleflight_distinct_keys_build_in_parallel(self) -> None:
        # Singleflight must NOT serialise different keys: two distinct uncached keys build
        # twice AND concurrently. A Barrier(2) inside build only clears if both builds are in
        # flight at once -> if distinct keys serialised it would time out (BrokenBarrierError).
        prep_cache._fingerprint = lambda gid, *_: ("fp",)
        calls_lock = threading.Lock()
        calls = {"n": 0}
        barrier = threading.Barrier(2, timeout=5)

        def build() -> object:
            with calls_lock:
                calls["n"] += 1
            barrier.wait()  # both threads must be in build() simultaneously to pass
            return object()

        errors: list[BaseException] = []

        def call(gid: int) -> None:
            try:
                prep_cache.cached_course_prep(
                    global_id=gid, requested=[1], render=True,
                    include_shots=False, player_id="me", build=build,
                )
            except BaseException as exc:  # BrokenBarrierError if the builds were serialised
                errors.append(exc)

        t1 = threading.Thread(target=call, args=(101,))
        t2 = threading.Thread(target=call, args=(202,))
        t1.start()
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)
        self.assertEqual(errors, [], "distinct keys must build concurrently (barrier met)")
        self.assertEqual(calls["n"], 2, "two distinct uncached keys must build twice")

    def test_lru_eviction_bounds_cache_size(self) -> None:
        # A token holder enumerating many (course/holes/render) keys must not grow the cache without
        # bound (each render=True entry embeds ~1MB of base64 hole maps). LRU caps it at _MAXSIZE.
        prep_cache._fingerprint = lambda gid, *_: ("fp",)
        for gid in range(prep_cache._MAXSIZE + 40):
            prep_cache.cached_course_prep(
                global_id=gid, requested=[1], render=True,
                include_shots=False, player_id="me", build=lambda: object(),
            )
        self.assertLessEqual(len(prep_cache._cache), prep_cache._MAXSIZE)
        # The most-recent key survives; the oldest (gid=0) was evicted.
        newest = (prep_cache._MAXSIZE + 39, (1,), True, False, "me")
        oldest = (0, (1,), True, False, "me")
        self.assertIn(newest, prep_cache._cache)
        self.assertNotIn(oldest, prep_cache._cache)


if __name__ == "__main__":
    unittest.main()
