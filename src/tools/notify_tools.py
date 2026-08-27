"""通知工具 - 多渠道通知（企微/钉钉/飞书/Telegram/Slack/邮件）

设计参考 ongrid 的 notify 抽象（统一 Message + 各渠道 Sender），
在保留基线企微/钉钉实现基础上扩展飞书/Telegram/Slack。
"""

import base64
import hashlib
import hmac
import logging
import time
from typing import Dict, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from .base import BaseTool, ToolResult, ToolParameter

logger = logging.getLogger(__name__)

_TIMEOUT_EXC = (httpx.TimeoutException, httpx.ConnectError)


class Notifier:
    """通知抽象基类：每个渠道实现 _build_payload 与 _sign（可选）"""

    name = "generic"

    def __init__(self, config=None):
        self._config = config

    def is_configured(self) -> bool:
        raise NotImplementedError

    def build_payload(self, title: str, content: str, level: str) -> dict:
        raise NotImplementedError

    def sign(self, payload: dict) -> Optional[str]:
        """返回签名 query 参数（钉钉），默认无签名"""
        return None

    def send(self, title: str, content: str, level: str) -> bool:
        raise NotImplementedError


class WeComNotifier(Notifier):
    """企业微信"""

    name = "wecom"

    def __init__(self, webhook: Optional[str] = None, config=None):
        if config and hasattr(config, "notify"):
            webhook = webhook or getattr(config.notify, "wecom_webhook", None)
        self._webhook = webhook

    def is_configured(self) -> bool:
        return bool(self._webhook and self._webhook.strip() and "${" not in (self._webhook or ""))

    def build_payload(self, title, content, level):
        emoji = NotifyTool.LEVEL_EMOJI.get(level, "")
        return {"msgtype": "markdown", "markdown": {"content": f"## {emoji} {title}\n\n{content}"}}

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=10), retry=retry_if_exception_type(_TIMEOUT_EXC))
    def send(self, title, content, level) -> bool:
        if not self.is_configured():
            logger.warning("企业微信 Webhook 未配置")
            return False
        resp = httpx.post(self._webhook, json=self.build_payload(title, content, level), timeout=10)
        result = resp.json()
        if result.get("errcode") != 0:
            logger.error(f"企业微信通知失败: {result.get('errmsg')}")
            return False
        return True


class DingTalkNotifier(Notifier):
    """钉钉（支持加签）"""

    name = "dingtalk"

    def __init__(self, webhook: Optional[str] = None, secret: Optional[str] = None, config=None):
        if config and hasattr(config, "notify"):
            webhook = webhook or getattr(config.notify, "dingtalk_webhook", None)
            secret = secret or getattr(config.notify, "dingtalk_secret", None)
        self._webhook = webhook
        self._secret = secret

    def is_configured(self) -> bool:
        return bool(self._webhook and self._webhook.strip() and "${" not in (self._webhook or ""))

    def build_payload(self, title, content, level):
        emoji = NotifyTool.LEVEL_EMOJI.get(level, "")
        return {"msgtype": "markdown", "markdown": {"title": f"{emoji} {title}", "text": f"## {emoji} {title}\n\n{content}"}}

    def sign(self, payload=None) -> Optional[str]:
        """钉钉加签：timestamp + secret HMAC-SHA256 → base64"""
        if not self._secret:
            return None
        timestamp = str(round(time.time() * 1000))
        string_to_sign = f"{timestamp}\n{self._secret}"
        hmac_code = hmac.new(self._secret.encode("utf-8"), string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
        sign = base64.b64encode(hmac_code).decode("utf-8")
        return f"timestamp={timestamp}&sign={sign}"

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=10), retry=retry_if_exception_type(_TIMEOUT_EXC))
    def send(self, title, content, level) -> bool:
        if not self.is_configured():
            logger.warning("钉钉 Webhook 未配置")
            return False
        url = self._webhook
        qs = self.sign()
        if qs:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}{qs}"
        resp = httpx.post(url, json=self.build_payload(title, content, level), timeout=10)
        result = resp.json()
        if result.get("errcode") != 0:
            logger.error(f"钉钉通知失败: {result.get('errmsg')}")
            return False
        return True


