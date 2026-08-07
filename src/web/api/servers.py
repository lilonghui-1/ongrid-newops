"""服务器路由 - 服务器列表、状态、指标历史、电源操作、阈值配置

端点：
- GET  /                 : 返回所有配置的服务器列表（探测在线状态）
- GET  /thresholds       : 获取当前监控阈值配置
- PUT  /thresholds       : 更新监控阈值配置（admin 权限）
- GET  /{host}/status    : 获取服务器实时状态（CPU/内存/磁盘）
- GET  /{host}/metrics   : 查询服务器指标历史数据
- POST /{host}/power     : 电源操作（reboot/shutdown/start，admin 权限）
"""

import asyncio
import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..core.deps import get_current_active_user, require_admin
from ..database import get_db
from ..models.server_metric import ServerMetric
from ..models.user import User
from ..schemas.server import (
    CPUInfo,
    DiskInfo,
    MemInfo,
    MetricHistoryResponse,
    PowerRequest,
    ServerInfo,
    ServerStatusResponse,
    ThresholdConfig,
)
from ...tools.base import ToolRegistry
from ...utils.config_loader import ConfigLoader

logger = logging.getLogger(__name__)

router = APIRouter(tags=["服务器管理"])

# ---------------------------------------------------------------------------
# 阈值持久化
# ---------------------------------------------------------------------------
THRESHOLDS_FILE = Path("/workspace/ops-agent/data/thresholds.json")

DEFAULT_THRESHOLDS = {
    "cpu_warning": 80,
    "cpu_critical": 90,
    "memory_warning": 80,
    "memory_critical": 90,
    "disk_warning": 80,
    "disk_critical": 90,
}


