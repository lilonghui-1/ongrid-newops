"""可观测性工具 - Prometheus (PromQL) / Loki (LogQL) / Grafana 转跳

设计参考 ongrid 可观测性客户端概念（promquery/logquery/grafana）：
查询结果保留原始 JSON 形状直回 LLM，支持 8MiB 上限截断。
本实现基于 httpx 全新编写。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx

from .base import BaseTool, ToolResult, ToolParameter

logger = logging.getLogger(__name__)

MAX_BODY = 8 * 1024 * 1024  # 8MiB


class PrometheusQueryTool(BaseTool):
    """Prometheus 查询工具（PromQL）"""

    name = "query_promql"
    description = "查询 Prometheus 指标（PromQL 即时查询与区间查询），返回原始 JSON"
    parameters = [
        ToolParameter(name="expr", type="string", description="PromQL 表达式，如 up{job='node'}"),
        ToolParameter(
            name="range",
            type="string",
            description="区间（可选）：如 1h/6h/24h；不填为即时查询",
            required=False,
            default=""
        ),
        ToolParameter(
            name="step",
            type="string",
            description="区间步长（可选）：如 60s/5m（默认 60s）",
            required=False,
            default="60s",
        ),
    ]

    def __init__(self, config=None):
        self._base_url = None
        if config and hasattr(config, "observability"):
            obs = config.observability
            self._base_url = (obs.prometheus_url if obs else None) or None
        if not self._base_url:
            import os
            self._base_url = os.environ.get("PROMETHEUS_URL")

    def _parse_range(self, rng: str) -> Optional[timedelta]:
        if not rng:
            return None
        unit = rng[-1]
        try:
            num = int(rng[:-1])
        except ValueError:
            return None
        mapping = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
        return timedelta(seconds=num * mapping.get(unit, 60))

    def _query_instant(self, expr: str) -> httpx.Response:
        import httpx
        return httpx.get(
            f"{self._base_url}/api/v1/query",
            params={"query": expr},
            timeout=30,
        )

    def _query_range(self, expr: str, td: timedelta, step: str) -> httpx.Response:
        import httpx

        end = datetime.now()
        start = end - td
        return httpx.get(
            f"{self._base_url}/api/v1/query_range",
            params={
                "query": expr,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "step": step,
            },
            timeout=30,
        )

    def execute(self, **kwargs) -> ToolResult:
        if not self._base_url:
            return ToolResult(success=False, error="Prometheus 未配置（config observability.prometheus_url 或 PROMETHEUS_URL）")
        expr = kwargs["expr"]
        rng = kwargs.get("range", "")
        step = kwargs.get("step", "60s")
        try:
            td = self._parse_range(rng)
            if td:
                resp = self._query_range(expr, td, step)
            else:
                resp = self._query_instant(expr)
            body = resp.content[:MAX_BODY].decode("utf-8", errors="replace")
            try:
                data = resp.json()
                success = resp.status_code == 200 and data.get("status") == "success"
                return ToolResult(
                    success=success,
                    data=data,
                    metadata={"status_code": resp.status_code, "range": rng, "step": step},
                )
            except ValueError:
                return ToolResult(success=False, error=f"Prometheus 返回非 JSON: {body[:500]}")
        except Exception as e:
            return ToolResult(success=False, error=f"Prometheus 查询失败: {type(e).__name__}: {e}")


class LokiQueryTool(BaseTool):
    """Loki 查询工具（LogQL）"""

    name = "query_logql"
    description = "查询 Loki 日志（LogQL 区间查询与标签查询，返回原始 JSON）"
    parameters = [
        ToolParameter(name="query", type="string", description="LogQL 表达式，如 {app='nginx'} |= 'error'"),
        ToolParameter(
            name="range",
            type="string",
            description="时间范围（默认 1h）",
            required=False,
            default="1h",
        ),
        ToolParameter(
            name="limit",
            type="integer",
            description="返回条数上限（默认 200）",
            required=False,
            default=200,
        ),
    ]

    def __init__(self, config=None):
        self._base_url = None
        if config and hasattr(config, "observability"):
            obs = config.observability
            self._base_url = (obs.loki_url or None) if obs else None
        if not self._base_url:
            import os
            self._base_url = os.environ.get("LOKI_URL")

    def execute(self, **kwargs) -> ToolResult:
        import httpx

        if not self._base_url:
            return ToolResult(success=False, error="Loki 未配置（observability.loki_url 或 LOKI_URL）")
        query = kwargs["query"]
        rng = kwargs.get("range", "1h")
        limit = int(kwargs.get("limit", 200))
        try:
            td = timedelta(seconds=int(rng[:-1]) * {"s": 1, "m": 60, "h": 3600, "d": 86400}.get(rng[-1], 60))
            end = datetime.now()
            start = end - td
            resp = httpx.get(
                f"{self._base_url}/loki/api/v1/query_range",
                params={
                    "query": query,
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "limit": limit,
                    "direction": "backward",
                },
                timeout=30,
            )
            data = resp.json()
            return ToolResult(
                success=resp.status_code == 200,
                data=data,
                metadata={"status_code": resp.status_code, "range": rng, "limit": limit},
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Loki 查询失败: {type(e).__name__}: {e}")


class GrafanaTool(BaseTool):
    """Grafana 工具 - 健康检查与 dashboard 转跳链接生成"""

    name = "grafana_dashboard"
    description = "获取 Grafana dashboard 转跳链接（按名称搜索 uid）"
    parameters = [
        ToolParameter(name="dashboard", type="string", description="dashboard 名称关键词"),
    ]

    def __init__(self, config=None):
        self._base_url = None
        if config and hasattr(config, "observability"):
            obs = config.observability
            self._base_url = (obs.grafana_url or None) if obs else None
        if not self._base_url:
            import os
            self._base_url = os.environ.get("GRAFANA_URL")

    def execute(self, **kwargs) -> ToolResult:
        import httpx

        if not self._base_url:
            return ToolResult(success=False, error="Grafana 未配置（observability.grafana_url 或 GRAFANA_URL）")
        name = kwargs["dashboard"]
        try:
            resp = httpx.get(
                f"{self._base_url}/api/search",
                params={"query": name, "type": "dash-db"},
                timeout=20,
            )
            hits = resp.json()
            results = [
                {"title": h.get("title"), "url": f"{self._base_url}{h.get('url', '')}"}
                for h in hits[:5]
            ]
            return ToolResult(
                success=resp.status_code == 200,
                data={"dashboard": name, "hits": results},
                metadata={"status_code": resp.status_code},
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Grafana 查询失败: {type(e).__name__}: {e}")


def register_observability_tools(config=None) -> None:
    """注册可观测性三件套"""
    from .base import ToolRegistry

    ToolRegistry.register(PrometheusQueryTool(config))
    ToolRegistry.register(LokiQueryTool(config))
    ToolRegistry.register(GrafanaTool(config))