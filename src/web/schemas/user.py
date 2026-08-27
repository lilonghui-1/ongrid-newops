"""用户管理请求/响应模型 (Pydantic v2)

包含用户创建、更新、密码修改等数据结构。
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class UserCreateRequest(BaseModel):
    """创建用户请求"""

    username: str = Field(..., min_length=2, max_length=64, description="用户名")
    password: str = Field(..., min_length=6, max_length=128, description="密码")
    display_name: str = Field("", max_length=64, description="显示名称")
    role: str = Field("viewer", description="用户角色: admin / operator / viewer")


class UserUpdateRequest(BaseModel):
    """修改用户信息请求"""

    display_name: Optional[str] = Field(None, max_length=64, description="显示名称")
    role: Optional[str] = Field(None, description="用户角色: admin / operator / viewer")
    is_active: Optional[bool] = Field(None, description="是否启用")


class PasswordChangeRequest(BaseModel):
    """修改密码请求（管理员重置 / 用户自行修改）"""

    old_password: Optional[str] = Field(None, description="旧密码（用户自行修改时必填）")
    new_password: str = Field(..., min_length=6, max_length=128, description="新密码")


class UserResponse(BaseModel):
    """用户信息响应"""

    id: int = Field(..., description="用户 ID")
    username: str = Field(..., description="用户名")
    display_name: str = Field(..., description="显示名称")
    role: str = Field(..., description="用户角色")
    is_active: bool = Field(..., description="是否启用")
    created_at: datetime = Field(..., description="创建时间")
    last_login_at: Optional[datetime] = Field(None, description="最后登录时间")


class UserListResponse(BaseModel):
    """用户列表响应"""

    total: int = Field(..., description="总数")
    users: List[UserResponse] = Field(default_factory=list, description="用户列表")
