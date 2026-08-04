"""配置备份模型"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class ConfigBackup(Base):
    """配置备份表

    字段：
    - id: 主键自增
    - server_host: 服务器主机，索引
    - file_path: 配置文件路径
    - original_content: 原始内容（Text）
    - new_content: 修改后内容（Text，可空）
    - backup_content: 备份内容（Text）
    - version: 版本号
    - modified_by: 修改人
    - modified_at: 修改时间
    - is_rolled_back: 是否已回滚（Boolean，默认 False）
    """

    __tablename__ = "config_backups"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    server_host: Mapped[str] = mapped_column(
        String(128), index=True, nullable=False
    )
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    original_content: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    new_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    backup_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    modified_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    modified_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    is_rolled_back: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<ConfigBackup(id={self.id}, server_host={self.server_host!r}, "
            f"file_path={self.file_path!r}, version={self.version!r})>"
        )
