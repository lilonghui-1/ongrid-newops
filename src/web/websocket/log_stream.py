"""WebSocket 实时日志推送"""
import asyncio
import hashlib
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import JWTError

from ..core.security import decode_token
from ...tools.base import ToolRegistry

router = APIRouter()
logger = logging.getLogger(__name__)


@router.websocket("/logs/{server_host}")
async def log_stream(websocket: WebSocket, server_host: str, file_path: str = "/var/log/syslog", token: str = ""):
    """实时日志推送 - 通过 SSH tail -f 持续读取日志"""
    # 1. 验证 token
    try:
        decode_token(token)
    except (JWTError, Exception):
        await websocket.close(code=4001)
        return

    await websocket.accept()

    try:
        # 2. 获取 SSH 工具
        ssh_tool = ToolRegistry.get("ssh_execute")
        if not ssh_tool:
            await websocket.send_json({"error": "SSH 工具未注册"})
            await websocket.close()
            return

        # 3. 执行 tail -f 命令，通过 asyncio.to_thread 包装同步 SSH 调用
        # 注意：tail -f 是持续运行的命令，需要特殊处理
        # 方案：使用 SSH channel 的方式，而不是 exec_command
        # 简化实现：每隔 2 秒执行一次 tail -n 50 获取最新日志，去重后推送

        last_hash = ""
        while True:
            try:
                result = await asyncio.to_thread(
                    ssh_tool.execute_with_logging,
                    host=server_host,
                    command=f"tail -n 50 {file_path}",
                    timeout=10
                )

                if result.success and result.data:
                    content = result.data.get("stdout", "")
                    # 去重：只推送新增的行
                    current_hash = hashlib.md5(content.encode()).hexdigest()
                    if current_hash != last_hash:
                        last_hash = current_hash
                        lines = content.strip().split("\n")
                        for line in lines:
                            level = _detect_log_level(line)
                            await websocket.send_json({
                                "line": line,
                                "level": level,
                                "file": file_path
                            })

                    # 检查是否有停止消息
                    # WebSocket 接收会在 disconnect 时抛异常

                await asyncio.sleep(2)

            except WebSocketDisconnect:
                logger.info(f"WebSocket 日志流断开: {server_host}")
                break
            except Exception as e:
                logger.error(f"日志推送异常: {e}")
                await websocket.send_json({"error": str(e)})
                break

    except WebSocketDisconnect:
        logger.info(f"WebSocket 日志流断开: {server_host}")


def _detect_log_level(line: str) -> str:
    """检测日志行级别"""
    line_upper = line.upper()
    if "ERROR" in line_upper or "FATAL" in line_upper or "CRITICAL" in line_upper:
        return "ERROR"
    elif "WARN" in line_upper or "WARNING" in line_upper:
        return "WARN"
    elif "DEBUG" in line_upper:
        return "DEBUG"
    else:
        return "INFO"
