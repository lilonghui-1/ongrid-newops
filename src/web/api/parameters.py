"""参数管理路由 - 管理配置文件中的 ${VAR} 环境变量参数

端点：
- GET    /             : 获取参数列表（支持按分类筛选）
- POST   /             : 新增参数
- PUT    /{key}        : 更新参数
- DELETE /{key}        : 删除参数
- POST   /apply        : 应用参数到环境变量并触发配置重载
- GET    /categories   : 获取所有分类
"""

import logging
import os
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc
from sqlalchemy.orm import Session

from ..core.deps import get_current_active_user, require_admin
from ..database import get_db
from ..models.system_parameter import SystemParameter
from ..models.user import User
from ..schemas.parameter import (
    ApplyParametersResponse,
    SystemParameterCreate,
    SystemParameterListResponse,
    SystemParameterResponse,
    SystemParameterUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["参数管理"])

# 预设分类
CATEGORIES = [
    {"value": "ssh", "label": "SSH 连接"},
    {"value": "database", "label": "数据库"},
    {"value": "llm", "label": "LLM 模型"},
    {"value": "email", "label": "邮件通知"},
    {"value": "notify", "label": "即时通知"},
    {"value": "web", "label": "Web 平台"},
    {"value": "log_platform", "label": "日志平台"},
    {"value": "general", "label": "通用"},
]


def _param_to_response(p: SystemParameter, mask_secret: bool = True) -> SystemParameterResponse:
    """将 ORM 对象转换为响应"""
    value = p.value
    if p.is_secret and mask_secret and value:
        value = "******"
    return SystemParameterResponse(
        id=p.id,
        key=p.key,
        value=value,
        description=p.description,
        is_secret=p.is_secret,
        category=p.category,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


@router.get("/", response_model=SystemParameterListResponse, summary="获取参数列表")
def list_parameters(
    category: Optional[str] = Query(None, description="按分类筛选"),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取系统参数列表，支持按分类筛选。"""
    query = db.query(SystemParameter)
    if category:
        query = query.filter(SystemParameter.category == category)

    total = query.count()
    items = (
        query.order_by(SystemParameter.category, SystemParameter.key)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return SystemParameterListResponse(
        total=total,
        items=[_param_to_response(item) for item in items],
    )


@router.get("/categories", summary="获取参数分类列表")
def list_categories(
    current_user: User = Depends(get_current_active_user),
):
    """获取所有可用的参数分类。"""
    return CATEGORIES


@router.post("/", response_model=SystemParameterResponse, summary="新增参数")
def create_parameter(
    request: SystemParameterCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """新增一个系统参数。"""
    existing = db.query(SystemParameter).filter(SystemParameter.key == request.key).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"参数 '{request.key}' 已存在",
        )

    param = SystemParameter(
        key=request.key,
        value=request.value,
        description=request.description,
        is_secret=request.is_secret,
        category=request.category,
    )
    db.add(param)
    db.commit()
    db.refresh(param)

    logger.info(f"新增参数: {request.key}，操作人: {current_user.username}")
    return _param_to_response(param, mask_secret=False)


@router.put("/{key}", response_model=SystemParameterResponse, summary="更新参数")
def update_parameter(
    key: str,
    request: SystemParameterUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """更新指定参数的值。"""
    param = db.query(SystemParameter).filter(SystemParameter.key == key).first()
    if not param:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"参数 '{key}' 不存在",
        )

    param.value = request.value
    if request.description is not None:
        param.description = request.description
    if request.is_secret is not None:
        param.is_secret = request.is_secret
    if request.category is not None:
        param.category = request.category

    db.commit()
    db.refresh(param)

    logger.info(f"更新参数: {key}，操作人: {current_user.username}")
    return _param_to_response(param, mask_secret=False)


@router.delete("/{key}", summary="删除参数")
def delete_parameter(
    key: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """删除指定参数。"""
    param = db.query(SystemParameter).filter(SystemParameter.key == key).first()
    if not param:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"参数 '{key}' 不存在",
        )

    db.delete(param)
    db.commit()

    logger.info(f"删除参数: {key}，操作人: {current_user.username}")
    return {"success": True, "message": f"参数 '{key}' 已删除"}


@router.post("/apply", response_model=ApplyParametersResponse, summary="应用参数到配置")
def apply_parameters(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """将所有参数应用到环境变量并触发配置热重载。

    流程：
    1. 从数据库读取所有参数
    2. 注入到 os.environ
    3. 触发配置热重载
    """
    params = db.query(SystemParameter).all()
    applied = 0
    for p in params:
        if p.value is not None:
            os.environ[p.key] = p.value
            applied += 1

    logger.info(f"已应用 {applied} 个参数到环境变量，操作人: {current_user.username}")

    # 触发配置热重载
    from ..core.config_manager import AppConfigManager
    manager = AppConfigManager.get_instance()
    result = manager.reload_config()

    return ApplyParametersResponse(
        success=result["success"],
        message=f"已应用 {applied} 个参数" + ("，配置已热重载" if result["success"] else f"，热重载失败: {result['message']}"),
        applied_count=applied,
    )
