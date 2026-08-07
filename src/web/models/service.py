"""应用服务定义模型

用于存储用户在后台维护的应用服务元数据，包括服务名称、分类、描述、端口等信息。
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class AppService(Base):
    """应用服务定义表

    存储用户通过 Web 界面维护的应用服务元数据，用于持久化管理服务信息。

    字段：
    - id: 主键自增
    - server_host: 所属服务器主机地址（关联到配置中的服务器）
    - name: 服务名称（systemctl 服务名）
    - display_name: 服务显示名称（友好名称）
    - description: 服务描述
    - category: 服务分类（web/middleware/database/application/custom）
    - port: 服务端口（可选）
    - enabled: 是否启用监控
    - created_by: 创建人
    - created_at: 创建时间
    - updated_at: 更新时间
    """

    __tablename__ = "app_services"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    server_host: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    category: Mapped[str] = mapped_column(
        String(32), nullable=False, default="application"
    )
    port: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, onupdate=func.now(), nullable=True
    )

    def __repr__(self) -> str:
        return (
            f"<AppService(id={self.id}, server_host={self.server_host!r}, "
            f"name={self.name!r}, category={self.category!r})>"
        )