class FeishuNotifier(Notifier):
    """飞书自定义机器人（加签可选）"""

    name = "lark"

    def __init__(self, webhook: Optional[str] = None, secret: Optional[str] = None, config=None):
        if config and hasattr(config, "notify"):
            webhook = webhook or getattr(config.notify, "lark_webhook", None)
            secret = secret or getattr(config.notify, "lark_secret", None)
        self._webhook = webhook
        self._secret = secret

    def is_configured(self) -> bool:
        return bool(self._webhook and self._webhook.strip() and "${" not in (self._webhook or ""))

    def _sign(self) -> Optional[str]:
        if not self._secret:
            return None
        timestamp = str(round(time.time()))
        string_to_sign = f"{timestamp}\n{self._secret}"
        hmac_code = hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
        sign = base64.b64encode(hmac_code).decode("utf-8")
        return sign

    def build_payload(self, title, content, level):
        emoji = NotifyTool.LEVEL_EMOJI.get(level, "")
        sign = self._sign()
        payload = {
            "msg_type": "interactive",
            "card": {
                "header": {"title": {"tag": "plain_text", "content": f"{emoji} {title}"}},
                "elements": [{"tag": "markdown", "content": content}],
            },
        }
        if sign:
            payload["timestamp"] = str(round(time.time()))
            payload["sign"] = sign
        return payload

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=10), retry=retry_if_exception_type(_TIMEOUT_EXC))
    def send(self, title, content, level) -> bool:
        if not self.is_configured():
            logger.warning("飞书 Webhook 未配置")
            return False
        if not (self._webhook or "").startswith(("http://", "https://")):
            logger.error(f"飞书 Webhook 地址格式错误（需以 http:// 或 https:// 开头）: {self._webhook!r}")
            return False
        resp = httpx.post(self._webhook, json=self.build_payload(title, content, level), timeout=10)
        result = resp.json()
        if result.get("code") != 0:
            logger.error(f"飞书通知失败: {result.get('msg')}")
            return False
        return True


class TelegramNotifier(Notifier):
    """Telegram Bot"""

    name = "telegram"

    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None, config=None):
        if config and hasattr(config, "notify"):
            bot_token = bot_token or getattr(config.notify, "telegram_bot_token", None)
            chat_id = chat_id or getattr(config.notify, "telegram_chat_id", None)
        self._bot_token = bot_token
        self._chat_id = chat_id

    def is_configured(self) -> bool:
        return bool(self._bot_token and self._chat_id and "${" not in (self._bot_token or ""))

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=10), retry=retry_if_exception_type(_TIMEOUT_EXC))
    def send(self, title, content, level) -> bool:
        if not self.is_configured():
            logger.warning("Telegram Bot 未配置")
            return False
        emoji = NotifyTool.LEVEL_EMOJI.get(level, "")
        text = f"{emoji} *{title}*\n\n{content}"
        resp = httpx.post(
            f"https://api.telegram.org/bot{self._bot_token}/sendMessage",
            json={"chat_id": self._chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=10,
        )
        result = resp.json()
        if not result.get("ok"):
            logger.error(f"Telegram 通知失败: {result}")
            return False
        return True


class SlackNotifier(Notifier):
    """Slack incoming webhook"""

    name = "slack"

    def __init__(self, webhook: Optional[str] = None, config=None):
        if config and hasattr(config, "notify"):
            webhook = webhook or getattr(config.notify, "slack_webhook", None)
        self._webhook = webhook

    def is_configured(self) -> bool:
        return bool(self._webhook and self._webhook.strip() and "${" not in (self._webhook or ""))

    COLOR_MAP = {"info": "#2eb886", "warning": "#f2c744", "error": "#e01e5a", "critical": "#d0021b"}

    def build_payload(self, title, content, level):
        return {
            "attachments": [
                {"color": self.COLOR_MAP.get(level, "#2eb886"), "title": title, "text": content}
            ]
        }

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=10), retry=retry_if_exception_type(_TIMEOUT_EXC))
    def send(self, title, content, level) -> bool:
        if not self.is_configured():
            logger.warning("Slack Webhook 未配置")
            return False
        resp = httpx.post(self._webhook, json=self.build_payload(title, content, level), timeout=10)
        return resp.status_code == 200


