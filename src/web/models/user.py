"""用户模型"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class User(Base):
    """用户表

    字段：
    - id: 主键自增
    - username: 用户名，唯一索引
    - password_hash: 密码哈希
    - display_name: 显示名称
    - role: 角色（admin / operator / viewer）
    - is_active: 是否启用
    - created_at: 创建时间
    - last_login_at: 最后登录时间
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    role: Mapped[str] = mapped_column(
        String(32), nullable=False, default="viewer"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )

    def __repr__(self) -> str:
        return (
            f"<User(id={self.id}, username={self.username!r}, "
            f"role={self.role!r}, is_active={self.is_active})>"
        )
