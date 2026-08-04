"""认证请求/响应模型 (Pydantic v2)

包含登录、令牌刷新、用户信息等数据结构。
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """登录请求"""

    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")


class TokenResponse(BaseModel):
    """登录成功后返回的令牌响应"""

    access_token: str = Field(..., description="访问令牌")
    refresh_token: str = Field(..., description="刷新令牌")
    token_type: str = Field("bearer", description="令牌类型")
    username: str = Field(..., description="用户名")
    role: str = Field(..., description="用户角色")


class RefreshTokenRequest(BaseModel):
    """刷新令牌请求"""

    refresh_token: str = Field(..., description="刷新令牌")


class UserResponse(BaseModel):
    """用户信息响应"""

    id: int = Field(..., description="用户 ID")
    username: str = Field(..., description="用户名")
    display_name: str = Field(..., description="显示名称")
    role: str = Field(..., description="用户角色")
    is_active: bool = Field(..., description="是否启用")
    last_login_at: Optional[datetime] = Field(None, description="最后登录时间")
