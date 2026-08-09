"""本地配置文件相关 Pydantic 模型

用于管理后端本地的 YAML 配置文件（config.yaml, servers.yaml, rules.yaml）。
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class LocalConfigFileInfo(BaseModel):
    """本地配置文件信息"""

    name: str = Field(..., description="文件名")
    path: str = Field(..., description="文件完整路径")
    label: str = Field(..., description="显示名称")
    description: str = Field(..., description="文件描述")
    format: str = Field("yaml", description="文件格式")


class LocalConfigContent(BaseModel):
    """本地配置文件内容"""

    name: str = Field(..., description="文件名")
    content: str = Field(..., description="文件内容")
    size: int = Field(0, description="文件大小（字节）")


class LocalConfigSaveRequest(BaseModel):
    """保存本地配置文件请求"""

    content: str = Field(..., description="文件内容")


class LocalConfigReloadResponse(BaseModel):
    """配置重载响应"""

    success: bool = Field(..., description="是否成功")
    message: str = Field(..., description="提示信息")
    details: dict = Field(default_factory=dict, description="详细变更信息")