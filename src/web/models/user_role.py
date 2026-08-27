"""用户-角色关联模型 (RBAC)

多对多关联表，一个用户可以拥有多个角色。
"""

from sqlalchemy import Column, ForeignKey, Integer, DateTime, func

from ..database import Base


class UserRole(Base):
    """用户-角色关联"""

    __tablename__ = "user_roles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), index=True, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
