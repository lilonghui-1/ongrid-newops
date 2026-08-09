"""本地配置文件路由 - 后端本地 YAML 配置文件管理、热重载

端点：
- GET  /files                : 获取所有本地配置文件列表
- GET  /files/{name}         : 读取指定配置文件内容
- PUT  /files/{name}         : 保存配置文件内容（写入本地 YAML 文件）
- POST /reload               : 触发配置热重载
"""

import logging
import os
import shutil
from pathlib import Path
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status

from ..core.deps import get_current_active_user, require_admin
from ..core.config_manager import AppConfigManager
from ..models.user import User
from ..schemas.local_config import (
    LocalConfigContent,
    LocalConfigFileInfo,
    LocalConfigReloadResponse,
    LocalConfigSaveRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["本地配置管理"])

# 本地配置文件定义
CONFIG_DIR = Path("/workspace/config")

LOCAL_CONFIG_FILES = {
    "config.yaml": LocalConfigFileInfo(
        name="config.yaml",
        path=str(CONFIG_DIR / "config.yaml"),
        label="主配置",
        description="LLM 配置、通知渠道、调度任务、Web 平台、告警阈值等",
        format="yaml",
    ),
    "servers.yaml": LocalConfigFileInfo(
        name="servers.yaml",
        path=str(CONFIG_DIR / "servers.yaml"),
        label="服务器配置",
        description="服务器列表、SSH 连接信息、数据库连接配置",
        format="yaml",
    ),
    "rules.yaml": LocalConfigFileInfo(
        name="rules.yaml",
        path=str(CONFIG_DIR / "rules.yaml"),
        label="自愈规则",
        description="自愈触发条件、执行操作、确认级别",
        format="yaml",
    ),
}


def _get_config_path(name: str) -> Path:
    """获取配置文件完整路径"""
    path = CONFIG_DIR / name
    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"配置文件不存在: {name}",
        )
    return path


@router.get("/files", response_model=list, summary="获取本地配置文件列表")
def list_local_config_files(
    current_user: User = Depends(get_current_active_user),
):
    """返回所有本地后端配置文件列表。

    Args:
        current_user: 当前登录用户

    Returns:
        LocalConfigFileInfo 列表
    """
    result = []
    for name, info in LOCAL_CONFIG_FILES.items():
        path = Path(info.path)
        result.append({
            "name": name,
            "path": info.path,
            "label": info.label,
            "description": info.description,
            "format": info.format,
            "exists": path.exists(),
            "size": path.stat().st_size if path.exists() else 0,
            "modified_at": datetime.fromtimestamp(
                path.stat().st_mtime
            ).isoformat() if path.exists() else None,
        })
    return result


@router.get("/files/{name}", response_model=LocalConfigContent, summary="读取配置文件内容")
def read_local_config_file(
    name: str,
    current_user: User = Depends(get_current_active_user),
):
    """读取指定本地配置文件的内容。

    Args:
        name: 文件名（config.yaml / servers.yaml / rules.yaml）
        current_user: 当前登录用户

    Returns:
        LocalConfigContent: 文件内容
    """
    if name not in LOCAL_CONFIG_FILES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"不支持的配置文件: {name}，支持: {', '.join(LOCAL_CONFIG_FILES.keys())}",
        )

    path = _get_config_path(name)
    try:
        content = path.read_text(encoding="utf-8")
        return LocalConfigContent(
            name=name,
            content=content,
            size=len(content.encode("utf-8")),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"读取配置文件失败: {e}",
        )


@router.put("/files/{name}", summary="保存配置文件内容")
def save_local_config_file(
    name: str,
    request: LocalConfigSaveRequest,
    current_user: User = Depends(require_admin),
):
    """保存配置文件内容。

    操作流程：
    1. 自动备份原文件（添加 .bak 后缀）
    2. 写入新内容
    3. 返回操作结果

    Args:
        name: 文件名
        request: 包含 content 的保存请求
        current_user: 当前登录用户（需要 admin 权限）

    Returns:
        操作结果
    """
    if name not in LOCAL_CONFIG_FILES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"不支持的配置文件: {name}，支持: {', '.join(LOCAL_CONFIG_FILES.keys())}",
        )

    path = _get_config_path(name)

    try:
        # 1. 自动备份原文件
        backup_path = path.with_suffix(f".yaml.bak.{datetime.now().strftime('%Y%m%d%H%M%S')}")
        shutil.copy2(str(path), str(backup_path))

        # 2. 写入新内容
        path.write_text(request.content, encoding="utf-8")

        logger.info(f"配置文件 {name} 已保存（备份: {backup_path.name}），操作人: {current_user.username}")

        return {
            "success": True,
            "message": f"配置文件 {name} 已保存",
            "backup": backup_path.name,
            "modified_by": current_user.username,
        }

    except Exception as e:
        logger.error(f"保存配置文件 {name} 失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"保存配置文件失败: {e}",
        )


@router.post("/reload", response_model=LocalConfigReloadResponse, summary="触发配置热重载")
def reload_config(
    current_user: User = Depends(require_admin),
):
    """触发配置热重载。

    执行流程：
    1. 重新加载所有 YAML 配置文件
    2. 重新注册所有工具
    3. 重新创建 Master Agent
    4. 重启调度器
    5. 关闭旧 SSH 连接

    Returns:
        LocalConfigReloadResponse: 重载结果
    """
    manager = AppConfigManager.get_instance()
    result = manager.reload_config()

    logger.info(f"配置热重载完成，操作人: {current_user.username}")

    return LocalConfigReloadResponse(
        success=result["success"],
        message=result["message"],
        details=result.get("details", {}),
    )