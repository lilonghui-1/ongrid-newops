"""配置文件路由 - 配置文件列表、读取、保存（带备份）、回滚、历史

端点：
- GET  /{host}/list             : 返回预定义的配置文件路径列表
- GET  /{host}/read             : 通过 SSH 读取配置文件内容
- POST /{host}/save             : 保存配置文件（先备份原内容，再写入新内容）
- POST /{host}/rollback/{backup_id}: 回滚到指定备份版本
- GET  /{host}/history          : 查询配置文件修改历史
"""

import asyncio
import base64
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..core.deps import get_current_active_user, require_operator
from ..database import get_db
from ..models.config_backup import ConfigBackup
from ..models.user import User
from ..schemas.config_file import (
    ConfigBackupInfo,
    ConfigFileContent,
    ConfigFileInfo,
    ConfigSaveRequest,
)
from ...tools.base import ToolRegistry

logger = logging.getLogger(__name__)

router = APIRouter(tags=["配置文件管理"])

# ---------------------------------------------------------------------------
# 预定义配置文件列表
# ---------------------------------------------------------------------------
PREDEFINED_CONFIGS: List[ConfigFileInfo] = [
    ConfigFileInfo(path="/etc/nginx/nginx.conf", name="nginx.conf", format="conf"),
    ConfigFileInfo(path="/etc/my.cnf", name="my.cnf", format="conf"),
    ConfigFileInfo(path="/etc/redis/redis.conf", name="redis.conf", format="conf"),
    ConfigFileInfo(path="/opt/app/application.yml", name="application.yml", format="yml"),
    ConfigFileInfo(path="/opt/app/application.yaml", name="application.yaml", format="yml"),
    ConfigFileInfo(path="/opt/app/application.properties", name="application.properties", format="properties"),
    ConfigFileInfo(path="/etc/sysctl.conf", name="sysctl.conf", format="conf"),
    ConfigFileInfo(path="/etc/ssh/sshd_config", name="sshd_config", format="conf"),
    ConfigFileInfo(path="/etc/fstab", name="fstab", format="conf"),
    ConfigFileInfo(path="/etc/hosts", name="hosts", format="conf"),
    ConfigFileInfo(path="/etc/environment", name="environment", format="conf"),
    ConfigFileInfo(path="/etc/crontab", name="crontab", format="conf"),
    ConfigFileInfo(path="/etc/rsyslog.conf", name="rsyslog.conf", format="conf"),
]


def _detect_format(file_path: str) -> str:
    """根据文件扩展名推断配置文件格式。"""
    if "." not in file_path:
        return "conf"
    ext = file_path.rsplit(".", 1)[-1].lower()
    format_map = {
        "yml": "yml",
        "yaml": "yml",
        "json": "json",
        "conf": "conf",
        "cfg": "conf",
        "properties": "properties",
        "ini": "conf",
        "xml": "xml",
    }
    return format_map.get(ext, "conf")


def _build_backup_info(backup: ConfigBackup) -> ConfigBackupInfo:
    """将 ConfigBackup ORM 对象转换为 ConfigBackupInfo schema。"""
    version_val = 0
    try:
        version_val = int(backup.version)
    except (ValueError, TypeError):
        version_val = 0

    return ConfigBackupInfo(
        id=backup.id,
        server_host=backup.server_host,
        file_path=backup.file_path,
        version=version_val,
        modified_by=backup.modified_by or "",
        modified_at=backup.modified_at,
        is_rolled_back=backup.is_rolled_back,
    )


@router.get("/{host}/list", response_model=List[ConfigFileInfo], summary="获取配置文件列表")
def list_config_files(
    host: str,
    current_user: User = Depends(get_current_active_user),
):
    """返回预定义的配置文件路径列表。

    Args:
        host: 服务器地址
        current_user: 当前登录用户

    Returns:
        ConfigFileInfo 列表
    """
    return PREDEFINED_CONFIGS


@router.get("/{host}/read", response_model=ConfigFileContent, summary="读取配置文件内容")
async def read_config_file(
    host: str,
    file_path: str = Query(..., description="配置文件路径"),
    current_user: User = Depends(get_current_active_user),
):
    """通过 SSH cat 命令读取服务器上的配置文件内容。

    Args:
        host: 服务器地址
        file_path: 配置文件路径
        current_user: 当前登录用户

    Returns:
        ConfigFileContent: 文件内容
    """
    ssh_tool = ToolRegistry.get("ssh_execute")
    if not ssh_tool:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SSH 工具未注册",
        )

    command = f"cat '{file_path}'"
    result = await asyncio.to_thread(
        ssh_tool.execute_with_logging,
        host=host,
        command=command,
        timeout=15,
    )

    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"读取配置文件失败: {result.error}",
        )

    content = (result.data or {}).get("stdout", "")
    file_format = _detect_format(file_path)

    return ConfigFileContent(
        path=file_path,
        content=content,
        format=file_format,
        size=len(content.encode("utf-8")),
    )


