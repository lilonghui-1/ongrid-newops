"""角色模型 (RBAC)

角色定义表，支持系统内置角色和自定义角色。
"""

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, func

from ..database import Base


class Role(Base):
    """角色定义"""

    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), unique=True, index=True, nullable=False)
    description = Column(String(256), nullable=True)
    is_system = Column(Boolean, default=False, nullable=False, comment="系统内置角色不可删除")
    created_at = Column(DateTime, nullable=False, server_default=func.now())
