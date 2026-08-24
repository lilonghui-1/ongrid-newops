"""可观测性工具测试 - Prometheus/Loki/Grafana（mock 外部 HTTP）"""

import pytest
from unittest.mock import MagicMock, patch

from src.tools.observability_tools import (
    PrometheusQueryTool,
    LokiQueryTool,
    GrafanaTool,
)
from src.tools.base import ToolRegistry


class TestPrometheusQueryTool:
    """Prometheus 查询工具测试"""

    def setup_method(self):
        ToolRegistry.clear()

    def _make_config(self):
        config = MagicMock()
        obs = MagicMock()
        obs.prometheus_url = "http://prometheus:9090"
        obs.loki_url = "http://loki:3100"
        obs.grafana_url = "http://grafana:3000"
        config.observability = obs
        return config

    def test_instant_query_success(self):
        tool = PrometheusQueryTool(self._make_config())
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "success", "data": {"result": []}}
        mock_resp.content = b'{"status":"success"}'
        with patch("httpx.get", return_value=mock_resp) as mock_get:
            result = tool.execute(expr="up")
            assert result.success
            assert result.data["status"] == "success"
            mock_get.assert_called_once()

    def test_missing_config(self):
        tool = PrometheusQueryTool(config=None)
        with patch.dict("os.environ", {}, clear=True):
            result = tool.execute(expr="up")
            assert not result.success
            assert "未配置" in result.error

    def test_range_query(self):
        tool = PrometheusQueryTool(self._make_config())
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "success", "data": {"resultType": "matrix"}}
        mock_resp.content = b'{"status":"success"}'
        with patch("httpx.get", return_value=mock_resp) as mock_get:
            result = tool.execute(expr="up", range="1h", step="60s")
            assert result.success
            # 区间查询应调用 query_range
            assert "/query_range" in mock_get.call_args[0][0]


class TestLokiQueryTool:
    """Loki 查询工具"""

    def _make_config(self):
        config = MagicMock()
        obs = MagicMock()
        obs.prometheus_url = "http://prometheus:9090"
        obs.loki_url = "http://loki:3100"
        obs.grafana_url = "http://grafana:3000"
        config.observability = obs
        return config

    def test_loki_query_success(self):
        tool = LokiQueryTool(self._make_config())
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "success", "data": {"result": []}}
        with patch("httpx.get", return_value=mock_resp) as mock_get:
            result = tool.execute(query="{app='nginx'}")
            assert result.success
            assert "/loki/api/v1/query_range" in mock_get.call_args[0][0]

    def test_loki_query_no_config(self):
        tool = LokiQueryTool(None)
        result = tool.execute(query="{app='nginx'}")
        assert not result.success


class TestGrafanaTool:
    """Grafana 工具测试"""

    def _make_config(self):
        config = MagicMock()
        obs = MagicMock()
        obs.prometheus_url = "http://prometheus:9090"
        obs.loki_url = "http://loki:3100"
        obs.grafana_url = "http://grafana:3000"
        config.observability = obs
        return config

    def test_grafana_search_success(self):
        tool = GrafanaTool(self._make_config())
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"title": "Node Exporter", "url": "/d/abc123/node-exporter"}
        ]
        with patch("httpx.get", return_value=mock_resp):
            result = tool.execute(dashboard="node")
            assert result.success
            assert len(result.data["hits"]) == 1
            assert result.data["hits"][0]["url"].startswith("http://grafana:3000")

    def test_grafana_unconfigured(self):
        tool = GrafanaTool(None)
        result = tool.execute(dashboard="node")
        assert not result.success