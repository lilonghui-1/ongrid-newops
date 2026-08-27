"""依赖注入 - 数据库会话、用户认证、权限校验

为 FastAPI 路由提供可复用的依赖项：
- get_db              : 数据库会话
- get_current_user    : 解析 JWT 获取当前用户
- get_current_active_user : 仅允许活跃用户
- require_admin       : 要求 admin 角色（向后兼容）
- require_operator    : 要求 admin 或 operator 角色（向后兼容）
- require_permission  : 基于 RBAC 的细粒度权限校验
- get_user_permissions: 获取用户全部权限码集合
"""

from typing import Callable, Generator, Set

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models.role_permission import RolePermission
from ..models.user import User
from ..models.user_role import UserRole
from .security import decode_token

# OAuth2 密码流令牌端点
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


# ---------------------------------------------------------------------------
# 数据库会话
# ---------------------------------------------------------------------------
def get_db() -> Generator[Session, None, None]:
    """获取数据库会话，请求结束后自动关闭。

    Yields:
        SQLAlchemy Session 实例
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 用户认证
# ---------------------------------------------------------------------------
def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """解析 JWT 令牌并返回对应的用户对象。

    Args:
        token: Bearer 令牌（由 oauth2_scheme 自动从 Authorization 头提取）
        db: 数据库会话

    Returns:
        当前登录的 User 对象

    Raises:
        HTTPException 401: 令牌无效或用户不存在
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无法验证凭证",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception
    return user


def get_current_active_user(user: User = Depends(get_current_user)) -> User:
    """获取当前活跃用户，已被禁用的用户将被拒绝。

    Args:
        user: 由 get_current_user 注入的当前用户

    Returns:
        活跃的 User 对象

    Raises:
        HTTPException 400: 用户已被禁用
    """
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户已被禁用")
    return user


# ---------------------------------------------------------------------------
# 权限校验
# ---------------------------------------------------------------------------
def require_admin(user: User = Depends(get_current_user)) -> User:
    """要求当前用户具备 admin 角色。

    Raises:
        HTTPException 403: 权限不足
    """
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足，需要管理员权限",
        )
    return user


def require_operator(user: User = Depends(get_current_user)) -> User:
    """要求当前用户具备 admin 或 operator 角色。

    Raises:
        HTTPException 403: 权限不足
    """
    if user.role not in ("admin", "operator"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足，需要操作员权限",
        )
    return user


# ---------------------------------------------------------------------------
# RBAC 权限校验（新）
# ---------------------------------------------------------------------------
def get_user_permissions(user: User, db: Session) -> Set[str]:
    """获取用户通过所有角色积累的全部权限码集合。

    向后兼容：如果用户旧 role 字段为 admin，返回全部权限；
    为 operator，返回除 user:manage/role:manage 外的全部权限；
    为 viewer，返回全部 read 权限。
    """
    # 先查 RBAC 表
    role_ids = (
        db.query(UserRole.role_id)
        .filter(UserRole.user_id == user.id)
        .all()
    )
    if role_ids:
        perms = (
            db.query(RolePermission.permission)
            .filter(RolePermission.role_id.in_([r[0] for r in role_ids]))
            .distinct()
            .all()
        )
        result = {p[0] for p in perms}
        # 如果有 RBAC 权限就使用它，同时也检查旧角色字段做兜底
        if result:
            return result

    # 向后兼容：无 RBAC 角色时按旧 role 字段推断
    from ..schemas.role import ALL_PERMISSIONS

    if user.role == "admin":
        return set(ALL_PERMISSIONS)
    elif user.role == "operator":
        return set(ALL_PERMISSIONS) - {"user:manage", "role:manage"}
    else:
        return {p for p in ALL_PERMISSIONS if p.endswith(":read")}


def require_permission(permission: str) -> Callable:
    """生成一个权限校验依赖，检查当前用户是否拥有指定权限码。

    用法::

        @router.post("/servers/{host}/power", dependencies=[Depends(require_permission("server:write"))])
        def power_on(host: str, ...):
            ...

    或直接在路由参数中注入::

        def endpoint(user: User = Depends(require_permission("server:write"))):
            ...
    """
    def _check(
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        # 先检查活跃状态
        if not user.is_active:
            raise HTTPException(status_code=400, detail="用户已被禁用")
        perms = get_user_permissions(user, db)
        if permission not in perms:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"权限不足，需要权限: {permission}",
            )
        return user

    return _check
