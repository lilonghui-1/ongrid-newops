"""技能目录管理路由 - 查看技能清单、执行技能、按关键词匹配

端点：
- GET  /            : 技能清单（含安全分类/激活模式/是否 mutating）
- POST /execute     : 执行技能（mutating 需 reviewer_approved）
- GET  /match       : 按文本关键词匹配可激活技能
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..core.deps import get_current_active_user, require_operator
from ..models.user import User
from ...skills import SkillExecutor, SkillLoader
from ...utils.config_loader import ConfigLoader

logger = logging.getLogger(__name__)

router = APIRouter(tags=["技能目录"])


def _get_executor() -> SkillExecutor:
    """获取技能执行器（按配置定位 skills 目录）"""
    try:
        config = ConfigLoader.get_instance().config
        skills_dir = getattr(config.skills, "dir", "skills")
    except Exception:
        skills_dir = "skills"
    return SkillExecutor(skills_dir)


@router.get("/", summary="技能清单")
def list_skills(
    enabled_only: bool = Query(False, description="仅返回启用状态的技能"),
    current_user: User = Depends(get_current_active_user),
):
    """返回技能目录清单（名称、描述、安全分类、激活方式）"""
    executor = _get_executor()
    items = []
    for name, manifest in executor.manifests.items():
        items.append({
            "name": name,
            "description": manifest.description,
            "when_to_use": manifest.when_to_use,
            "security_class": manifest.metadata.security_class,
            "activation_mode": manifest.activation_mode,
            "keywords": manifest.metadata.keywords,
            "confirm_required": manifest.metadata.confirm_required,
            "enabled": True,
        })
    if enabled_only:
        items = [i for i in items if i["enabled"]]
    return {"total": len(items), "items": items}


@router.post("/execute", summary="执行技能")
def execute_skill(
    request: dict,
    current_user: User = Depends(require_operator),
):
    """执行指定技能

    Body:
        {"skill": "ssh-readonly", "params": {...}, "reviewer_approved": false}

    mutating 技能必须带 reviewer_approved=true 才可执行。
    """
    skill_name = request.get("skill")
    if not skill_name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="缺少 skill 参数")
    params = request.get("params") or {}
    reviewer_approved = bool(request.get("reviewer_approved", False))

    executor = _get_executor()
    if skill_name not in executor.manifests:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"技能不存在: {skill_name}")

    manifest = executor.manifests[skill_name]
    if manifest.is_mutating and not reviewer_approved:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail=f"技能 [{skill_name}] 为 mutating 操作，需 reviewer 审批（reviewer_approved=true）",
        )

    result = executor.execute(skill_name, {**params, "reviewer_approved": reviewer_approved})
    logger.info(f"技能执行: {skill_name} by {current_user.username}, success={result.success}")
    return {
        "success": result.success,
        "skill": skill_name,
        "data": result.data,
        "error": result.error,
        "metadata": result.metadata,
    }


@router.get("/match", summary="按文本匹配技能")
def match_skills(
    text: str = Query(..., description="待匹配文本"),
    current_user: User = Depends(get_current_active_user),
):
    """返回与文本匹配（keyword 激活模式）的技能列表"""
    executor = _get_executor()
    hits = []
    for name, manifest in executor.manifests.items():
        if manifest.activation_mode == "keyword" and manifest.matches_keywords(text):
            hits.append({
                "name": name,
                "description": manifest.description,
                "keywords": manifest.metadata.keywords,
            })
    return {"text": text, "total": len(hits), "items": hits}