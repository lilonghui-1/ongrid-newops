"""服务器监控指标模型"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class ServerMetric(Base):
    """服务器监控指标表

    字段：
    - id: 主键自增
    - server_host: 服务器主机，索引
    - cpu_usage: CPU 使用率（Float）
    - memory_usage: 内存使用率（Float）
    - disk_usage: 磁盘使用率（Float）
    - cpu_load_avg: CPU 负载平均值（String）
    - uptime: 运行时长（String）
    - online: 是否在线（Boolean）
    - collected_at: 采集时间，索引
    """

    __tablename__ = "server_metrics"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    server_host: Mapped[str] = mapped_column(
        String(128), index=True, nullable=False
    )
    cpu_usage: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    memory_usage: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    disk_usage: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cpu_load_avg: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    uptime: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    online: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    collected_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), index=True, nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<ServerMetric(id={self.id}, server_host={self.server_host!r}, "
            f"online={self.online})>"
        )
