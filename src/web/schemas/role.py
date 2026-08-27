"""RBAC 角色管理请求/响应模型 (Pydantic v2)"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# ── 资源类型 ──
RESOURCE_TYPES = ["server", "service", "config"]

# ── 全部权限码 ──
ALL_PERMISSIONS = [
    "server:read",
    "server:write",
    "service:read",
    "service:write",
    "service:manage",
    "config:read",
    "config:write",
    "log:read",
    "alert:read",
    "alert:write",
    "knowledge:read",
    "knowledge:write",
    "heal:read",
    "heal:write",
    "audit:read",
    "user:manage",
    "role:manage",
]

# ── 权限分组（供前端展示）──
PERMISSION_GROUPS = [
    {
        "module": "服务器",
        "permissions": ["server:read", "server:write"],
    },
    {
        "module": "应用服务",
        "permissions": ["service:read", "service:write", "service:manage"],
    },
    {
        "module": "配置管理",
        "permissions": ["config:read", "config:write"],
    },
    {
        "module": "日志",
        "permissions": ["log:read"],
    },
    {
        "module": "告警",
        "permissions": ["alert:read", "alert:write"],
    },
    {
        "module": "知识库",
        "permissions": ["knowledge:read", "knowledge:write"],
    },
    {
        "module": "自愈规则",
        "permissions": ["heal:read", "heal:write"],
    },
    {
        "module": "审计日志",
        "permissions": ["audit:read"],
    },
    {
        "module": "系统管理",
        "permissions": ["user:manage", "role:manage"],
    },
]


# ── 角色请求/响应 ──
class RoleCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=64, description="角色名称")
    description: str = Field("", max_length=256, description="描述")


class RoleUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=64, description="角色名称")
    description: Optional[str] = Field(None, max_length=256, description="描述")


class RoleResponse(BaseModel):
    id: int
    name: str
    description: str
    is_system: bool
    permissions: List[str] = Field(default_factory=list, description="权限码列表")
    resources: List[dict] = Field(default_factory=list, description="资源列表")
    user_count: int = Field(0, description="关联用户数")
    created_at: datetime


class RoleListResponse(BaseModel):
    total: int
    roles: List[RoleResponse]


# ── 权限分配 ──
class PermissionAssignRequest(BaseModel):
    permissions: List[str] = Field(..., description="权限码列表")


# ── 资源分配 ──
class ResourceAssignRequest(BaseModel):
    resource_type: str = Field(..., description="server / service / config")
    resource_ids: List[str] = Field(..., description="资源标识列表（ID 或 host）")


# ── 用户角色分配 ──
class UserRoleAssignRequest(BaseModel):
    role_ids: List[int] = Field(..., description="角色 ID 列表")
