"""告警记录模型"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class Alert(Base):
    """告警记录表

    字段：
    - id: 主键自增
    - server_host: 服务器主机，索引
    - alert_type: 告警类型
    - severity: 严重级别（warning / critical）
    - message: 告警消息（Text）
    - threshold: 阈值（Float，可空）
    - current_value: 当前值（Float，可空）
    - is_resolved: 是否已解决（Boolean，默认 False）
    - resolved_at: 解决时间（DateTime，可空）
    - created_at: 创建时间，索引
    """

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    server_host: Mapped[str] = mapped_column(
        String(128), index=True, nullable=False
    )
    alert_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(
        String(32), nullable=False, default="warning"
    )
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    threshold: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    current_value: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )
    is_resolved: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), index=True, nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<Alert(id={self.id}, server_host={self.server_host!r}, "
            f"alert_type={self.alert_type!r}, severity={self.severity!r}, "
            f"is_resolved={self.is_resolved})>"
        )
