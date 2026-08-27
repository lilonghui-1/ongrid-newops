"""飞书事件回调路由 - 接收飞书消息、触发 Agent 执行、回传结果

端点：
- POST /webhook  : 飞书事件回调入口（URL 验证 + 消息接收）

飞书自建应用事件订阅流程：
1. 在飞书开放平台创建自建应用，获取 App ID / App Secret / Verification Token / Encrypt Key
2. 配置事件订阅 URL 为 https://your-server/api/feishu/webhook
3. 订阅 im.message.receive_v1 事件
4. 用户在飞书中 @机器人 发消息 → 飞书推送到此回调 → 触发 LLM 对话 → 结果回传飞书
"""

import hashlib
import hmac
import json
import logging
import os
import threading
import time
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, Header, HTTPException, Request, status

from ..database import SessionLocal
from ..models.chat_history import ChatHistory
from ..utils.config_loader import ConfigLoader

logger = logging.getLogger(__name__)

router = APIRouter(tags=["飞书事件"])

# ── 飞书配置（从环境变量读取）──
FEISHU_APP_ID = os.environ.get("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "")
FEISHU_VERIFICATION_TOKEN = os.environ.get("FEISHU_VERIFICATION_TOKEN", "")
FEISHU_ENCRYPT_KEY = os.environ.get("FEISHU_ENCRYPT_KEY", "")

# ── 飞书 API 基址 ──
FEISHU_API_BASE = "https://open.feishu.cn/open-apis"

# ── tenant_access_token 缓存 ──
_token_cache = {"token": "", "expires_at": 0}


def _get_tenant_access_token() -> str:
    """获取飞书 tenant_access_token（带缓存，有效期约 2 小时）。"""
    if _token_cache["token"] and time.time() < _token_cache["expires_at"] - 60:
        return _token_cache["token"]

    if not FEISHU_APP_ID or not FEISHU_APP_SECRET:
        raise RuntimeError("FEISHU_APP_ID / FEISHU_APP_SECRET 未配置")

    resp = httpx.post(
        f"{FEISHU_API_BASE}/auth/v3/tenant_access_token/internal",
        json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET},
        timeout=10,
    )
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"获取 tenant_access_token 失败: {data.get('msg')}")

    _token_cache["token"] = data["tenant_access_token"]
    _token_cache["expires_at"] = time.time() + data.get("expire", 7200)
    return _token_cache["token"]


