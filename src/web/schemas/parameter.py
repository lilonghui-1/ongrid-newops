"""参数管理相关 Pydantic 模型"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class SystemParameterResponse(BaseModel):
    """参数响应"""
    id: int
    key: str
    value: Optional[str] = None
    description: Optional[str] = None
    is_secret: bool = False
    category: str = "general"
    created_at: datetime
    updated_at: datetime


class SystemParameterListResponse(BaseModel):
    """参数列表响应"""
    total: int
    items: List[SystemParameterResponse]


class SystemParameterCreate(BaseModel):
    """新增参数请求"""
    key: str = Field(..., description="参数名（与配置文件中的 ${KEY} 对应）", max_length=128)
    value: str = Field("", description="参数值")
    description: str = Field("", description="参数描述")
    is_secret: bool = Field(False, description="是否为敏感信息")
    category: str = Field("general", description="分类: ssh/database/llm/email/notify/web/general")


class SystemParameterUpdate(BaseModel):
    """更新参数请求"""
    value: str = Field(..., description="参数值")
    description: Optional[str] = None
    is_secret: Optional[bool] = None
    category: Optional[str] = None


class ApplyParametersResponse(BaseModel):
    """应用参数响应"""
    success: bool
    message: str
    applied_count: int = 0
