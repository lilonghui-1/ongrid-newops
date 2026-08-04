"""认证路由 - 登录、令牌刷新、用户信息、登出

端点：
- POST /login     : 用户名密码登录，返回 access_token / refresh_token
- POST /refresh   : 使用 refresh_token 换取新的令牌对
- GET  /me        : 获取当前登录用户信息
- POST /logout    : 登出（无服务端状态，仅返回提示）
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError
from sqlalchemy.orm import Session

from ..core.deps import get_current_user
from ..core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from ..database import get_db
from ..models.user import User
from ..schemas.auth import LoginRequest, RefreshTokenRequest, TokenResponse, UserResponse

router = APIRouter(tags=["认证"])


@router.post("/login", response_model=TokenResponse, summary="用户登录")
def login(request: LoginRequest, db: Session = Depends(get_db)):
    """用户名密码登录，验证成功后返回 JWT 令牌对。

    Args:
        request: 包含 username 和 password 的登录请求
        db: 数据库会话

    Returns:
        TokenResponse: access_token + refresh_token + 用户信息

    Raises:
        HTTPException 401: 用户名或密码错误
        HTTPException 403: 用户已被禁用
    """
    user = db.query(User).filter(User.username == request.username).first()
    if not user or not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户已被禁用，请联系管理员",
        )

    # 更新最后登录时间
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()

    token_data = {"sub": user.username, "role": user.role}
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        username=user.username,
        role=user.role,
    )


@router.post("/refresh", response_model=TokenResponse, summary="刷新令牌")
def refresh_token(request: RefreshTokenRequest, db: Session = Depends(get_db)):
    """使用 refresh_token 换取新的令牌对。

    Args:
        request: 包含 refresh_token 的请求
        db: 数据库会话

    Returns:
        TokenResponse: 新的 access_token + refresh_token

    Raises:
        HTTPException 401: refresh_token 无效或过期
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="刷新令牌无效或已过期",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_token(request.refresh_token)
    except JWTError:
        raise credentials_exception

    # 校验令牌类型
    if payload.get("type") != "refresh":
        raise credentials_exception

    username: str = payload.get("sub")
    if not username:
        raise credentials_exception

    user = db.query(User).filter(User.username == username).first()
    if not user or not user.is_active:
        raise credentials_exception

    token_data = {"sub": user.username, "role": user.role}
    new_access_token = create_access_token(token_data)
    new_refresh_token = create_refresh_token(token_data)

    return TokenResponse(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",
        username=user.username,
        role=user.role,
    )


@router.get("/me", response_model=UserResponse, summary="获取当前用户信息")
def get_me(current_user: User = Depends(get_current_user)):
    """返回当前登录用户的基本信息。

    Args:
        current_user: 由 get_current_user 依赖注入的当前用户

    Returns:
        UserResponse: 用户信息
    """
    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        display_name=current_user.display_name or current_user.username,
        role=current_user.role,
        is_active=current_user.is_active,
        last_login_at=current_user.last_login_at,
    )


@router.post("/logout", summary="用户登出")
def logout():
    """用户登出。

    JWT 为无状态令牌，服务端不维护会话，因此登出仅返回提示信息。
    客户端应清除本地存储的令牌。
    """
    return {"message": "已登出"}
