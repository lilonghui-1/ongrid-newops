"""知识库 Pydantic Schema - 请求/响应模型"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class KnowledgeEntryCreate(BaseModel):
    """创建知识条目请求"""
    category: str = "system"
    symptom: str
    possible_causes: List[str] = []
    diagnosis_steps: List[str] = []
    solutions: List[str] = []
    severity: str = "medium"


class KnowledgeEntryUpdate(BaseModel):
    """更新知识条目请求"""
    category: Optional[str] = None
    symptom: Optional[str] = None
    possible_causes: Optional[List[str]] = None
    diagnosis_steps: Optional[List[str]] = None
    solutions: Optional[List[str]] = None
    severity: Optional[str] = None


class KnowledgeEntryResponse(BaseModel):
    """知识条目响应"""
    id: int
    category: str
    symptom: str
    possible_causes: List[str]
    diagnosis_steps: List[str]
    solutions: List[str]
    severity: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class KnowledgeEntryListResponse(BaseModel):
    """知识条目列表响应"""
    total: int
    items: List[KnowledgeEntryResponse]


class CategoryOption(BaseModel):
    """分类选项"""
    value: str
    label: str