"""「打开即用」prepare-recent 端点:fire-and-forget + member-scoped 路由分类。"""
from __future__ import annotations

import unittest
from unittest import mock

from fastapi.testclient import TestClient

from server_v2.main import app
from server_v2.players_api import is_player_scoped_route


class PrepareRecentApiTests(unittest.TestCase):
    def test_route_is_player_scoped(self):
        # 无 target-player、写调用者自己缓存 → member-scoped(过路由护栏)。
        self.assertTrue(is_player_scoped_route("POST", "/api/v2/history/prepare-recent"))

    def test_endpoint_returns_queued_shape_and_fires_background(self):
        # 后台重活(load history + 渲 topo + 烤统计)mock 掉:只验端点契约 + 触发了后台。
        with mock.patch("server_v2.main._prepare_recent_bg") as bg:
            client = TestClient(app)
            resp = client.post("/api/v2/history/prepare-recent")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["schema"], "ai-caddie-prepare-recent-v1")
        self.assertTrue(body["queued"])
        bg.assert_called_once()  # 后台任务已注册并跑(mock 成 no-op)


if __name__ == "__main__":
    unittest.main()