def _load_thresholds() -> dict:
    """从 JSON 文件加载阈值配置，文件不存在时返回默认值。"""
    if THRESHOLDS_FILE.exists():
        try:
            with open(THRESHOLDS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                # 合并默认值，确保所有字段都存在
                merged = DEFAULT_THRESHOLDS.copy()
                merged.update(data)
                return merged
        except (json.JSONDecodeError, IOError):
            pass
    return DEFAULT_THRESHOLDS.copy()


def _save_thresholds(data: dict) -> None:
    """将阈值配置保存到 JSON 文件。"""
    THRESHOLDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(THRESHOLDS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# 系统指标解析辅助函数
# ---------------------------------------------------------------------------
def _parse_size_to_bytes(size_str: str) -> float:
    """将大小字符串（如 7.8Gi、512Mi、2.0G）转换为字节数。"""
    size_str = size_str.strip()
    match = re.match(r"([\d.]+)\s*([A-Za-z]*)", size_str)
    if not match:
        return 0.0
    value = float(match.group(1))
    unit = match.group(2).upper()
    multipliers = {
        "": 1,
        "B": 1,
        "K": 1024,
        "KB": 1024,
        "KIB": 1024,
        "M": 1024**2,
        "MB": 1024**2,
        "MIB": 1024**2,
        "G": 1024**3,
        "GB": 1024**3,
        "GIB": 1024**3,
        "T": 1024**4,
        "TB": 1024**4,
        "TIB": 1024**4,
    }
    return value * multipliers.get(unit, 1)


def _parse_cpu_info(text: str) -> CPUInfo:
    """解析 CPU 指标文本，提取使用率、核心数、负载平均值。"""
    usage = 0.0
    cores = 0
    load_avg = ""

    # CPU 使用率：从 top 输出中提取 idle 百分比，usage = 100 - idle
    idle_match = re.search(r"(\d+\.?\d*)\s*id", text)
    if idle_match:
        idle = float(idle_match.group(1))
        usage = round(100 - idle, 1)

    # CPU 核心数
    cores_match = re.search(r"CPU Cores:\s*(\d+)", text)
    if cores_match:
        cores = int(cores_match.group(1))

    # 负载平均值
    load_match = re.search(r"Load Average:\s*(.+)", text)
    if load_match:
        load_avg = load_match.group(1).strip()
    else:
        # /proc/loadavg 格式: "0.05 0.03 0.01 1/123 456"
        load_match = re.search(r"(\d+\.?\d*\s+\d+\.?\d*\s+\d+\.?\d*)", text)
        if load_match:
            load_avg = load_match.group(1)

    return CPUInfo(usage=usage, cores=cores, load_avg=load_avg)


def _parse_memory_info(text: str) -> MemInfo:
    """解析内存指标文本，提取总量、已用、可用、使用率。"""
    total = used = free = ""
    usage = 0.0

    mem_match = re.search(r"Mem:\s+(\S+)\s+(\S+)\s+(\S+)", text)
    if mem_match:
        total = mem_match.group(1)
        used = mem_match.group(2)
        free = mem_match.group(3)
        total_bytes = _parse_size_to_bytes(total)
        used_bytes = _parse_size_to_bytes(used)
        if total_bytes > 0:
            usage = round(used_bytes / total_bytes * 100, 1)

    return MemInfo(total=total, used=used, free=free, usage=usage)


def _parse_disk_info(text: str) -> DiskInfo:
    """解析磁盘指标文本，提取根分区总量、已用、可用、使用率。"""
    total = used = free = ""
    usage = 0.0

    for line in text.split("\n"):
        line = line.strip()
        if not line or line.startswith("Filesystem") or line.startswith("Inode"):
            continue
        parts = line.split()
        if len(parts) < 6:
            continue
        # 优先匹配根分区
        if parts[-1] == "/":
            total = parts[1]
            used = parts[2]
            free = parts[3]
            try:
                usage = float(parts[4].rstrip("%"))
            except ValueError:
                pass
            break

    # 如果没找到根分区，取第一条数据行
    if not total:
        for line in text.split("\n"):
            line = line.strip()
            if not line or line.startswith("Filesystem") or line.startswith("Inode"):
                continue
            parts = line.split()
            if len(parts) >= 6:
                total = parts[1]
                used = parts[2]
                free = parts[3]
                try:
                    usage = float(parts[4].rstrip("%"))
                except ValueError:
                    pass
                break

    return DiskInfo(total=total, used=used, free=free, usage=usage)


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------
@router.get("", response_model=List[ServerInfo], summary="获取服务器列表")
async def list_servers(
    current_user: User = Depends(get_current_active_user),
):
    """返回所有已配置的服务器列表，并探测在线状态。

    通过 SSH 执行 ``whoami`` 命令探测每台服务器是否在线。
    """
    try:
        config = ConfigLoader.get_instance().config
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="配置未加载",
        )

    ssh_tool = ToolRegistry.get("ssh_execute")
    servers_config = config.servers or []

    async def _check_online(host: str) -> bool:
        """通过 SSH whoami 探测服务器是否在线。"""
        if not ssh_tool:
            return False
        try:
            result = await asyncio.to_thread(
                ssh_tool.execute_with_logging,
                host=host,
                command="whoami",
                timeout=5,
            )
            return result.success
        except Exception:
            return False

    # 并行探测所有服务器
    hosts = [s.host for s in servers_config]
    online_results = await asyncio.gather(*[_check_online(h) for h in hosts])

    result: List[ServerInfo] = []
    for server_cfg, online in zip(servers_config, online_results):
        db_types = [db.type for db in (server_cfg.databases or [])]
        result.append(ServerInfo(
            id=server_cfg.host,
            name=server_cfg.name or server_cfg.host,
            host=server_cfg.host,
            port=server_cfg.port,
            os_type=server_cfg.os_type,
            tags=list(server_cfg.tags or []),
            online=online,
            databases=db_types,
        ))

    return result


@router.get("/thresholds", response_model=ThresholdConfig, summary="获取监控阈值配置")
def get_thresholds(
    current_user: User = Depends(get_current_active_user),
):
    """返回当前的监控阈值配置。"""
    data = _load_thresholds()
    return ThresholdConfig(**data)


@router.put("/thresholds", response_model=ThresholdConfig, summary="更新监控阈值配置")
def update_thresholds(
    config: ThresholdConfig,
    current_user: User = Depends(require_admin),
):
    """更新监控阈值配置（需要管理员权限）。

    Args:
        config: 新的阈值配置
        current_user: 当前登录用户（需要 admin 权限）

    Returns:
        更新后的阈值配置
    """
    data = config.model_dump()
    _save_thresholds(data)
    return ThresholdConfig(**data)


@router.get("/{host}/status", response_model=ServerStatusResponse, summary="获取服务器实时状态")
async def get_server_status(
    host: str,
    current_user: User = Depends(get_current_active_user),
):
    """获取指定服务器的实时状态（CPU、内存、磁盘）。

    调用 system_metrics 工具采集指标，并解析为结构化数据。
    """
    metrics_tool = ToolRegistry.get("system_metrics")
    ssh_tool = ToolRegistry.get("ssh_execute")

    if not metrics_tool:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="系统指标工具未注册",
        )

    # 并行采集系统指标和 uptime
    metrics_task = asyncio.to_thread(
        metrics_tool.execute_with_logging, host=host, metric_type="all"
    )
    uptime_task = asyncio.to_thread(
        ssh_tool.execute_with_logging,
        host=host,
        command="uptime -p 2>/dev/null || cat /proc/uptime",
        timeout=10,
    ) if ssh_tool else asyncio.to_thread(lambda: None)

    metrics_result, uptime_result = await asyncio.gather(metrics_task, uptime_task)

    if not metrics_result.success:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"获取服务器状态失败: {metrics_result.error}",
        )

    raw_data = metrics_result.data or {}
    cpu_text = raw_data.get("cpu", "")
    mem_text = raw_data.get("memory", "")
    disk_text = raw_data.get("disk", "")

    cpu_info = _parse_cpu_info(cpu_text)
    mem_info = _parse_memory_info(mem_text)
    disk_info = _parse_disk_info(disk_text)

    # 解析 uptime
    uptime_str = ""
    if uptime_result and hasattr(uptime_result, "success") and uptime_result.success:
        uptime_str = (uptime_result.data or {}).get("stdout", "").strip()
        # 如果是 /proc/uptime 的输出（纯数字），转换为可读格式
        if uptime_str and re.match(r"^\d+\.?\d*\s+\d+\.?\d*$", uptime_str):
            try:
                seconds = float(uptime_str.split()[0])
                days = int(seconds // 86400)
                hours = int((seconds % 86400) // 3600)
                mins = int((seconds % 3600) // 60)
                uptime_str = f"up {days}d {hours}h {mins}m"
            except (ValueError, IndexError):
                pass

    return ServerStatusResponse(
        host=host,
        online=True,
        cpu=cpu_info,
        memory=mem_info,
        disk=disk_info,
        uptime=uptime_str,
    )


@router.get("/{host}/metrics", response_model=MetricHistoryResponse, summary="查询指标历史")
def get_server_metrics(
    host: str,
    time_range: str = Query("1h", description="时间范围: 1h/24h/7d"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """从数据库查询服务器的历史监控指标。

    Args:
        host: 服务器地址
        time_range: 时间范围（1h/24h/7d）
        db: 数据库会话
        current_user: 当前登录用户

    Returns:
        MetricHistoryResponse: 指标历史数据
    """
    time_map = {
        "1h": timedelta(hours=1),
        "24h": timedelta(hours=24),
        "7d": timedelta(days=7),
    }
    delta = time_map.get(time_range, timedelta(hours=1))
    since = datetime.now() - delta

    metrics = (
        db.query(ServerMetric)
        .filter(
            ServerMetric.server_host == host,
            ServerMetric.collected_at >= since,
        )
        .order_by(ServerMetric.collected_at.asc())
        .all()
    )

    metric_list = [
        {
            "cpu_usage": m.cpu_usage,
            "memory_usage": m.memory_usage,
            "disk_usage": m.disk_usage,
            "cpu_load_avg": m.cpu_load_avg,
            "uptime": m.uptime,
            "online": m.online,
            "collected_at": m.collected_at.isoformat() if m.collected_at else None,
        }
        for m in metrics
    ]

    return MetricHistoryResponse(
        host=host,
        metrics=metric_list,
        time_range=time_range,
    )


@router.post("/{host}/power", summary="服务器电源操作")
async def power_operation(
    host: str,
    request: PowerRequest,
    current_user: User = Depends(require_admin),
):
    """对服务器执行电源操作（重启/关机/开机）。

    需要管理员权限。通过 SSH 执行对应命令。

    Args:
        host: 服务器地址
        request: 电源操作请求（action: reboot/shutdown/start）
        current_user: 当前登录用户（需要 admin 权限）

    Returns:
        操作结果
    """
    valid_actions = ("reboot", "shutdown", "start")
    if request.action not in valid_actions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的操作: {request.action}，允许: {', '.join(valid_actions)}",
        )

    ssh_tool = ToolRegistry.get("ssh_execute")
    if not ssh_tool:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SSH 工具未注册",
        )

    # start 操作通常需要 WOL/IPMI，此处返回提示
    if request.action == "start":
        return {
            "success": False,
            "message": "开机操作需要 Wake-on-LAN 或 IPMI 支持，请通过带外管理工具执行",
            "host": host,
        }

    # 构建 SSH 命令
    command_map = {
        "reboot": "sudo shutdown -r now",
        "shutdown": "sudo shutdown -h now",
    }
    command = command_map[request.action]

    result = await asyncio.to_thread(
        ssh_tool.execute_with_logging,
        host=host,
        command=command,
        timeout=10,
    )

    action_label = "重启" if request.action == "reboot" else "关机"
    if not result.success:
        # 重启/关机命令执行后 SSH 连接可能断开，这是正常现象
        return {
            "success": True,
            "message": f"服务器 {host} {action_label}指令已发送（连接断开属正常现象）",
            "host": host,
            "action": request.action,
        }

    return {
        "success": True,
        "message": f"服务器 {host} {action_label}指令已执行",
        "host": host,
        "action": request.action,
        "detail": result.data,
    }
