from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ai_caddie.connectors.sync_lock import SyncInProgress, acquire_sync_lock, sync_lock_path


class SyncLockTests(unittest.TestCase):
    def test_lock_is_shared_by_nested_acquisition_and_released_after_context(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with acquire_sync_lock(root):
                self.assertTrue(sync_lock_path(root).exists())
                with self.assertRaises(SyncInProgress):
                    with acquire_sync_lock(root):
                        pass
            with acquire_sync_lock(root):
                pass


if __name__ == "__main__":
    unittest.main()
