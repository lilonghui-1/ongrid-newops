"""邮件发送记录模型"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class EmailLog(Base):
    """邮件发送记录表

    字段：
    - id: 主键自增
    - subject: 邮件主题
    - body: 邮件内容（HTML）
    - to_addrs: 收件人列表（逗号分隔）
    - attachment: 附件路径（可选）
    - status: 发送状态（success / failed）
    - error_msg: 错误信息（可选）
    - created_at: 发送时间
    """

    __tablename__ = "email_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    subject: Mapped[str] = mapped_column(String(256), nullable=False)
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    to_addrs: Mapped[str] = mapped_column(String(512), nullable=False)
    attachment: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="success"
    )
    error_msg: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<EmailLog(id={self.id}, subject={self.subject!r}, "
            f"status={self.status!r}, to={self.to_addrs!r})>"
        )