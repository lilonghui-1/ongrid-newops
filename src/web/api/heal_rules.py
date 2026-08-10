"""自愈规则管理路由 - 自愈规则 CRUD

端点：
- GET    /             : 获取自愈规则列表
- POST   /             : 新增自愈规则
- GET    /{rule_id}    : 获取单条规则
- PUT    /{rule_id}    : 更新自愈规则
- DELETE /{rule_id}    : 删除自愈规则
"""

import json
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..core.deps import get_current_active_user, require_admin
from ..database import get_db
from ..models.heal_rule import HealRule
from ..models.user import User
from ..schemas.heal_rule import (
    HealRuleCreate,
    HealRuleListResponse,
    HealRuleResponse,
    HealRuleUpdate,
    RuleAction,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["自愈规则管理"])


def _parse_actions(actions_json: str) -> list:
    """解析 actions JSON 字符串为 RuleAction 列表"""
    if not actions_json:
        return []
    try:
        data = json.loads(actions_json)
        return [RuleAction(**item) for item in data]
    except (json.JSONDecodeError, TypeError):
        return []


def _rule_to_response(rule: HealRule) -> HealRuleResponse:
    """将 ORM 对象转换为响应"""
    return HealRuleResponse(
        id=rule.id,
        name=rule.name,
        condition=rule.condition,
        description=rule.description,
        actions=_parse_actions(rule.actions),
        enabled=rule.enabled,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


@router.get("/", response_model=HealRuleListResponse, summary="获取自愈规则列表")
def list_rules(
    enabled: Optional[bool] = Query(None, description="按启用状态筛选"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取自愈规则列表，支持按启用状态筛选。"""
    query = db.query(HealRule)
    if enabled is not None:
        query = query.filter(HealRule.enabled == enabled)

    total = query.count()
    items = query.order_by(HealRule.name).all()

    return HealRuleListResponse(
        total=total,
        items=[_rule_to_response(item) for item in items],
    )


@router.get("/{rule_id}", response_model=HealRuleResponse, summary="获取单条规则")
def get_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取指定自愈规则的详细信息。"""
    rule = db.query(HealRule).filter(HealRule.id == rule_id).first()
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="自愈规则不存在",
        )
    return _rule_to_response(rule)


@router.post("/", response_model=HealRuleResponse, summary="新增自愈规则")
def create_rule(
    request: HealRuleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """新增一条自愈规则。"""
    existing = db.query(HealRule).filter(HealRule.name == request.name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"自愈规则 '{request.name}' 已存在",
        )

    rule = HealRule(
        name=request.name,
        condition=request.condition,
        description=request.description,
        actions=json.dumps(
            [a.model_dump() for a in request.actions],
            ensure_ascii=False,
        ),
        enabled=True,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)

    logger.info(f"新增自愈规则: {rule.name}，操作人: {current_user.username}")
    return _rule_to_response(rule)


@router.put("/{rule_id}", response_model=HealRuleResponse, summary="更新自愈规则")
def update_rule(
    rule_id: int,
    request: HealRuleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """更新指定自愈规则的内容。"""
    rule = db.query(HealRule).filter(HealRule.id == rule_id).first()
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="自愈规则不存在",
        )

    if request.condition is not None:
        rule.condition = request.condition
    if request.description is not None:
        rule.description = request.description
    if request.actions is not None:
        rule.actions = json.dumps(
            [a.model_dump() for a in request.actions],
            ensure_ascii=False,
        )
    if request.enabled is not None:
        rule.enabled = request.enabled

    db.commit()
    db.refresh(rule)

    logger.info(f"更新自愈规则: {rule.name}，操作人: {current_user.username}")
    return _rule_to_response(rule)


@router.delete("/{rule_id}", summary="删除自愈规则")
def delete_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """删除指定自愈规则。"""
    rule = db.query(HealRule).filter(HealRule.id == rule_id).first()
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="自愈规则不存在",
        )

    db.delete(rule)
    db.commit()

    logger.info(f"删除自愈规则: {rule.name}，操作人: {current_user.username}")
    return {"success": True, "message": f"自愈规则 '{rule.name}' 已删除"}