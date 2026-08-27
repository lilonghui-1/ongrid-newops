"""角色-资源关联模型 (RBAC)

多对多关联表，一个角色可以关联多种资源（服务器/服务/配置）。
"""

from sqlalchemy import Column, ForeignKey, Integer, String, DateTime, func

from ..database import Base


class RoleResource(Base):
    """角色-资源关联

    resource_type: server / service / config
    resource_id: 对应表的主键 ID（AppService.id / CustomConfig.id）；
                 server 因无独立表，用 server_host 字符串标识
    """

    __tablename__ = "role_resources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), index=True, nullable=False)
    resource_type = Column(String(32), nullable=False, comment="server / service / config")
    resource_id = Column(String(128), nullable=False, comment="资源标识（ID 或 host）")
    created_at = Column(DateTime, nullable=False, server_default=func.now())
