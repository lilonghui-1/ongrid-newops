"""应用服务路由 - 服务列表查看、服务重启/启停、批量操作、服务定义管理

端点：
- GET  /{host}                          : 获取服务器上的服务列表
- POST /{host}/{service}/restart        : 重启指定服务
- POST /{host}/batch-restart            : 批量重启/启停服务
- GET  /manage                          : 获取所有服务定义列表
- GET  /manage/{service_id}             : 获取单个服务定义详情
- POST /manage                          : 新增服务定义
- PUT  /manage/{service_id}             : 更新服务定义
- DELETE /manage/{service_id}           : 删除服务定义
- GET  /manage/by-server/{host}         : 获取指定服务器的服务定义列表
"""

import asyncio
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..core.deps import get_current_active_user, require_operator, require_admin
from ..database import get_db
from ..models.service import AppService
from ..models.user import User
from ..schemas.service import (
    AppServiceCreate,
    AppServiceResponse,
    AppServiceUpdate,
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


# ---------------------------------------------------------------------------
# 服务定义管理（后台维护的服务元数据 CRUD）
# ---------------------------------------------------------------------------


def _app_service_to_response(service: AppService) -> AppServiceResponse:
    """将 AppService ORM 对象转换为 AppServiceResponse schema。"""
    return AppServiceResponse(
        id=service.id,
        server_host=service.server_host,
        name=service.name,
        display_name=service.display_name or "",
        description=service.description or "",
        category=service.category,
        port=service.port,
        enabled=service.enabled,
        created_by=service.created_by or "",
        created_at=service.created_at,
        updated_at=service.updated_at,
    )


@router.get("/manage", response_model=List[AppServiceResponse], summary="获取所有服务定义")
def list_app_services(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取所有服务定义列表。

    Args:
        db: 数据库会话
        current_user: 当前登录用户

    Returns:
        AppServiceResponse 列表
    """
    services = db.query(AppService).order_by(AppService.server_host, AppService.name).all()
    return [_app_service_to_response(s) for s in services]


@router.get("/manage/by-server/{host}", response_model=List[AppServiceResponse], summary="获取指定服务器的服务定义")
def list_app_services_by_server(
    host: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取指定服务器的服务定义列表。

    Args:
        host: 服务器地址
        db: 数据库会话
        current_user: 当前登录用户

    Returns:
        AppServiceResponse 列表
    """
    services = (
        db.query(AppService)
        .filter(AppService.server_host == host)
        .order_by(AppService.name)
        .all()
    )
    return [_app_service_to_response(s) for s in services]


@router.get("/manage/{service_id}", response_model=AppServiceResponse, summary="获取服务定义详情")
def get_app_service(
    service_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取单个服务定义详情。

    Args:
        service_id: 服务定义 ID
        db: 数据库会话
        current_user: 当前登录用户

    Returns:
        AppServiceResponse
    """
    service = db.query(AppService).filter(AppService.id == service_id).first()
    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"服务定义不存在: id={service_id}",
        )
    return _app_service_to_response(service)


@router.post("/manage", response_model=AppServiceResponse, summary="新增服务定义")
def create_app_service(
    request: AppServiceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """新增服务定义。

    检查同一服务器下服务名称是否已存在，避免重复。

    Args:
        request: 新增服务定义请求
        db: 数据库会话
        current_user: 当前登录用户（需要 operator 权限）

    Returns:
        AppServiceResponse: 新创建的服务定义
    """
    # 检查是否已存在同名服务（同一服务器下）
    existing = db.query(AppService).filter(
        AppService.server_host == request.server_host,
        AppService.name == request.name,
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"服务定义已存在: server={request.server_host}, name={request.name}",
        )

    service = AppService(
        server_host=request.server_host,
        name=request.name,
        display_name=request.display_name or None,
        description=request.description or None,
        category=request.category,
        port=request.port,
        enabled=request.enabled,
        created_by=current_user.username,
    )
    db.add(service)
    db.commit()
    db.refresh(service)

    return _app_service_to_response(service)


@router.put("/manage/{service_id}", response_model=AppServiceResponse, summary="更新服务定义")
def update_app_service(
    service_id: int,
    request: AppServiceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """更新服务定义。

    仅更新请求中提供的字段，未提供的字段保持不变。

    Args:
        service_id: 服务定义 ID
        request: 更新服务定义请求（可选字段）
        db: 数据库会话
        current_user: 当前登录用户（需要 operator 权限）

    Returns:
        AppServiceResponse: 更新后的服务定义
    """
    service = db.query(AppService).filter(AppService.id == service_id).first()
    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"服务定义不存在: id={service_id}",
        )

    # 仅更新提供的字段
    update_data = request.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(service, field, value)

    db.commit()
    db.refresh(service)

    return _app_service_to_response(service)


@router.delete("/manage/{service_id}", summary="删除服务定义")
def delete_app_service(
    service_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """删除服务定义。

    仅删除数据库记录，不影响服务器上的实际服务。
    需要管理员权限。

    Args:
        service_id: 服务定义 ID
        db: 数据库会话
        current_user: 当前登录用户（需要 admin 权限）

    Returns:
        操作结果
    """
    service = db.query(AppService).filter(AppService.id == service_id).first()
    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"服务定义不存在: id={service_id}",
        )

    service_name = service.display_name or service.name
    db.delete(service)
    db.commit()

    return {
        "success": True,
        "message": f"服务定义「{service_name}」已删除",
        "service_id": service_id,
    }
