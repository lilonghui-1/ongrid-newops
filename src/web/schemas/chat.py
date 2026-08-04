"""AI 对话相关 Pydantic 模型

包含对话会话、消息、模型信息等数据结构。
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ChatSession(BaseModel):
    """对话会话"""

    id: str = Field(..., description="会话 ID")
    title: str = Field(..., description="会话标题")
    created_at: datetime = Field(..., description="创建时间")
    last_message: Optional[str] = Field(None, description="最后一条消息")


class CreateSessionRequest(BaseModel):
    """创建会话请求"""

    title: Optional[str] = Field(None, description="会话标题")


class SendMessageRequest(BaseModel):
    """发送消息请求"""

    message: str = Field(..., description="消息内容")
    model: str = Field("gpt-4", description="模型名称")
    context_type: Optional[str] = Field(None, description="上下文类型")
    context_content: Optional[str] = Field(None, description="上下文内容")


class ChatMessage(BaseModel):
    """对话消息"""

    id: int = Field(..., description="消息 ID")
    role: str = Field(..., description="角色: user/assistant")
    content: str = Field(..., description="消息内容")
    model: Optional[str] = Field(None, description="模型名称")
    created_at: datetime = Field(..., description="创建时间")


class ModelInfo(BaseModel):
    """模型信息"""

    name: str = Field(..., description="模型显示名称")
    model: str = Field(..., description="模型标识")
    available: bool = Field(True, description="是否可用")


class UploadContextRequest(BaseModel):
    """上传上下文请求（JSON body）"""

    type: str = Field("log", description="上下文类型: log/config/error")
    content: str = Field(..., description="上下文内容")
