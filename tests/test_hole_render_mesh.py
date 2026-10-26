"""Decoded mesh reuse must not hide downloads or cross fixture/data roots."""
from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ai_caddie.geometry import hole_render


def mesh(east: int) -> dict:
    return {'meshes': [{'name': 'Green.drc', 'positions': [[east, 0, 300]]}]}


class MeshLoadCacheTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'mesh.json'
        hole_render._load_mesh_cached.cache_clear()
        self.addCleanup(hole_render._load_mesh_cached.cache_clear)

    def test_reuses_file_read_and_decoded_mesh(self) -> None:
        self.path.write_text(json.dumps(mesh(1)))
        with patch.object(hole_render, 'mesh_path', return_value=self.path), \
                patch.object(Path, 'read_text', autospec=True, side_effect=Path.read_text) as read:
            first = hole_render.load_mesh(900001, 1)
            second = hole_render.load_mesh(900001, 1)
        self.assertEqual(first, second)
        self.assertEqual(second[1]['Green.drc']['positions'], [[1, 0, 300]])
        read.assert_called_once_with(self.path)

    def test_mtime_change_invalidates_even_when_size_is_unchanged(self) -> None:
        self.path.write_text(json.dumps(mesh(1)))
        original = self.path.stat()
        with patch.object(hole_render, 'mesh_path', return_value=self.path):
            hole_render.load_mesh(900001, 1)
            self.path.write_text(json.dumps(mesh(2)))
            self.assertEqual(self.path.stat().st_size, original.st_size)
            os.utime(self.path, ns=(original.st_atime_ns, original.st_mtime_ns + 1))
            _md, by = hole_render.load_mesh(900001, 1)
        self.assertEqual(by['Green.drc']['positions'], [[2, 0, 300]])

    def test_size_change_invalidates_even_when_mtime_is_unchanged(self) -> None:
        self.path.write_text(json.dumps(mesh(1)))
        original = self.path.stat()
        with patch.object(hole_render, 'mesh_path', return_value=self.path):
            hole_render.load_mesh(900001, 1)
            self.path.write_text(json.dumps(mesh(200)))
            os.utime(self.path, ns=(original.st_atime_ns, original.st_mtime_ns))
            _md, by = hole_render.load_mesh(900001, 1)
        self.assertEqual(by['Green.drc']['positions'], [[200, 0, 300]])

    def test_same_hole_in_another_root_does_not_reuse_the_first_mesh(self) -> None:
        other = self.path.with_name('other.json')
        self.path.write_text(json.dumps(mesh(1)))
        other.write_text(json.dumps(mesh(2)))
        original = self.path.stat()
        os.utime(other, ns=(original.st_atime_ns, original.st_mtime_ns))
        self.assertEqual(other.stat().st_size, original.st_size)
        with patch.object(hole_render, 'mesh_path', side_effect=[self.path, other]):
            first = hole_render.load_mesh(900001, 1)
            second = hole_render.load_mesh(900001, 1)
        self.assertEqual(first[1]['Green.drc']['positions'], [[1, 0, 300]])
        self.assertEqual(second[1]['Green.drc']['positions'], [[2, 0, 300]])

    def test_removed_file_is_not_served_from_cache(self) -> None:
        self.path.write_text(json.dumps(mesh(1)))
        with patch.object(hole_render, 'mesh_path', return_value=self.path):
            hole_render.load_mesh(900001, 1)
            self.path.unlink()
            with self.assertRaises(FileNotFoundError):
                hole_render.load_mesh(900001, 1)
