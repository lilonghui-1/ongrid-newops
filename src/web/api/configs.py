"""配置文件路由 - 配置文件列表、读取、保存（带备份）、回滚、历史、新增、删除

端点：
- GET  /categories               : 获取配置分类列表
- GET  /{host}/list              : 返回配置文件列表（预定义 + 自定义，支持分类筛选）
- GET  /{host}/read              : 通过 SSH 读取配置文件内容
- POST /{host}/save              : 保存配置文件（先备份原内容，再写入新内容）
- POST /{host}/create            : 新增配置文件并保存到服务器
- POST /{host}/rollback/{backup_id}: 回滚到指定备份版本
- DELETE /{host}/custom/{config_id}: 删除自定义配置定义
- GET  /{host}/history          : 查询配置文件修改历史
"""

import asyncio
import base64
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..core.deps import get_current_active_user, require_operator
from ..database import get_db
from ..models.config_backup import ConfigBackup
from ..models.custom_config import CustomConfig
from ..models.user import User
from ..schemas.config_file import (
    ConfigBackupInfo,
    ConfigCreateRequest,
    ConfigFileContent,
    ConfigFileInfo,
    ConfigSaveRequest,
)
from ...tools.base import ToolRegistry

logger = logging.getLogger(__name__)

router = APIRouter(tags=["配置文件管理"])

# ---------------------------------------------------------------------------
# 预定义配置文件列表（按分类组织）
# ---------------------------------------------------------------------------
PREDEFINED_CONFIGS: List[ConfigFileInfo] = [
    # 服务器配置
    ConfigFileInfo(path="/etc/nginx/nginx.conf", name="nginx.conf", format="conf", category="server"),
    ConfigFileInfo(path="/etc/sysctl.conf", name="sysctl.conf", format="conf", category="server"),
    ConfigFileInfo(path="/etc/ssh/sshd_config", name="sshd_config", format="conf", category="server"),
    ConfigFileInfo(path="/etc/fstab", name="fstab", format="conf", category="server"),
    ConfigFileInfo(path="/etc/hosts", name="hosts", format="conf", category="server"),
    ConfigFileInfo(path="/etc/environment", name="environment", format="conf", category="server"),
    ConfigFileInfo(path="/etc/crontab", name="crontab", format="conf", category="server"),
    ConfigFileInfo(path="/etc/rsyslog.conf", name="rsyslog.conf", format="conf", category="server"),
    # 数据库配置
    ConfigFileInfo(path="/etc/my.cnf", name="my.cnf", format="conf", category="database"),
    ConfigFileInfo(path="/etc/redis/redis.conf", name="redis.conf", format="conf", category="database"),
    ConfigFileInfo(path="/etc/postgresql/postgresql.conf", name="postgresql.conf", format="conf", category="database"),
    # 应用配置
    ConfigFileInfo(path="/opt/app/application.yml", name="application.yml", format="yml", category="application"),
    ConfigFileInfo(path="/opt/app/application.yaml", name="application.yaml", format="yml", category="application"),
    ConfigFileInfo(path="/opt/app/application.properties", name="application.properties", format="properties", category="application"),
]

# 分类标签映射
CATEGORY_LABELS = {
    "server": "服务器配置",
    "database": "数据库配置",
    "llm": "LLM 配置",
    "application": "应用配置",
    "other": "其他",
}


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


@router.get("/categories", summary="获取配置分类列表")
def get_categories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """返回所有配置分类及其文件数量。"""
    # 合并预定义和自定义配置
    all_configs = list(PREDEFINED_CONFIGS)
    custom_configs = db.query(CustomConfig).all()
    for cc in custom_configs:
        all_configs.append(ConfigFileInfo(
            path=cc.file_path,
            name=cc.name,
            format=_detect_format(cc.file_path),
            category=cc.category,
            is_custom=True,
            config_id=cc.id,
        ))

    # 统计每个分类的数量
    counts: dict = {}
    for c in all_configs:
        cat = c.category or "other"
        counts[cat] = counts.get(cat, 0) + 1

    # 返回所有已知分类（即使数量为 0 也列出）
    result = []
    for cat_key, cat_label in CATEGORY_LABELS.items():
        result.append({
            "category": cat_key,
            "label": cat_label,
            "count": counts.get(cat_key, 0),
        })
    # 补充未在 CATEGORY_LABELS 中的分类
    for cat_key, cnt in counts.items():
        if cat_key not in CATEGORY_LABELS:
            result.append({
                "category": cat_key,
                "label": cat_key,
                "count": cnt,
            })
    return result