class NotifyRouter:
    """统一通知路由：channel → sender"""

    def __init__(self, senders: Dict[str, Notifier]):
        self._senders = senders

    def channel_names(self) -> list:
        return list(self._senders.keys())

    def send(self, title, content, level, channels) -> Dict[str, bool]:
        results = {}
        for ch in channels:
            sender = self._senders.get(ch)
            if not sender:
                results[ch] = False
                logger.warning(f"未知通知渠道: {ch}")
                continue
            try:
                results[ch] = sender.send(title, content, level)
            except Exception as e:
                results[ch] = False
                logger.error(f"通知渠道 [{ch}] 失败: {e}")
        return results


class NotifyTool(BaseTool):
    """通知发送工具 - 多渠道（企微/钉钉/飞书/Telegram/Slack/邮件）"""

    name = "send_notification"
    description = "发送告警通知到企业微信/钉钉/飞书/Telegram/Slack（支持 Markdown）"
    parameters = [
        ToolParameter(name="title", type="string", description="通知标题"),
        ToolParameter(name="content", type="string", description="通知内容（支持 Markdown 格式）"),
        ToolParameter(
            name="level",
            type="string",
            description="告警级别: info, warning, error, critical",
            required=False,
            default="warning"
        ),
        ToolParameter(
            name="channel",
            type="string",
            description="通知渠道: wecom, dingtalk, lark, telegram, slack, all(全部已配置)",
            required=False,
            default="all"
        ),
    ]

    LEVEL_EMOJI = {
        'info': 'ℹ️',
        'warning': '⚠️',
        'error': '❌',
        'critical': '🔴',
    }

    def __init__(self, config=None):
        self._router = NotifyRouter({
            "wecom": WeComNotifier(config=config),
            "dingtalk": DingTalkNotifier(config=config),
            "lark": FeishuNotifier(config=config),
            "telegram": TelegramNotifier(config=config),
            "slack": SlackNotifier(config=config),
        })
        self._email_tool = None

    def _set_email_tool(self, email_tool):
        """延迟注入邮件工具（避免循环依赖）"""
        self._email_tool = email_tool

    def execute(self, **kwargs) -> ToolResult:
        title = kwargs['title']
        content = kwargs['content']
        level = kwargs.get('level', 'warning')
        channel = kwargs.get('channel', 'all')

        if channel == "all":
            channels = [c for c, s in self._router._senders.items() if s.is_configured()]
            if not channels:
                channels = ["wecom", "dingtalk"]
        else:
            channels = [channel]

        results = self._router.send(title, content, level, channels)

        # 邮件渠道
        if channel in ("all", "email") and self._email_tool and self._email_tool.is_configured:
            try:
                email_ok = self._email_tool.send_alert(
                    subject=title, body=content, level=level,
                    to_addrs=self._email_tool.config_to_addrs if hasattr(self._email_tool, "config_to_addrs") else None,
                    attachment_path=None,
                )
                results["email"] = bool(email_ok and email_ok.get("success"))
            except Exception as e:
                results["email"] = False
                logger.error(f"邮件通知失败: {e}")

        all_success = all(results.values()) if results else False
        return ToolResult(
            success=all_success,
            data={"results": results, "level": level, "channels": list(results.keys())},
            metadata={"title": title, "channel": channel}
        )