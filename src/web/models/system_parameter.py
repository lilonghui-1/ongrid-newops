"""系统参数模型 - 管理 ${VAR} 占位符对应的值"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class SystemParameter(Base):
    """系统参数表

    用于管理配置文件中 ${VAR} 占位符对应的值。
    配置加载时会自动将数据库中的参数注入到 os.environ。

    字段：
    - id: 主键自增
    - key: 参数名（与配置文件中的 ${KEY} 对应）
    - value: 参数值
    - description: 参数描述
    - is_secret: 是否为敏感信息（密码等），前端显示时遮蔽
    - category: 分类（ssh / database / llm / email / notify / web / general）
    - created_at: 创建时间
    - updated_at: 更新时间
    """

    __tablename__ = "system_parameters"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    category: Mapped[str] = mapped_column(String(64), default="general", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<SystemParameter(id={self.id}, key={self.key!r}, category={self.category!r})>"
