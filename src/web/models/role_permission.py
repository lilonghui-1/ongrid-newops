"""角色-权限关联模型 (RBAC)

一个角色拥有多个功能权限码（如 server:read, service:write）。
"""

from sqlalchemy import Column, ForeignKey, Integer, String, DateTime, func

from ..database import Base


class RolePermission(Base):
    """角色-权限关联

    permission 格式: 模块:操作，如 server:read, service:write, user:manage
    """

    __tablename__ = "role_permissions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), index=True, nullable=False)
    permission = Column(String(64), nullable=False, comment="权限码，如 server:read")
    created_at = Column(DateTime, nullable=False, server_default=func.now())
