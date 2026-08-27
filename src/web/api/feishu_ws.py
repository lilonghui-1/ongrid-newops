"""飞书长连接客户端 - 使用 lark-oapi SDK WebSocket 模式

与 Webhook 模式不同，长连接模式无需公网 IP 和域名，
通过 WebSocket 主动连接飞书服务器接收事件推送。

两种入站模式可通过配置选择：
- use_ws: true  → 长连接模式（推荐，无需公网 IP）
- use_ws: false → Webhook 模式（需要公网可访问的回调 URL）

使用方式：
1. pip install lark-oapi
2. 配置 FEISHU_APP_ID / FEISHU_APP_SECRET
3. 设置 feishu_app.use_ws: true（或环境变量 FEISHU_USE_WS=true）
4. 启动服务后自动在后台线程维持长连接
"""

import json
import logging
import os
import threading
from typing import Any, Dict

logger = logging.getLogger(__name__)

# 飞书配置（从环境变量读取，与 feishu.py 共享）
FEISHU_APP_ID = os.environ.get("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "")

# 长连接客户端单例
_ws_client = None
_ws_thread = None


def _convert_event_to_dict(event) -> Dict[str, Any]:
    """将 lark-oapi SDK 事件对象转为与 feishu.py 一致的 dict 格式。

    feishu.py 的 _process_feishu_message 期望格式：
    {
        "event": {
            "message": {"chat_id": ..., "message_type": ..., "content": ...},
            "sender": {"sender_id": {"open_id": ...}},
            "mentions": [...]
        }
    }
    """
    try:
        # Pydantic v2: model_dump()
        event_dict = event.event.model_dump()
    except AttributeError:
        try:
            # Pydantic v1: dict()
            event_dict = event.event.dict()
        except AttributeError:
            # 兜底：手动提取字段
            msg = getattr(event.event, "message", None)
            sender = getattr(event.event, "sender", None)
            event_dict = {
                "message": {
                    "chat_id": getattr(msg, "chat_id", "") if msg else "",
                    "message_type": getattr(msg, "message_type", "text") if msg else "text",
                    "content": getattr(msg, "content", "{}") if msg else "{}",
                    "message_id": getattr(msg, "message_id", "") if msg else "",
                },
                "sender": {
                    "sender_id": {
                        "open_id": getattr(
                            getattr(sender, "sender_id", None) if sender else None,
                            "open_id", "unknown"
                        )
                    },
                },
                "mentions": [],
            }
    return {"event": event_dict}


def _on_message_receive(ctx, event):
    """im.message.receive_v1 事件回调。

    lark-oapi SDK 会将事件解析为 P2ImMessageReceiveV1 对象。
    在新线程中处理消息，避免阻塞 SDK 事件循环导致飞书重试。
    """
    try:
        event_data = _convert_event_to_dict(event)
        msg_info = event_data.get("event", {}).get("message", {})
        logger.info(
            f"收到飞书长连接消息: chat_id={msg_info.get('chat_id', '')}, "
            f"type={msg_info.get('message_type', '')}, "
            f"content={msg_info.get('content', '')[:100]}"
        )

        # 复用 feishu.py 的消息处理逻辑
        from .feishu import _process_feishu_message
        thread = threading.Thread(
            target=_process_feishu_message,
            args=(event_data,),
            daemon=True,
        )
        thread.start()
    except Exception as e:
        logger.error(f"飞书长连接消息处理异常: {e}", exc_info=True)


def start_ws_client():
    """启动飞书 WebSocket 长连接客户端（阻塞函数，应在后台线程中调用）。

    使用 lark-oapi SDK 的 lark.ws.Client 建立 WebSocket 长连接，
    SDK 内部自动重连，无需手动维护心跳。
    """
    global _ws_client

    if not FEISHU_APP_ID or not FEISHU_APP_SECRET:
        logger.warning("飞书长连接未启动：FEISHU_APP_ID / FEISHU_APP_SECRET 未配置")
        return

    try:
        import lark_oapi as lark
    except ImportError:
        logger.error("飞书长连接需要 lark-oapi 包，请执行: pip install lark-oapi")
        return

    logger.info("正在启动飞书 WebSocket 长连接...")

    # 构建事件分发处理器
    # builder 的两个参数为 encryption_key 和 verification_token，
    # 长连接模式下 SDK 自动处理验证，传空字符串即可
    event_handler = (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_im_message_receive_v1(_on_message_receive)
        .build()
    )

    _ws_client = lark.ws.Client(
        FEISHU_APP_ID,
        FEISHU_APP_SECRET,
        event_handler=event_handler,
        log_level=lark.LogLevel.INFO,
    )

    # 阻塞调用，SDK 内部自动重连
    _ws_client.start()


def start_in_background():
    """在后台守护线程中启动飞书长连接。

    由 app.py 在应用启动时调用。
    读取环境变量 FEISHU_USE_WS 判断是否启用（默认 true）。
    """
    global _ws_thread

    use_ws = os.environ.get("FEISHU_USE_WS", "true").lower() in ("true", "1", "yes", "on")

    if not use_ws:
        logger.info("飞书长连接模式未启用（FEISHU_USE_WS != true），使用 Webhook 模式")
        return

    if not FEISHU_APP_ID or not FEISHU_APP_SECRET:
        logger.info("飞书长连接未启动：未配置 FEISHU_APP_ID / FEISHU_APP_SECRET")
        return

    _ws_thread = threading.Thread(target=start_ws_client, daemon=True, name="feishu-ws")
    _ws_thread.start()
    logger.info("飞书长连接后台线程已启动")


def get_status() -> dict:
    """获取飞书长连接状态。"""
    return {
        "enabled": os.environ.get("FEISHU_USE_WS", "true").lower() in ("true", "1", "yes", "on"),
        "app_id_configured": bool(FEISHU_APP_ID),
        "app_secret_configured": bool(FEISHU_APP_SECRET),
        "ws_thread_alive": _ws_thread.is_alive() if _ws_thread else False,
        "ready": bool(FEISHU_APP_ID and FEISHU_APP_SECRET),
    }
