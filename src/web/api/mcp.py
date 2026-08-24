"""MCP 服务器管理路由 - 查看已注册 MCP 工具、执行 MCP 工具

端点：
- GET  /        : MCP server 与工具清单
- POST /call    : 调用 MCP 工具（按注册名 mcp_{server}_{tool}）
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..core.deps import get_current_active_user, require_operator
from ..models.user import User
from ...mcp import load_mcp_servers
from ...tools.base import ToolRegistry

logger = logging.getLogger(__name__)

router = APIRouter(tags=["MCP 工具"])


@router.get("/", summary="MCP 工具清单")
def list_mcp_tools(
    current_user: User = Depends(get_current_active_user),
):
    """返回已配置的 MCP server 与已注册的 MCP 工具"""
    servers = load_mcp_servers()
    server_names = [s.name for s in servers if s.enabled]

    mcp_tools = []
    for name, tool in ToolRegistry.get_all().items():
        if name.startswith("mcp_"):
            mcp_tools.append({
                "name": name,
                "description": tool.description,
                "parameters": [
                    {"name": p.name, "type": p.type, "required": p.required}
                    for p in tool.parameters
                ],
            })

    return {
        "servers": server_names,
        "total": len(mcp_tools),
        "tools": mcp_tools,
    }


@router.post("/call", summary="调用 MCP 工具")
def call_mcp_tool(
    request: dict,
    current_user: User = Depends(require_operator),
):
    """调用已注册的 MCP 工具

    Body:
        {"tool": "mcp_server_tool", "args": {...}}
    """
    tool_name = request.get("tool")
    if not tool_name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="缺少 tool 参数")
    if not tool_name.startswith("mcp_"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="工具名必须以 mcp_ 开头")

    tool = ToolRegistry.get(tool_name)
    if not tool:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"MCP 工具未注册: {tool_name}")

    args = request.get("args") or {}
    result = tool.execute(**args)
    logger.info(f"MCP 工具调用: {tool_name} by {current_user.username}, success={result.success}")
    return {
        "success": result.success,
        "tool": tool_name,
        "data": result.data,
        "error": result.error,
        "metadata": result.metadata,
    }