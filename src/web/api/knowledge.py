"""知识库管理路由 - 运维知识条目 CRUD

端点：
- GET    /             : 获取知识条目列表（支持按分类筛选）
- POST   /             : 新增知识条目
- GET    /{id}         : 获取单条知识条目
- PUT    /{id}         : 更新知识条目
- DELETE /{id}         : 删除知识条目
- GET    /categories   : 获取所有分类
"""

import json
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..core.deps import get_current_active_user, require_admin
from ..database import get_db
from ..models.knowledge_entry import KnowledgeEntry
from ..models.user import User
from ..schemas.knowledge import (
    CategoryOption,
    KnowledgeEntryCreate,
    KnowledgeEntryListResponse,
    KnowledgeEntryResponse,
    KnowledgeEntryUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["知识库管理"])

# 预设分类
CATEGORIES = [
    {"value": "system", "label": "系统"},
    {"value": "database", "label": "数据库"},
    {"value": "network", "label": "网络"},
    {"value": "application", "label": "应用"},
]


def _entry_to_response(entry: KnowledgeEntry) -> KnowledgeEntryResponse:
    """将 ORM 对象转换为响应"""
    return KnowledgeEntryResponse(
        id=entry.id,
        category=entry.category,
        symptom=entry.symptom,
        possible_causes=json.loads(entry.possible_causes) if entry.possible_causes else [],
        diagnosis_steps=json.loads(entry.diagnosis_steps) if entry.diagnosis_steps else [],
        solutions=json.loads(entry.solutions) if entry.solutions else [],
        severity=entry.severity,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
    )


@router.get("/", response_model=KnowledgeEntryListResponse, summary="获取知识条目列表")
def list_entries(
    category: Optional[str] = Query(None, description="按分类筛选"),
    severity: Optional[str] = Query(None, description="按严重程度筛选"),
    keyword: Optional[str] = Query(None, description="搜索关键词（匹配症状）"),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取知识条目列表，支持按分类、严重程度筛选和关键词搜索。"""
    query = db.query(KnowledgeEntry)

    if category:
        query = query.filter(KnowledgeEntry.category == category)
    if severity:
        query = query.filter(KnowledgeEntry.severity == severity)
    if keyword:
        query = query.filter(KnowledgeEntry.symptom.ilike(f"%{keyword}%"))

    total = query.count()
    items = (
        query.order_by(KnowledgeEntry.severity, KnowledgeEntry.symptom)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return KnowledgeEntryListResponse(
        total=total,
        items=[_entry_to_response(item) for item in items],
    )


@router.get("/categories", summary="获取知识库分类列表")
def list_categories(
    current_user: User = Depends(get_current_active_user),
):
    """获取所有可用的知识分类。"""
    return CATEGORIES


@router.get("/{entry_id}", response_model=KnowledgeEntryResponse, summary="获取单条知识条目")
def get_entry(
    entry_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取指定知识条目的详细信息。"""
    entry = db.query(KnowledgeEntry).filter(KnowledgeEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="知识条目不存在",
        )
    return _entry_to_response(entry)


@router.post("/", response_model=KnowledgeEntryResponse, summary="新增知识条目")
def create_entry(
    request: KnowledgeEntryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """新增一条知识条目。"""
    entry = KnowledgeEntry(
        category=request.category,
        symptom=request.symptom,
        possible_causes=json.dumps(request.possible_causes, ensure_ascii=False),
        diagnosis_steps=json.dumps(request.diagnosis_steps, ensure_ascii=False),
        solutions=json.dumps(request.solutions, ensure_ascii=False),
        severity=request.severity,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    logger.info(f"新增知识条目: {entry.symptom}，操作人: {current_user.username}")
    return _entry_to_response(entry)


@router.put("/{entry_id}", response_model=KnowledgeEntryResponse, summary="更新知识条目")
def update_entry(
    entry_id: int,
    request: KnowledgeEntryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """更新指定知识条目的内容。"""
    entry = db.query(KnowledgeEntry).filter(KnowledgeEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="知识条目不存在",
        )

    if request.category is not None:
        entry.category = request.category
    if request.symptom is not None:
        entry.symptom = request.symptom
    if request.possible_causes is not None:
        entry.possible_causes = json.dumps(request.possible_causes, ensure_ascii=False)
    if request.diagnosis_steps is not None:
        entry.diagnosis_steps = json.dumps(request.diagnosis_steps, ensure_ascii=False)
    if request.solutions is not None:
        entry.solutions = json.dumps(request.solutions, ensure_ascii=False)
    if request.severity is not None:
        entry.severity = request.severity

    db.commit()
    db.refresh(entry)

    logger.info(f"更新知识条目: {entry.symptom}，操作人: {current_user.username}")
    return _entry_to_response(entry)


@router.delete("/{entry_id}", summary="删除知识条目")
def delete_entry(
    entry_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """删除指定知识条目。"""
    entry = db.query(KnowledgeEntry).filter(KnowledgeEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="知识条目不存在",
        )

    db.delete(entry)
    db.commit()

    logger.info(f"删除知识条目: {entry.symptom}，操作人: {current_user.username}")
    return {"success": True, "message": f"知识条目 '{entry.symptom}' 已删除"}