@router.post("/{host}/save", response_model=ConfigBackupInfo, summary="保存配置文件")
async def save_config_file(
    host: str,
    request: ConfigSaveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """保存配置文件内容。

    操作流程：
    1. 通过 SSH 读取当前文件原始内容
    2. 将原始内容存入 ConfigBackup 表作为备份
    3. 通过 SSH 写入新内容（使用 base64 编码安全传输）
    4. 返回备份信息

    Args:
        host: 服务器地址
        request: 包含 file_path 和 content 的保存请求
        db: 数据库会话
        current_user: 当前登录用户（需要 operator 权限）

    Returns:
        ConfigBackupInfo: 备份信息
    """
    ssh_tool = ToolRegistry.get("ssh_execute")
    if not ssh_tool:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SSH 工具未注册",
        )

    # 1. 读取当前文件原始内容
    read_command = f"cat '{request.file_path}'"
    read_result = await asyncio.to_thread(
        ssh_tool.execute_with_logging,
        host=host,
        command=read_command,
        timeout=15,
    )

    original_content = ""
    if read_result.success and read_result.data:
        original_content = read_result.data.get("stdout", "")

    # 2. 创建备份记录
    existing_count = (
        db.query(ConfigBackup)
        .filter(
            ConfigBackup.server_host == host,
            ConfigBackup.file_path == request.file_path,
        )
        .count()
    )
    version = str(existing_count + 1)

    backup = ConfigBackup(
        server_host=host,
        file_path=request.file_path,
        original_content=original_content,
        new_content=request.content,
        backup_content=original_content,
        version=version,
        modified_by=current_user.username,
    )
    db.add(backup)
    db.commit()
    db.refresh(backup)

    # 3. 写入新内容（base64 编码安全传输）
    encoded = base64.b64encode(request.content.encode("utf-8")).decode("ascii")
    write_command = f"echo '{encoded}' | base64 -d > '{request.file_path}'"
    write_result = await asyncio.to_thread(
        ssh_tool.execute_with_logging,
        host=host,
        command=write_command,
        timeout=15,
    )

    if not write_result.success:
        logger.warning(f"写入配置文件失败: {write_result.error}")
        # 写入失败不删除备份，以便排查

    return _build_backup_info(backup)


@router.post("/{host}/rollback/{backup_id}", summary="回滚配置文件")
async def rollback_config(
    host: str,
    backup_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """回滚配置文件到指定备份版本。

    从 ConfigBackup 表读取备份的原始内容，重新写入服务器。

    Args:
        host: 服务器地址
        backup_id: 备份 ID
        db: 数据库会话
        current_user: 当前登录用户（需要 operator 权限）

    Returns:
        操作结果
    """
    backup = db.query(ConfigBackup).filter(
        ConfigBackup.id == backup_id,
        ConfigBackup.server_host == host,
    ).first()

    if not backup:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"备份记录不存在: id={backup_id}, host={host}",
        )

    # 获取要恢复的内容（优先使用 backup_content，其次 original_content）
    restore_content = backup.backup_content or backup.original_content or ""
    if not restore_content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="备份内容为空，无法回滚",
        )

    ssh_tool = ToolRegistry.get("ssh_execute")
    if not ssh_tool:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SSH 工具未注册",
        )

    # 写入备份内容到服务器
    encoded = base64.b64encode(restore_content.encode("utf-8")).decode("ascii")
    write_command = f"echo '{encoded}' | base64 -d > '{backup.file_path}'"
    write_result = await asyncio.to_thread(
        ssh_tool.execute_with_logging,
        host=host,
        command=write_command,
        timeout=15,
    )

    if not write_result.success:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"回滚写入失败: {write_result.error}",
        )

    # 标记为已回滚
    backup.is_rolled_back = True
    db.commit()

    return {
        "success": True,
        "message": f"配置文件 {backup.file_path} 已回滚到版本 {backup.version}",
        "backup_id": backup_id,
        "file_path": backup.file_path,
        "version": backup.version,
    }


@router.get("/{host}/history", response_model=List[ConfigBackupInfo], summary="查询修改历史")
def get_config_history(
    host: str,
    file_path: str = Query(None, description="配置文件路径（可选筛选）"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """查询配置文件的修改历史。

    Args:
        host: 服务器地址
        file_path: 配置文件路径（可选，不指定则返回该服务器所有记录）
        db: 数据库会话
        current_user: 当前登录用户

    Returns:
        ConfigBackupInfo 列表
    """
    query = db.query(ConfigBackup).filter(ConfigBackup.server_host == host)

    if file_path:
        query = query.filter(ConfigBackup.file_path == file_path)

    backups = query.order_by(ConfigBackup.modified_at.desc()).all()

    return [_build_backup_info(b) for b in backups]
