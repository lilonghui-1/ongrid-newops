"""自愈规则模型 - 自动处理已诊断问题的规则"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class HealRule(Base):
    """自愈规则表

    存储自愈规则定义，每条规则包含触发条件、执行操作和确认级别。

    字段：
    - id: 主键自增
    - name: 规则名称（唯一标识）
    - condition: 触发条件表达式
    - description: 规则描述
    - actions: 执行操作列表（JSON 数组）
    - enabled: 是否启用
    - created_at: 创建时间
    - updated_at: 更新时间
    """

    __tablename__ = "heal_rules"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    condition: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    actions: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<HealRule(id={self.id}, name={self.name!r}, enabled={self.enabled})>"