@router.get("/{host}/list", response_model=List[ConfigFileInfo], summary="获取配置文件列表")
def list_config_files(
    host: str,
    category: Optional[str] = Query(None, description="按分类筛选: server/database/llm/application/other"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """返回配置文件列表（预定义 + 自定义），支持按分类筛选。

    Args:
        host: 服务器地址
        category: 配置分类筛选（可选）
        db: 数据库会话
        current_user: 当前登录用户

    Returns:
        ConfigFileInfo 列表
    """
    configs = list(PREDEFINED_CONFIGS)

    # 从数据库加载自定义配置
    custom_configs = db.query(CustomConfig).all()
    for cc in custom_configs:
        configs.append(ConfigFileInfo(
            path=cc.file_path,
            name=cc.name,
            format=_detect_format(cc.file_path),
            category=cc.category,
            is_custom=True,
            config_id=cc.id,
        ))

    # 按分类筛选
    if category:
        configs = [c for c in configs if (c.category or "other") == category]

    return configs


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


# ---------------------------------------------------------------------------
# 新增 / 删除自定义配置文件
# ---------------------------------------------------------------------------
@router.post("/{host}/create", response_model=ConfigFileInfo, summary="新增配置文件")
async def create_config_file(
    host: str,
    request: ConfigCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """新增配置文件并保存到服务器。

    操作流程：
    1. 检查路径是否已存在于预定义或自定义配置中
    2. 通过 SSH 在服务器上创建目录（如需）并写入初始内容
    3. 在数据库中保存自定义配置记录
    4. 返回 ConfigFileInfo

    Args:
        host: 服务器地址
        request: 新增配置文件请求
        db: 数据库会话
        current_user: 当前登录用户（需要 operator 权限）

    Returns:
        ConfigFileInfo: 新创建的配置文件信息
    """
    # 1. 检查路径是否已存在
    existing_predefined = next(
        (c for c in PREDEFINED_CONFIGS if c.path == request.path), None
    )
    if existing_predefined:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"配置文件路径已存在于预定义配置中: {request.path}",
        )

    existing_custom = db.query(CustomConfig).filter(
        CustomConfig.file_path == request.path
    ).first()
    if existing_custom:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"配置文件路径已存在于自定义配置中: {request.path}",
        )

    # 2. 通过 SSH 在服务器上创建文件
    ssh_tool = ToolRegistry.get("ssh_execute")
    if not ssh_tool:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SSH 工具未注册",
        )

    # 确保目录存在
    dir_path = request.path.rsplit("/", 1)[0] if "/" in request.path else "."
    mkdir_command = f"mkdir -p '{dir_path}'"
    await asyncio.to_thread(
        ssh_tool.execute_with_logging,
        host=host,
        command=mkdir_command,
        timeout=10,
    )

    # 写入初始内容（base64 编码安全传输）
    encoded = base64.b64encode(request.content.encode("utf-8")).decode("ascii")
    write_command = f"echo '{encoded}' | base64 -d > '{request.path}'"
    write_result = await asyncio.to_thread(
        ssh_tool.execute_with_logging,
        host=host,
        command=write_command,
        timeout=15,
    )

    if not write_result.success:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"创建配置文件失败: {write_result.error}",
        )

    # 3. 在数据库中保存自定义配置记录
    custom_config = CustomConfig(
        name=request.name,
        file_path=request.path,
        category=request.category,
        description=request.description or None,
        created_by=current_user.username,
    )
    db.add(custom_config)
    db.commit()
    db.refresh(custom_config)

    # 4. 返回 ConfigFileInfo
    return ConfigFileInfo(
        path=custom_config.file_path,
        name=custom_config.name,
        format=_detect_format(custom_config.file_path),
        category=custom_config.category,
        is_custom=True,
        config_id=custom_config.id,
    )


@router.delete("/{host}/custom/{config_id}", summary="删除自定义配置")
def delete_custom_config(
    host: str,
    config_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """删除自定义配置定义（仅删除数据库记录，不删除服务器上的文件）。

    Args:
        host: 服务器地址
        config_id: 自定义配置 ID
        db: 数据库会话
        current_user: 当前登录用户（需要 operator 权限）

    Returns:
        操作结果
    """
    custom_config = db.query(CustomConfig).filter(
        CustomConfig.id == config_id,
    ).first()

    if not custom_config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"自定义配置不存在: id={config_id}",
        )

    file_path = custom_config.file_path
    db.delete(custom_config)
    db.commit()

    return {
        "success": True,
        "message": f"自定义配置 {file_path} 已删除（服务器文件未删除）",
        "config_id": config_id,
    }
