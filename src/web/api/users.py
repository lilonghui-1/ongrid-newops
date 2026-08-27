"""用户管理路由 - 用户 CRUD、停用/启用、密码重置

端点：
- GET   /          获取用户列表（管理员）
- POST  /          创建用户（管理员）
- PUT   /{id}      修改用户信息（管理员）
- PATCH /{id}/toggle  启用/停用用户（管理员）
- PUT   /{id}/password  重置用户密码（管理员）
- PUT   /me/password    修改自己的密码（已登录用户）
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..core.deps import get_current_active_user, require_admin
from ..core.security import get_password_hash, verify_password
from ..database import get_db
from ..models.user import User
from ..schemas.user import (
    PasswordChangeRequest,
    UserCreateRequest,
    UserListResponse,
    UserResponse,
    UserUpdateRequest,
)

router = APIRouter(tags=["用户管理"])

VALID_ROLES = {"admin", "operator", "viewer"}


def _user_to_response(user: User) -> UserResponse:
    """将 User ORM 对象转为响应模型"""
    return UserResponse(
        id=user.id,
        username=user.username,
        display_name=user.display_name or user.username,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )


@router.get("", response_model=UserListResponse, summary="获取用户列表")
def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """获取所有用户列表（仅管理员）。"""
    users = db.query(User).order_by(User.id).all()
    return UserListResponse(
        total=len(users),
        users=[_user_to_response(u) for u in users],
    )


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED, summary="创建用户")
def create_user(
    request: UserCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """创建新用户（仅管理员）。"""
    # 校验角色
    if request.role not in VALID_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效的角色 '{request.role}'，可选: admin / operator / viewer",
        )

    # 检查用户名是否已存在
    existing = db.query(User).filter(User.username == request.username).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"用户名 '{request.username}' 已存在",
        )

    user = User(
        username=request.username,
        password_hash=get_password_hash(request.password),
        display_name=request.display_name or request.username,
        role=request.role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _user_to_response(user)


@router.put("/{user_id}", response_model=UserResponse, summary="修改用户信息")
def update_user(
    user_id: int,
    request: UserUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """修改用户信息：显示名称、角色、启用状态（仅管理员）。"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"用户 ID {user_id} 不存在",
        )

    # 防止最后一个管理员被降级或停用
    if request.role is not None or request.is_active is False:
        is_last_admin = (
            user.role == "admin"
            and user.is_active
            and db.query(User).filter(User.role == "admin", User.is_active.is_(True)).count() <= 1
        )
        if is_last_admin:
            if request.is_active is False:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="不能停用最后一个管理员账户",
                )
            if request.role is not None and request.role != "admin":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="不能将最后一个管理员降级",
                )

    if request.role is not None:
        if request.role not in VALID_ROLES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"无效的角色 '{request.role}'，可选: admin / operator / viewer",
            )
        user.role = request.role

    if request.display_name is not None:
        user.display_name = request.display_name

    if request.is_active is not None:
        user.is_active = request.is_active

    db.commit()
    db.refresh(user)
    return _user_to_response(user)


@router.patch("/{user_id}/toggle", response_model=UserResponse, summary="启用/停用用户")
def toggle_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """切换用户启用状态（仅管理员）。"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"用户 ID {user_id} 不存在",
        )

    # 防止停用最后一个管理员
    if user.role == "admin" and user.is_active:
        active_admins = db.query(User).filter(
            User.role == "admin", User.is_active.is_(True)
        ).count()
        if active_admins <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="不能停用最后一个管理员账户",
            )

    user.is_active = not user.is_active
    db.commit()
    db.refresh(user)
    return _user_to_response(user)


@router.put("/{user_id}/password", summary="重置用户密码")
def reset_password(
    user_id: int,
    request: PasswordChangeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """管理员重置指定用户的密码（仅管理员，无需旧密码）。"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"用户 ID {user_id} 不存在",
        )

    user.password_hash = get_password_hash(request.new_password)
    db.commit()
    return {"message": f"用户 '{user.username}' 的密码已重置"}


@router.put("/me/password", summary="修改自己的密码")
def change_my_password(
    request: PasswordChangeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """已登录用户修改自己的密码（需提供旧密码）。"""
    if not request.old_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请提供旧密码",
        )

    if not verify_password(request.old_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="旧密码不正确",
        )

    current_user.password_hash = get_password_hash(request.new_password)
    db.commit()
    return {"message": "密码修改成功"}


# ---------------------------------------------------------------------------
# 用户-角色分配（RBAC）
# ---------------------------------------------------------------------------
from ..models.role import Role
from ..models.user_role import UserRole
from ..schemas.role import UserRoleAssignRequest


@router.get("/{user_id}/roles", summary="获取用户角色列表")
def get_user_roles(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取指定用户分配的所有角色。"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"用户 ID {user_id} 不存在")
    role_ids = (
        db.query(UserRole.role_id)
        .filter(UserRole.user_id == user_id)
        .all()
    )
    roles = db.query(Role).filter(Role.id.in_([r[0] for r in role_ids])).all()
    return {
        "user_id": user_id,
        "roles": [
            {"id": r.id, "name": r.name, "description": r.description or "", "is_system": r.is_system}
            for r in roles
        ],
    }


@router.put("/{user_id}/roles", summary="设置用户角色")
def set_user_roles(
    user_id: int,
    request: UserRoleAssignRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """设置用户的角色列表（覆盖式：先删后插）。仅管理员可操作。"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"用户 ID {user_id} 不存在")

    # 校验 role_id 有效性
    valid_roles = db.query(Role).filter(Role.id.in_(request.role_ids)).all()
    if len(valid_roles) != len(request.role_ids):
        invalid_ids = set(request.role_ids) - {r.id for r in valid_roles}
        raise HTTPException(status_code=400, detail=f"无效的角色 ID: {invalid_ids}")

    # 覆盖式更新
    db.query(UserRole).filter(UserRole.user_id == user_id).delete()
    for rid in request.role_ids:
        db.add(UserRole(user_id=user_id, role_id=rid))
    db.commit()
    return {"message": f"用户 '{user.username}' 的角色已更新", "role_ids": request.role_ids}
