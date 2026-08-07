"""自定义配置文件定义模型"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class CustomConfig(Base):
    """自定义配置文件定义表

    存储用户通过 Web 界面新增的配置文件元数据（路径、名称、分类等），
    文件内容本身存储在远程服务器上。

    字段：
    - id: 主键自增
    - name: 配置文件名称
    - file_path: 服务器上的文件路径
    - category: 配置分类（server/database/llm/application）
    - description: 配置描述
    - created_by: 创建人
    - created_at: 创建时间
    """

    __tablename__ = "custom_configs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    category: Mapped[str] = mapped_column(
        String(32), nullable=False, default="application"
    )
    description: Mapped[Optional[str]] = mapped_column(
        String(256), nullable=True
    )
    created_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<CustomConfig(id={self.id}, name={self.name!r}, "
            f"file_path={self.file_path!r}, category={self.category!r})>"
        )
