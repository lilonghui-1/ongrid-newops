"""角色管理路由 - 角色 CRUD、权限分配、资源分配

端点：
- GET    /                  获取角色列表
- POST   /                  创建角色
- PUT    /{id}              修改角色信息
- DELETE /{id}              删除角色（系统角色不可删）
- GET    /{id}/permissions 获取角色权限
- PUT    /{id}/permissions  设置角色权限
- GET    /{id}/resources    获取角色资源
- PUT    /{id}/resources    设置角色资源
- GET    /permissions/all  获取所有可用权限码
- GET    /{id}/users        获取角色下的用户列表
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..core.deps import get_current_active_user, require_permission
from ..database import get_db
from ..models.role import Role
from ..models.role_permission import RolePermission
from ..models.role_resource import RoleResource
from ..models.user import User
from ..models.user_role import UserRole
from ..schemas.role import (
    ALL_PERMISSIONS,
    PERMISSION_GROUPS,
    RESOURCE_TYPES,
    PermissionAssignRequest,
    ResourceAssignRequest,
    RoleCreateRequest,
    RoleListResponse,
    RoleResponse,
    RoleUpdateRequest,
)
from ..schemas.user import UserResponse

router = APIRouter(tags=["角色管理"])


def _role_to_response(db: Session, role: Role) -> RoleResponse:
    """将 Role ORM 对象转为响应模型（含权限和资源）"""
    perms = (
        db.query(RolePermission.permission)
        .filter(RolePermission.role_id == role.id)
        .all()
    )
    resources_q = (
        db.query(RoleResource)
        .filter(RoleResource.role_id == role.id)
        .all()
    )
    resources = [
        {"resource_type": r.resource_type, "resource_id": r.resource_id}
        for r in resources_q
    ]
    user_count = db.query(UserRole).filter(UserRole.role_id == role.id).count()
    return RoleResponse(
        id=role.id,
        name=role.name,
        description=role.description or "",
        is_system=role.is_system,
        permissions=[p[0] for p in perms],
        resources=resources,
        user_count=user_count,
        created_at=role.created_at,
    )


@router.get("/permissions/all", summary="获取所有可用权限码")
def get_all_permissions(
    current_user: User = Depends(get_current_active_user),
):
    """返回所有可用权限码及分组信息，供前端勾选。"""
    return {
        "permissions": ALL_PERMISSIONS,
        "groups": PERMISSION_GROUPS,
    }


@router.get("", response_model=RoleListResponse, summary="获取角色列表")
def list_roles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    roles = db.query(Role).order_by(Role.id).all()
    return RoleListResponse(
        total=len(roles),
        roles=[_role_to_response(db, r) for r in roles],
    )


@router.post("", response_model=RoleResponse, status_code=status.HTTP_201_CREATED, summary="创建角色")
def create_role(
    request: RoleCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("role:manage")),
):
    existing = db.query(Role).filter(Role.name == request.name).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"角色名 '{request.name}' 已存在")
    role = Role(name=request.name, description=request.description)
    db.add(role)
    db.commit()
    db.refresh(role)
    return _role_to_response(db, role)


@router.put("/{role_id}", response_model=RoleResponse, summary="修改角色信息")
def update_role(
    role_id: int,
    request: RoleUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("role:manage")),
):
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail=f"角色 ID {role_id} 不存在")
    if request.name is not None and request.name != role.name:
        existing = db.query(Role).filter(Role.name == request.name).first()
        if existing:
            raise HTTPException(status_code=409, detail=f"角色名 '{request.name}' 已存在")
        role.name = request.name
    if request.description is not None:
        role.description = request.description
    db.commit()
    db.refresh(role)
    return _role_to_response(db, role)


@router.delete("/{role_id}", summary="删除角色")
def delete_role(
    role_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("role:manage")),
):
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail=f"角色 ID {role_id} 不存在")
    if role.is_system:
        raise HTTPException(status_code=400, detail="系统内置角色不可删除")
    # 级联删除关联
    db.query(UserRole).filter(UserRole.role_id == role_id).delete()
    db.query(RolePermission).filter(RolePermission.role_id == role_id).delete()
    db.query(RoleResource).filter(RoleResource.role_id == role_id).delete()
    db.delete(role)
    db.commit()
    return {"message": f"角色 '{role.name}' 已删除"}


@router.get("/{role_id}/permissions", summary="获取角色权限")
def get_role_permissions(
    role_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail=f"角色 ID {role_id} 不存在")
    perms = (
        db.query(RolePermission.permission)
        .filter(RolePermission.role_id == role_id)
        .all()
    )
    return {"role_id": role_id, "permissions": [p[0] for p in perms]}


@router.put("/{role_id}/permissions", summary="设置角色权限")
def set_role_permissions(
    role_id: int,
    request: PermissionAssignRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("role:manage")),
):
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail=f"角色 ID {role_id} 不存在")
    # 校验权限码
    invalid = [p for p in request.permissions if p not in ALL_PERMISSIONS]
    if invalid:
        raise HTTPException(status_code=400, detail=f"无效的权限码: {invalid}")
    # 全删后全插（简单可靠的覆盖策略）
    db.query(RolePermission).filter(RolePermission.role_id == role_id).delete()
    for perm in request.permissions:
        db.add(RolePermission(role_id=role_id, permission=perm))
    db.commit()
    return {"message": f"角色 '{role.name}' 的权限已更新", "permissions": request.permissions}


@router.get("/{role_id}/resources", summary="获取角色资源")
def get_role_resources(
    role_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail=f"角色 ID {role_id} 不存在")
    resources = (
        db.query(RoleResource)
        .filter(RoleResource.role_id == role_id)
        .all()
    )
    return {
        "role_id": role_id,
        "resources": [
            {"resource_type": r.resource_type, "resource_id": r.resource_id}
            for r in resources
        ],
    }


@router.put("/{role_id}/resources", summary="设置角色资源")
def set_role_resources(
    role_id: int,
    request: ResourceAssignRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("role:manage")),
):
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail=f"角色 ID {role_id} 不存在")
    if request.resource_type not in RESOURCE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"无效的资源类型 '{request.resource_type}'，可选: {RESOURCE_TYPES}",
        )
    # 删除该类型旧资源，插入新的
    db.query(RoleResource).filter(
        RoleResource.role_id == role_id,
        RoleResource.resource_type == request.resource_type,
    ).delete()
    for rid in request.resource_ids:
        db.add(RoleResource(
            role_id=role_id,
            resource_type=request.resource_type,
            resource_id=str(rid),
        ))
    db.commit()
    return {
        "message": f"角色 '{role.name}' 的 {request.resource_type} 资源已更新",
        "resource_type": request.resource_type,
        "resource_ids": request.resource_ids,
    }


@router.get("/{role_id}/users", response_model=list, summary="获取角色下的用户列表")
def get_role_users(
    role_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail=f"角色 ID {role_id} 不存在")
    user_ids = (
        db.query(UserRole.user_id)
        .filter(UserRole.role_id == role_id)
        .all()
    )
    users = db.query(User).filter(User.id.in_([u[0] for u in user_ids])).all()
    return [
        UserResponse(
            id=u.id,
            username=u.username,
            display_name=u.display_name or u.username,
            role=u.role,
            is_active=u.is_active,
            created_at=u.created_at,
            last_login_at=u.last_login_at,
        )
        for u in users
    ]