def _send_feishu_message(chat_id: str, content: str, msg_type: str = "text") -> bool:
    """通过飞书 API 向指定会话发送消息。"""
    try:
        token = _get_tenant_access_token()
        payload = {
            "receive_id": chat_id,
            "msg_type": msg_type,
            "content": json.dumps({"text": content}) if msg_type == "text" else content,
        }
        resp = httpx.post(
            f"{FEISHU_API_BASE}/im/v1/messages?receive_id_type=chat_id",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        result = resp.json()
        if result.get("code") != 0:
            logger.error(f"飞书消息发送失败: {result.get('msg')}")
            return False
        return True
    except Exception as e:
        logger.error(f"飞书消息发送异常: {e}")
        return False


def _send_feishu_card(chat_id: str, title: str, content: str) -> bool:
    """发送飞书卡片消息（Markdown 内容）。"""
    try:
        token = _get_tenant_access_token()
        card = {
            "msg_type": "interactive",
            "content": json.dumps({
                "config": {"wide_screen_mode": True},
                "header": {
                    "title": {"tag": "plain_text", "content": title},
                },
                "elements": [
                    {"tag": "markdown", "content": content},
                ],
            }),
        }
        payload = {
            "receive_id": chat_id,
            "msg_type": "interactive",
            "content": card["content"],
        }
        resp = httpx.post(
            f"{FEISHU_API_BASE}/im/v1/messages?receive_id_type=chat_id",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        result = resp.json()
        if result.get("code") != 0:
            logger.error(f"飞书卡片发送失败: {result.get('msg')}")
            return False
        return True
    except Exception as e:
        logger.error(f"飞书卡片发送异常: {e}")
        return False


def _decrypt_payload(encrypt_key: str, encrypted_data: str) -> Dict[str, Any]:
    """解密飞书加密事件数据（AES-256-CBC）。"""
    import base64
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    key = hashlib.sha256(encrypt_key.encode("utf-8")).digest()
    encrypted = base64.b64decode(encrypted_data)
    cipher = Cipher(algorithms.AES(key), modes.CBC(key[:16]))
    decryptor = cipher.decryptor()
    decrypted = decryptor.update(encrypted) + decryptor.finalize()
    # 去除 PKCS7 padding
    pad_len = decrypted[-1]
    decrypted = decrypted[:-pad_len]
    return json.loads(decrypted.decode("utf-8"))


def _process_feishu_message(event_data: Dict[str, Any]):
    """处理飞书消息事件（在后台线程中执行）。

    1. 提取消息内容和发送者
    2. 调用 LLM 生成回复
    3. 通过飞书 API 回传结果
    """
    try:
        event = event_data.get("event", {})
        message = event.get("message", {})
        sender = event.get("sender", {})
        sender_id = sender.get("sender_id", {}).get("open_id", "unknown")
        chat_id = message.get("chat_id", "")
        msg_type = message.get("message_type", "text")
        content_str = message.get("content", "{}")

        # 只处理文本消息
        if msg_type != "text":
            _send_feishu_message(chat_id, "暂仅支持文本消息")
            return

        # 提取文本内容
        try:
            content_data = json.loads(content_str)
            user_text = content_data.get("text", "").strip()
        except Exception:
            user_text = content_str.strip()

        if not user_text:
            return

        # 去除 @机器人 的前缀
        # 飞书消息中 @机器人 的格式为 @_user_1，content 中会有 mentions
        mentions = event.get("mentions", [])
        for m in mentions:
            mention_key = m.get("key", "")
            if mention_key:
                user_text = user_text.replace(mention_key, "").strip()

        logger.info(f"飞书消息来自 {sender_id}: {user_text[:100]}")

        # 先发送"处理中"提示
        _send_feishu_message(chat_id, "正在处理您的请求，请稍候...")

        # 调用 LLM 对话
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage, SystemMessage

        try:
            config = ConfigLoader.get_instance().config
        except RuntimeError:
            _send_feishu_message(chat_id, "系统配置未加载，请联系管理员")
            return

        system_prompt = (
            "你是一个专业的运维助手，帮助用户解决服务器管理、数据库运维、"
            "日志分析、服务监控等运维问题。请提供准确、简洁、可操作的建议。"
            "用户通过飞书群与你对话，回复请使用 Markdown 格式，保持简洁。"
        )

        llm_kwargs = {
            "model": config.llm.model,
            "temperature": config.llm.temperature,
        }
        api_key = config.llm.api_key
        if api_key and not api_key.startswith("${"):
            llm_kwargs["api_key"] = api_key
        base_url = config.llm.base_url
        if base_url and not base_url.startswith("${"):
            llm_kwargs["base_url"] = base_url

        llm = ChatOpenAI(**llm_kwargs)
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_text),
        ]

        # 同步调用 LLM（在后台线程中）
        response = llm.invoke(messages)
        reply_text = response.content if hasattr(response, "content") else str(response)

        if not reply_text or not reply_text.strip():
            reply_text = "抱歉，未能生成回复。"

        # 保存到聊天历史（使用飞书 chat_id 作为 session_id）
        db = SessionLocal()
        try:
            # 保存用户消息
            db.add(ChatHistory(
                session_id=f"feishu_{chat_id}",
                user_id=None,
                role="user",
                content=user_text,
                model=config.llm.model,
            ))
            # 保存 AI 回复
            db.add(ChatHistory(
                session_id=f"feishu_{chat_id}",
                user_id=None,
                role="assistant",
                content=reply_text,
                model=config.llm.model,
            ))
            db.commit()
        except Exception as e:
            logger.error(f"保存飞书聊天历史失败: {e}")
        finally:
            db.close()

        # 回传结果到飞书（卡片消息，Markdown 格式）
        _send_feishu_card(chat_id, "运维 Agent 回复", reply_text)

        logger.info(f"飞书消息处理完成，回复长度: {len(reply_text)}")

    except Exception as e:
        logger.error(f"处理飞书消息异常: {e}", exc_info=True)
        # 尝试通知用户
        try:
            chat_id = event_data.get("event", {}).get("message", {}).get("chat_id", "")
            if chat_id:
                _send_feishu_message(chat_id, f"处理消息时出错: {e}")
        except Exception:
            pass


