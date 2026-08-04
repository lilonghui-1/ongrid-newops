"""审计日志模型"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class AuditLog(Base):
    """审计日志表

    字段：
    - id: 主键自增
    - user_id: 用户 ID，索引
    - username: 用户名
    - action: 操作动作
    - target: 操作目标
    - method: HTTP 方法
    - path: 请求路径
    - status_code: HTTP 状态码
    - ip_address: 请求来源 IP
    - detail: 详情（Text）
    - created_at: 创建时间，索引
    """

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, index=True, nullable=True
    )
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    target: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    method: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    status_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), index=True, nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<AuditLog(id={self.id}, username={self.username!r}, "
            f"action={self.action!r})>"
        )
