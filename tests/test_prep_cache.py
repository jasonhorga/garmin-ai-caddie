"""prep_cache: fingerprint-keyed cache for course_prep (the ~19s /courses/{id}/prep build).

Locks in: a 2nd identical request is a cache HIT (build runs once); a different player or a
changed fingerprint (new sync / regenerated geometry) forces a rebuild — so 备战 is instant while
inputs are unchanged but never serves stale prep after a sync. unittest on purpose (CI uses
`python -m unittest discover`, which ignores pytest fixtures).
"""

from __future__ import annotations

import unittest

from ai_caddie import prep_cache


class PrepCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        prep_cache.clear()
        self._orig_fingerprint = prep_cache._fingerprint

    def tearDown(self) -> None:
        prep_cache._fingerprint = self._orig_fingerprint
        prep_cache.clear()

    def test_hit_miss_on_player_and_fingerprint(self) -> None:
        calls: list[int] = []
        prep_cache._fingerprint = lambda gid: ("fp1",)

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
        prep_cache._fingerprint = lambda gid: ("fp2",)
        call()
        self.assertEqual(len(calls), 3)

        # Back to a stable fingerprint → hits again (no rebuild).
        call()
        self.assertEqual(len(calls), 3)

    def test_lru_eviction_bounds_cache_size(self) -> None:
        # A token holder enumerating many (course/holes/render) keys must not grow the cache without
        # bound (each render=True entry embeds ~1MB of base64 hole maps). LRU caps it at _MAXSIZE.
        prep_cache._fingerprint = lambda gid: ("fp",)
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
