"""应用服务路由 - 服务列表查看、服务重启/启停、批量操作

端点：
- GET  /{host}                  : 获取服务器上的服务列表
- POST /{host}/{service}/restart: 重启指定服务
- POST /{host}/batch-restart    : 批量重启/启停服务
"""

import asyncio
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..core.deps import get_current_active_user, require_operator
from ..database import get_db
from ..models.user import User
from ..schemas.service import (
    BatchServiceOperationRequest,
    ServiceInfo,
    ServiceListResponse,
)
from ...tools.base import ToolRegistry

logger = logging.getLogger(__name__)

router = APIRouter(tags=["应用服务"])


def _parse_systemctl_services(output: str) -> List[ServiceInfo]:
    """解析 systemctl list-units --type=service 的输出。

    输出示例::

        UNIT                       LOAD   ACTIVE SUB     DESCRIPTION
        nginx.service              loaded active running A high performance web server
        ...

    Args:
        output: systemctl 命令输出文本

    Returns:
        ServiceInfo 列表
    """
    services: List[ServiceInfo] = []
    lines = output.strip().split("\n")

    for line in lines:
        line = line.strip()
        if not line or line.startswith("UNIT") or line.startswith("LOAD"):
            continue
        if line.startswith("●"):
            line = line[1:].strip()

        parts = line.split()
        if len(parts) < 4:
            continue

        unit_name = parts[0]
        active_state = parts[2]  # active / inactive / failed
        sub_state = parts[3]     # running / dead / exited

        # 仅处理 .service 结尾的单元
        if not unit_name.endswith(".service"):
            continue

        service_name = unit_name.replace(".service", "")
        status_str = f"{active_state} ({sub_state})" if active_state != sub_state else active_state

        services.append(ServiceInfo(
            name=service_name,
            status=status_str,
        ))

    return services


@router.get("/{host}", response_model=ServiceListResponse, summary="获取服务列表")
async def list_services(
    host: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取指定服务器上的系统服务列表。

    通过 SSH 执行 ``systemctl list-units --type=service`` 获取服务列表。

    Args:
        host: 服务器地址
        db: 数据库会话
        current_user: 当前登录用户

    Returns:
        ServiceListResponse: 服务列表
    """
    ssh_tool = ToolRegistry.get("ssh_execute")
    if not ssh_tool:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SSH 工具未注册",
        )

    command = "systemctl list-units --type=service --no-pager --no-legend"
    result = await asyncio.to_thread(
        ssh_tool.execute_with_logging, host=host, command=command, timeout=30
    )

    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"获取服务列表失败: {result.error}",
        )

    stdout = result.data.get("stdout", "") if result.data else ""
    services = _parse_systemctl_services(stdout)

    return ServiceListResponse(host=host, services=services)


@router.post("/{host}/{service}/restart", summary="重启指定服务")
async def restart_service(
    host: str,
    service: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """重启指定服务器上的某个服务。

    调用 ToolRegistry 中注册的 service_control 工具执行重启操作。

    Args:
        host: 服务器地址
        service: 服务名称
        db: 数据库会话
        current_user: 当前登录用户（需要 operator 权限）

    Returns:
        操作结果
    """
    tool = ToolRegistry.get("service_control")
    if not tool:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="服务管理工具未注册",
        )

    result = await asyncio.to_thread(
        tool.execute_with_logging,
        host=host,
        service_name=service,
        action="restart",
    )

    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"重启服务 {service} 失败: {result.error}",
        )

    return {
        "success": True,
        "message": f"服务 {service} 已重启",
        "detail": result.data,
    }


@router.post("/{host}/{service}/start", summary="启动指定服务")
async def start_service(
    host: str,
    service: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """启动指定服务器上的某个服务。

    Args:
        host: 服务器地址
        service: 服务名称
        db: 数据库会话
        current_user: 当前登录用户（需要 operator 权限）

    Returns:
        操作结果
    """
    tool = ToolRegistry.get("service_control")
    if not tool:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="服务管理工具未注册",
        )

    result = await asyncio.to_thread(
        tool.execute_with_logging,
        host=host,
        service_name=service,
        action="start",
    )

    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"启动服务 {service} 失败: {result.error}",
        )

    return {
        "success": True,
        "message": f"服务 {service} 已启动",
        "detail": result.data,
    }


@router.post("/{host}/{service}/stop", summary="停止指定服务")
async def stop_service(
    host: str,
    service: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """停止指定服务器上的某个服务。

    Args:
        host: 服务器地址
        service: 服务名称
        db: 数据库会话
        current_user: 当前登录用户（需要 operator 权限）

    Returns:
        操作结果
    """
    tool = ToolRegistry.get("service_control")
    if not tool:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="服务管理工具未注册",
        )

    result = await asyncio.to_thread(
        tool.execute_with_logging,
        host=host,
        service_name=service,
        action="stop",
    )

    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"停止服务 {service} 失败: {result.error}",
        )

    return {
        "success": True,
        "message": f"服务 {service} 已停止",
        "detail": result.data,
    }


@router.post("/{host}/batch-restart", summary="批量操作服务")
async def batch_restart_services(
    host: str,
    request: BatchServiceOperationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """批量对多个服务执行启动/停止/重启操作。

    Args:
        host: 服务器地址
        request: 包含 service_names 和 action 的批量操作请求
        db: 数据库会话
        current_user: 当前登录用户（需要 operator 权限）

    Returns:
        每个服务的操作结果
    """
    tool = ToolRegistry.get("service_control")
    if not tool:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="服务管理工具未注册",
        )

    valid_actions = ("start", "stop", "restart")
    if request.action not in valid_actions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的操作: {request.action}，允许: {', '.join(valid_actions)}",
        )

    results = []
    for service_name in request.service_names:
        result = await asyncio.to_thread(
            tool.execute_with_logging,
            host=host,
            service_name=service_name,
            action=request.action,
        )
        results.append({
            "service": service_name,
            "success": result.success,
            "error": result.error,
            "detail": result.data if result.success else None,
        })

    success_count = sum(1 for r in results if r["success"])
    return {
        "host": host,
        "action": request.action,
        "total": len(results),
        "success_count": success_count,
        "results": results,
    }
