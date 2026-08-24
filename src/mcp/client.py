"""MCP 客户端 - 基于官方 mcp SDK，读取 config/mcp.yaml 注册外部 MCP server

设计参考 ongrid 的 MCP 客户端概念（initialize → tools/list → tools/call，Streamable HTTP），
本实现基于官方 mcp Python SDK 全新编写。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from ..tools.base import BaseTool, ToolParameter, ToolResult, ToolRegistry

logger = logging.getLogger(__name__)

try:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    MCP_AVAILABLE = True
except ImportError:  # pragma: no cover - 依赖缺失时降级
    MCP_AVAILABLE = False
    ClientSession = None
    streamablehttp_client = None


class MCPServerConfig:
    """MCP server 配置"""
    name: str
    url: str
    headers: Dict[str, str] = {}
    enabled: bool = True

    def __init__(self, name: str, url: str, headers: Dict[str, str] = None, enabled: bool = True):
        self.name = name
        self.url = url
        self.headers = headers or {}
        self.enabled = enabled


def load_mcp_servers(config_path: str = "config/mcp.yaml") -> List[MCPServerConfig]:
    """从 config/mcp.yaml 加载 MCP server 列表"""
    path = Path(config_path)
    if not path.exists():
        return []
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as e:
        logger.error(f"加载 mcp.yaml 失败: {e}")
        return []
    servers = []
    for item in data.get("mcp_servers") or []:
        servers.append(MCPServerConfig(
            name=str(item.get("name") or ""),
            url=str(item.get("url") or ""),
            headers=dict(item.get("headers") or {}),
            enabled=bool(item.get("enabled", True)),
        ))
    return servers


class MCPTool(BaseTool):
    """把外部 MCP server 的一个 tool 包装为 BaseTool"""

    def __init__(self, server_name: str, tool_name: str, description: str,
                 input_schema: Dict[str, Any], session_factory):
        self.name = f"mcp_{server_name}_{tool_name}"
        self.description = f"[MCP:{server_name}] {description}"
        self._mcp_tool_name = tool_name
        self._session_factory = session_factory
        self._input_schema = input_schema or {}
        self.parameters = self._build_parameters()

    def _build_parameters(self) -> list:
        from ..tools.base import ToolParameter

        params = []
        schema = self._input_schema.get("properties") or {}
        required = set(self._input_schema.get("required") or [])
        for pname, pmeta in schema.items():
            params.append(ToolParameter(
                name=pname,
                type=str(pmeta.get("type", "string")),
                description=str(pmeta.get("description") or ""),
                required=pname in required,
            ))
        return params

    def execute(self, **kwargs) -> ToolResult:
        if not MCP_AVAILABLE:
            return ToolResult(success=False, error="mcp SDK 未安装（pip install mcp）")
        try:
            # 通过 session factory 调用 MCP tool
            args = {k: v for k, v in kwargs.items() if k in self._input_schema.get("properties", {})}
            result = self._session_factory().call_tool(self._mcp_tool_name, args)
            if isinstance(result, ToolResult):
                return result
            text = _extract_text(result)
            return ToolResult(success=True, data={"content": text})
        except Exception as e:
            return ToolResult(success=False, error=f"MCP 调用失败: {type(e).__name__}: {e}")


def _extract_text(call_result: Any) -> str:
    """从 mcp CallToolResult 提取文本内容"""
    parts = []
    content = getattr(call_result, "content", None) or []
    for block in content:
        if getattr(block, "type", "") == "text":
            parts.append(getattr(block, "text", ""))
        else:
            parts.append(f"[{getattr(block, 'type', 'block')}]")
    return "\n".join(parts)


class MCPClientSession:
    """MCP 客户端会话包装（初始化 + list_tools + call_tool）

    每次调用在独立 anyio 事件循环中完成 open → 操作 → close。
    """

    def __init__(self, url: str, headers: Dict[str, str], timeout: float = 30.0):
        self.url = url
        self.headers = headers
        self.timeout = timeout

    def list_tools(self) -> List[Dict[str, Any]]:
        if not MCP_AVAILABLE:
            return []
        import anyio
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        async def _list():
            async with streamablehttp_client(self.url, headers=self.headers, timeout=self.timeout) as stack:
                async with ClientSession(stack) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    return [{"name": t.name, "description": t.description, "inputSchema": t.inputSchema} for t in tools.tools]

        return anyio.run(_list)

    def call_tool(self, name: str, args: Dict[str, Any]):
        if not MCP_AVAILABLE:
            raise RuntimeError("mcp SDK 未安装")
        import anyio
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        async def _call():
            async with streamablehttp_client(self.url, headers=self.headers, timeout=self.timeout) as stack:
                async with ClientSession(stack) as session:
                    await session.initialize()
                    return await session.call_tool(name, args)

        return anyio.run(_call)


class MCPRegistry:
    """MCP server 注册表：管理多个 MCP server 的会话与工具"""

    def __init__(self, servers: List[MCPServerConfig]):
        self._servers = servers
        self._tools: List[BaseTool] = []

    def register_tools(self) -> List[BaseTool]:
        """连接各 server 并注册其 tools"""
        for server in self._servers:
            if not server.enabled or not server.url:
                continue
            try:
                client = MCPClientSession(server.url, server.headers)
                tools_meta = client.list_tools()
                for meta in tools_meta:
                    tool = MCPServerTool(
                        server_name=server.name,
                        tool_name=meta["name"],
                        description=meta["description"],
                        input_schema=meta.get("inputSchema") or {},
                        url=server.url,
                        headers=server.headers,
                    )
                    self._tools.append(tool)
                    ToolRegistry.register(tool)
                    logger.info(f"MCP 工具注册: {tool.name}")
            except Exception as e:
                logger.error(f"MCP server [{server.name}] 注册失败: {e}")
        return self._tools


class MCPServerTool(BaseTool):
    """包装远程 MCP tool 的 BaseTool（每次调用建立短会话）"""

    def __init__(self, server_name: str, tool_name: str, description: str,
                 input_schema: Dict[str, Any], url: str, headers: Dict[str, str]):
        self.name = f"mcp_{server_name}_{tool_name}"
        self.description = f"[MCP:{server_name}] {description}"
        self._mcp_tool_name = tool_name
        self._url = url
        self._headers = headers
        self._input_schema = input_schema or {}
        self.parameters = self._build_parameters(self._input_schema)

    def _build_parameters(self, schema: Dict[str, Any]) -> list:
        from ..tools.base import ToolParameter

        params = []
        for pname, pmeta in (schema.get("properties") or {}).items():
            params.append(ToolParameter(
                name=pname,
                type=str(pmeta.get("type", "string")),
                description=str(pmeta.get("description") or ""),
                required=pname in (schema.get("required") or []),
            ))
        return params

    def execute(self, **kwargs) -> ToolResult:
        if not MCP_AVAILABLE:
            return ToolResult(success=False, error="mcp SDK 未安装")
        try:
            import anyio
            from mcp import ClientSession
            from mcp.client.streamable_http import streamablehttp_client

            # 仅传参 schema 中声明的参数，避免多余参数污染远端
            allowed = set((self._input_schema or {}).get("properties", {}).keys())
            args = {k: v for k, v in kwargs.items() if k in allowed}

            async def _run():
                async with streamablehttp_client(self._url, headers=self._headers, timeout=30) as stack:
                    async with ClientSession(stack) as session:
                        await session.initialize()
                        result = await session.call_tool(self._mcp_tool_name, args)
                        return _extract_text(result)

            text = anyio.run(_run)
            return ToolResult(success=True, data={"content": text})
        except Exception as e:
            return ToolResult(success=False, error=f"MCP 调用失败: {type(e).__name__}: {e}")


def register_mcp_tools(config_path: str = "config/mcp.yaml") -> None:
    """注册 config/mcp.yaml 中所有 MCP server 的工具到 ToolRegistry"""
    servers = load_mcp_servers(config_path)
    if not servers:
        return
    registry = MCPRegistry(servers)
    registry.register_tools()