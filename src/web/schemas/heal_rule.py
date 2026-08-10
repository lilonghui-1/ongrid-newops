"""自愈规则 Pydantic Schema - 请求/响应模型"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class RuleAction(BaseModel):
    """规则操作定义"""
    tool: str
    params: Dict[str, Any] = {}
    confirm_required: bool = False


class HealRuleCreate(BaseModel):
    """创建自愈规则请求"""
    name: str
    condition: str
    description: Optional[str] = None
    actions: List[RuleAction] = []


class HealRuleUpdate(BaseModel):
    """更新自愈规则请求"""
    condition: Optional[str] = None
    description: Optional[str] = None
    actions: Optional[List[RuleAction]] = None
    enabled: Optional[bool] = None


class HealRuleResponse(BaseModel):
    """自愈规则响应"""
    id: int
    name: str
    condition: str
    description: Optional[str] = None
    actions: List[RuleAction]
    enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class HealRuleListResponse(BaseModel):
    """自愈规则列表响应"""
    total: int
    items: List[HealRuleResponse]