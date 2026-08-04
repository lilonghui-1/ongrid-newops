"""AI 对话历史模型"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class ChatHistory(Base):
    """AI 对话历史表

    字段：
    - id: 主键自增
    - session_id: 会话 ID，索引
    - user_id: 用户 ID，索引
    - role: 角色（user / assistant）
    - content: 消息内容（Text）
    - model: 模型名称
    - context_type: 上下文类型（可空）
    - context_content: 上下文内容（Text，可空）
    - created_at: 创建时间
    """

    __tablename__ = "chat_histories"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(128), index=True, nullable=False
    )
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, index=True, nullable=True
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    context_type: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    context_content: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<ChatHistory(id={self.id}, session_id={self.session_id!r}, "
            f"role={self.role!r})>"
        )
