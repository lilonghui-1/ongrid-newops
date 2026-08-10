"""知识条目模型 - 运维知识库条目"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class KnowledgeEntry(Base):
    """知识条目表

    存储运维知识库中的诊断规则和处理方案。

    字段：
    - id: 主键自增
    - category: 分类（system/database/network/application）
    - symptom: 症状描述
    - possible_causes: 可能原因（JSON 数组）
    - diagnosis_steps: 诊断步骤（JSON 数组）
    - solutions: 解决方案（JSON 数组）
    - severity: 严重程度（low/medium/high/critical）
    - created_at: 创建时间
    - updated_at: 更新时间
    """

    __tablename__ = "knowledge_entries"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    symptom: Mapped[str] = mapped_column(String(256), nullable=False)
    possible_causes: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    diagnosis_steps: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    solutions: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    severity: Mapped[str] = mapped_column(String(32), nullable=False, default="medium")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<KnowledgeEntry(id={self.id}, symptom={self.symptom!r}, "
            f"category={self.category!r}, severity={self.severity!r})>"
        )