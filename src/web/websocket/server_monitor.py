"""WebSocket 服务器状态实时推送"""
import asyncio
import logging
from datetime import datetime
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import JWTError

from ..core.security import decode_token
from ...tools.base import ToolRegistry
from ...utils.config_loader import ConfigLoader
from ..database import SessionLocal
from ..models.server_metric import ServerMetric

router = APIRouter()
logger = logging.getLogger(__name__)


@router.websocket("/monitor")
async def server_monitor(websocket: WebSocket, token: str = ""):
    """服务器状态实时推送 - 每 10 秒采集一次所有服务器状态"""
    # 验证 token
    try:
        decode_token(token)
    except (JWTError, Exception):
        await websocket.close(code=4001)
        return

    await websocket.accept()

    config = ConfigLoader.get_instance().config
    metrics_tool = ToolRegistry.get("system_metrics")

    if not metrics_tool:
        await websocket.send_json({"error": "系统指标工具未注册"})
        await websocket.close()
        return

    try:
        while True:
            servers_data = []
            for server in config.servers:
                if not server.host:
                    continue

                try:
                    # 采集指标
                    result = await asyncio.to_thread(
                        metrics_tool.execute_with_logging,
                        host=server.host,
                        metric_type="all"
                    )

                    if result.success and result.data:
                        data = result.data
                        cpu_usage = _extract_cpu_usage(data)
                        mem_usage = _extract_mem_usage(data)
                        disk_usage = _extract_disk_usage(data)
                        online = True

                        # 存入数据库
                        _save_metric(server.host, cpu_usage, mem_usage, disk_usage, online)

                        # 检查阈值告警
                        _check_thresholds(server.host, cpu_usage, mem_usage, disk_usage, config)

                        servers_data.append({
                            "host": server.host,
                            "name": server.name or server.host,
                            "online": online,
                            "cpu_usage": cpu_usage,
                            "memory_usage": mem_usage,
                            "disk_usage": disk_usage,
                            "os_type": server.os_type,
                            "timestamp": datetime.now().isoformat()
                        })
                    else:
                        servers_data.append({
                            "host": server.host,
                            "name": server.name or server.host,
                            "online": False,
                            "cpu_usage": 0,
                            "memory_usage": 0,
                            "disk_usage": 0,
                            "os_type": server.os_type,
                            "timestamp": datetime.now().isoformat()
                        })
                except Exception as e:
                    logger.warning(f"采集 {server.host} 指标失败: {e}")
                    servers_data.append({
                        "host": server.host,
                        "name": server.name or server.host,
                        "online": False,
                        "error": str(e),
                        "timestamp": datetime.now().isoformat()
                    })

            await websocket.send_json({
                "type": "server_status",
                "servers": servers_data,
                "timestamp": datetime.now().isoformat()
            })

            await asyncio.sleep(10)

    except WebSocketDisconnect:
        logger.info("WebSocket 监控断开")
    except Exception as e:
        logger.error(f"监控推送异常: {e}")


def _extract_cpu_usage(data: dict) -> float:
    """从 SystemMetricsTool 返回数据中提取 CPU 使用率"""
    # data 格式参考 system_tools.py 的返回结构
    try:
        cpu_data = data.get("cpu", {})
        if isinstance(cpu_data, str):
            import re
            match = re.search(r'(\d+\.?\d*)%', cpu_data)
            if match:
                return float(match.group(1))
        elif isinstance(cpu_data, dict):
            for key in ["usage", "cpu_usage", "CPU Usage", "usage_percent"]:
                if key in cpu_data:
                    val = cpu_data[key]
                    if isinstance(val, str):
                        import re
                        match = re.search(r'(\d+\.?\d*)', val)
                        if match:
                            return float(match.group(1))
                    return float(val)
    except Exception:
        pass
    return 0.0


def _extract_mem_usage(data: dict) -> float:
    try:
        mem_data = data.get("memory", {})
        if isinstance(mem_data, str):
            import re
            match = re.search(r'(\d+\.?\d*)%', mem_data)
            if match:
                return float(match.group(1))
        elif isinstance(mem_data, dict):
            for key in ["usage_percent", "memory_usage", "usage", "used_percent"]:
                if key in mem_data:
                    val = mem_data[key]
                    if isinstance(val, str):
                        import re
                        match = re.search(r'(\d+\.?\d*)', val)
                        if match:
                            return float(match.group(1))
                    return float(val)
    except Exception:
        pass
    return 0.0


def _extract_disk_usage(data: dict) -> float:
    try:
        disk_data = data.get("disk", {})
        if isinstance(disk_data, str):
            import re
            match = re.search(r'(\d+\.?\d*)%', disk_data)
            if match:
                return float(match.group(1))
        elif isinstance(disk_data, dict):
            for key in ["usage_percent", "disk_usage", "usage", "used_percent"]:
                if key in disk_data:
                    val = disk_data[key]
                    if isinstance(val, str):
                        import re
                        match = re.search(r'(\d+\.?\d*)', val)
                        if match:
                            return float(match.group(1))
                    return float(val)
    except Exception:
        pass
    return 0.0


def _save_metric(host: str, cpu: float, mem: float, disk: float, online: bool):
    """保存监控指标到数据库"""
    db = SessionLocal()
    try:
        metric = ServerMetric(
            server_host=host,
            cpu_usage=cpu,
            memory_usage=mem,
            disk_usage=disk,
            online=online,
        )
        db.add(metric)
        db.commit()
    except Exception as e:
        logger.warning(f"保存指标失败: {e}")
        db.rollback()
    finally:
        db.close()


def _check_thresholds(host: str, cpu: float, mem: float, disk: float, config):
    """检查阈值告警"""
    from ..models.alert import Alert
    thresholds = config.thresholds if hasattr(config, 'thresholds') else {"cpu": 80, "memory": 85, "disk": 90}

    db = SessionLocal()
    try:
        if cpu > thresholds.get("cpu", 80):
            alert = Alert(server_host=host, alert_type="cpu_high", severity="warning" if cpu < 90 else "critical",
                         message=f"CPU 使用率 {cpu:.1f}% 超过阈值 {thresholds.get('cpu', 80)}%",
                         threshold=thresholds.get("cpu", 80), current_value=cpu)
            db.add(alert)
        if mem > thresholds.get("memory", 85):
            alert = Alert(server_host=host, alert_type="mem_high", severity="warning" if mem < 90 else "critical",
                         message=f"内存使用率 {mem:.1f}% 超过阈值 {thresholds.get('memory', 85)}%",
                         threshold=thresholds.get("memory", 85), current_value=mem)
            db.add(alert)
        if disk > thresholds.get("disk", 90):
            alert = Alert(server_host=host, alert_type="disk_high", severity="warning" if disk < 95 else "critical",
                         message=f"磁盘使用率 {disk:.1f}% 超过阈值 {thresholds.get('disk', 90)}%",
                         threshold=thresholds.get("disk", 90), current_value=disk)
            db.add(alert)
        db.commit()
    except Exception as e:
        logger.warning(f"保存告警失败: {e}")
        db.rollback()
    finally:
        db.close()
