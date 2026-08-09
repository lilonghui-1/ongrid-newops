"""邮件发送工具 - 支持 SMTP SSL/TLS

支持 HTML 格式邮件、多收件人、文件附件和重试机制。
"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email.utils import formataddr
from email import encoders
from pathlib import Path
from typing import List, Optional

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from .base import BaseTool, ToolResult, ToolParameter

logger = logging.getLogger(__name__)


class EmailTool(BaseTool):
    """邮件发送工具 - SMTP 邮件发送"""

    name = "send_email"
    description = "发送告警邮件到指定收件人（支持 HTML 格式和附件）"
    parameters = [
        ToolParameter(name="subject", type="string", description="邮件主题"),
        ToolParameter(name="body", type="string", description="邮件内容（支持 HTML 格式）"),
        ToolParameter(
            name="to_addrs",
            type="string",
            description="收件人邮箱，多个用逗号分隔",
            required=False,
            default="",
        ),
        ToolParameter(
            name="attachment_path",
            type="string",
            description="附件文件路径（可选）",
            required=False,
            default="",
        ),
    ]

    # 级别颜色映射
    LEVEL_COLORS = {
        "info": "#409eff",
        "warning": "#e6a23c",
        "error": "#f56c6c",
        "critical": "#b22222",
    }

    def __init__(self, config=None):
        self._smtp_host = None
        self._smtp_port = 465
        self._smtp_user = None
        self._smtp_password = None
        self._from_addr = None
        self._to_addrs: List[str] = []
        self._use_ssl = True

        if config and hasattr(config, "email"):
            cfg = config.email
            self._smtp_host = getattr(cfg, "smtp_host", None) or self._smtp_host
            self._smtp_port = getattr(cfg, "smtp_port", 465)
            self._smtp_user = getattr(cfg, "smtp_user", None) or self._smtp_user
            self._smtp_password = getattr(cfg, "smtp_password", None) or self._smtp_password
            self._from_addr = getattr(cfg, "from_addr", None) or self._from_addr
            self._to_addrs = getattr(cfg, "to_addrs", []) or self._to_addrs
            self._use_ssl = getattr(cfg, "use_ssl", True)

    @property
    def is_configured(self) -> bool:
        """检查邮件配置是否完整"""
        return all([
            self._smtp_host,
            self._smtp_user,
            self._smtp_password,
            self._from_addr,
            self._to_addrs,
        ])

    def _build_html_body(self, subject: str, body: str, level: str = "warning") -> str:
        """构建 HTML 格式邮件正文"""
        color = self.LEVEL_COLORS.get(level, "#409eff")
        return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: 'Microsoft YaHei', Arial, sans-serif; padding: 20px; background: #f5f7fa;">
<div style="max-width: 700px; margin: 0 auto; background: #fff; border-radius: 8px; box-shadow: 0 2px 12px rgba(0,0,0,0.1); overflow: hidden;">
<div style="background: {color}; padding: 20px; text-align: center;">
<h2 style="color: #fff; margin: 0;">{subject}</h2>
</div>
<div style="padding: 24px; line-height: 1.8; color: #333;">
{body}
</div>
<div style="padding: 16px 24px; background: #f5f7fa; border-top: 1px solid #e6e6e6; font-size: 12px; color: #999; text-align: center;">
<p>此邮件由 Ops Agent 运维系统自动发出，请勿直接回复。</p>
<p>发送时间: <span id="send-time"></span></p>
</div>
</div>
</body>
</html>"""

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, max=10),
        retry=retry_if_exception_type(
            (smtplib.SMTPException, OSError)
        ),
    )
    def _send(
        self,
        subject: str,
        body: str,
        to_addrs: Optional[List[str]] = None,
        attachment_path: Optional[str] = None,
        level: str = "warning",
    ) -> bool:
        """执行邮件发送

        Args:
            subject: 邮件主题
            body: 邮件正文（纯文本或 HTML）
            to_addrs: 收件人列表，不传则使用默认配置
            attachment_path: 附件路径
            level: 告警级别，用于控制主题颜色

        Returns:
            bool: 发送是否成功
        """
        if not self.is_configured:
            logger.error("邮件配置不完整，跳过发送")
            return False

        recipients = to_addrs or self._to_addrs
        if not recipients:
            logger.warning("收件人列表为空，跳过发送")
            return False

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = formataddr(("Ops Agent", self._from_addr))
        msg["To"] = ", ".join(recipients)

        # HTML 正文
        html_content = self._build_html_body(subject, body, level)
        msg.attach(MIMEText(html_content, "html", "utf-8"))

        # 附件（可选）
        if attachment_path:
            path = Path(attachment_path)
            if path.exists() and path.is_file():
                with open(path, "rb") as f:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    f"attachment; filename={path.name}",
                )
                msg.attach(part)
            else:
                logger.warning(f"附件不存在，跳过: {attachment_path}")

        # 发送
        if self._use_ssl:
            with smtplib.SMTP_SSL(
                self._smtp_host, self._smtp_port, timeout=15
            ) as server:
                server.login(self._smtp_user, self._smtp_password)
                server.sendmail(self._from_addr, recipients, msg.as_string())
        else:
            with smtplib.SMTP(
                self._smtp_host, self._smtp_port, timeout=15
            ) as server:
                server.starttls()
                server.login(self._smtp_user, self._smtp_password)
                server.sendmail(self._from_addr, recipients, msg.as_string())

        logger.info(
            f"邮件发送成功: subject={subject!r}, to={recipients}, "
            f"attachment={attachment_path or '无'}"
        )
        return True

    def execute(self, **kwargs) -> ToolResult:
        """执行邮件发送（工具接口）"""
        subject = kwargs["subject"]
        body = kwargs["body"]
        to_addrs_str = kwargs.get("to_addrs", "")
        attachment_path = kwargs.get("attachment_path", "")

        if to_addrs_str:
            to_addrs = [a.strip() for a in to_addrs_str.split(",") if a.strip()]
        else:
            to_addrs = None

        try:
            success = self._send(
                subject=subject,
                body=body,
                to_addrs=to_addrs,
                attachment_path=attachment_path or None,
                level="warning",
            )
            return ToolResult(
                success=success,
                data={
                    "subject": subject,
                    "to": to_addrs or self._to_addrs,
                    "attachment": attachment_path or None,
                },
                metadata={"tool": self.name},
            )
        except Exception as e:
            logger.error(f"邮件发送失败: {e}")
            return ToolResult(
                success=False,
                error=f"{type(e).__name__}: {str(e)}",
                metadata={"tool": self.name, "subject": subject},
            )

    def send_alert(
        self,
        subject: str,
        body: str,
        level: str = "warning",
        to_addrs: Optional[List[str]] = None,
        attachment_path: Optional[str] = None,
    ) -> dict:
        """发送告警邮件（高级接口，供调度器/API 调用）

        Returns:
            dict: {"success": bool, "message": str, "detail": dict}
        """
        try:
            success = self._send(
                subject=subject,
                body=body,
                to_addrs=to_addrs,
                attachment_path=attachment_path,
                level=level,
            )
            return {
                "success": success,
                "message": "邮件发送成功" if success else "邮件发送失败",
                "detail": {
                    "subject": subject,
                    "to": to_addrs or self._to_addrs,
                    "level": level,
                },
            }
        except Exception as e:
            logger.error(f"告警邮件发送失败: {e}")
            return {
                "success": False,
                "message": f"邮件发送失败: {e}",
                "detail": {"subject": subject, "error": str(e)},
            }