@router.post("/webhook", summary="飞书事件回调入口")
async def feishu_webhook(
    request: Request,
    x_lark_request_timestamp: Optional[str] = Header(None),
    x_lark_request_nonce: Optional[str] = Header(None),
    x_lark_signature: Optional[str] = Header(None),
):
    """飞书事件订阅回调入口。

    处理两种请求：
    1. URL 验证（飞书配置回调时发送 challenge）
    2. 事件推送（用户发消息时推送 im.message.receive_v1 事件）

    安全验证：
    - 如配置了 Verification Token，校验 event.header.token
    - 如配置了 Encrypt Key，解密事件数据
    """
    body = await request.json()

    # ── 1. URL 验证（飞书配置回调地址时发送）──
    if "challenge" in body:
        challenge = body.get("challenge", "")
        # 如有加密，解密验证
        if "encrypt" in body and FEISHU_ENCRYPT_KEY:
            try:
                decrypted = _decrypt_payload(FEISHU_ENCRYPT_KEY, body["encrypt"])
                return {"challenge": decrypted.get("challenge", challenge)}
            except Exception as e:
                logger.error(f"飞书 challenge 解密失败: {e}")
                raise HTTPException(status_code=400, detail="解密失败")
        return {"challenge": challenge}

    # ── 2. 事件推送 ──
    # 解密（如配置了 Encrypt Key）
    event_data = body
    if "encrypt" in body and FEISHU_ENCRYPT_KEY:
        try:
            event_data = _decrypt_payload(FEISHU_ENCRYPT_KEY, body["encrypt"])
        except Exception as e:
            logger.error(f"飞书事件解密失败: {e}")
            raise HTTPException(status_code=400, detail="事件解密失败")

    # 验证 Token（如配置了）
    if FEISHU_VERIFICATION_TOKEN:
        token = event_data.get("header", {}).get("token", "")
        if token != FEISHU_VERIFICATION_TOKEN:
            logger.warning(f"飞书事件 Token 校验失败: {token[:8]}...")
            raise HTTPException(status_code=401, detail="Token 校验失败")

    # 检查事件类型
    event_type = event_data.get("header", {}).get("event_type", "")

    # 只处理消息接收事件
    if event_type != "im.message.receive_v1":
        logger.debug(f"忽略非消息事件: {event_type}")
        return {"code": 0, "msg": "ok"}

    # 在后台线程中处理消息（避免阻塞飞书回调超时）
    thread = threading.Thread(target=_process_feishu_message, args=(event_data,), daemon=True)
    thread.start()

    # 立即返回，飞书要求 3 秒内响应
    return {"code": 0, "msg": "ok"}


@router.get("/status", summary="飞书集成状态")
async def feishu_status():
    """检查飞书集成配置状态。"""
    from .feishu_ws import get_status as _get_ws_status

    ws_status = _get_ws_status()
    return {
        "app_id_configured": bool(FEISHU_APP_ID),
        "app_secret_configured": bool(FEISHU_APP_SECRET),
        "verification_token_configured": bool(FEISHU_VERIFICATION_TOKEN),
        "encrypt_key_configured": bool(FEISHU_ENCRYPT_KEY),
        "webhook_url": "/api/feishu/webhook",
        "ready": bool(FEISHU_APP_ID and FEISHU_APP_SECRET),
        "ws_mode": ws_status,
    }
