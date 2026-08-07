"""配置文件相关 Pydantic 模型

包含配置文件信息、内容、保存/回滚请求等数据结构。
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ConfigFileInfo(BaseModel):
    """配置文件信息"""

    path: str = Field(..., description="文件路径")
    name: str = Field(..., description="文件名称")
    format: str = Field(..., description="文件格式: yml/json/conf/properties")
    category: str = Field("other", description="配置分类: server/database/llm/application/other")
    is_custom: bool = Field(False, description="是否为用户自定义配置")
    config_id: Optional[int] = Field(None, description="自定义配置的数据库 ID（仅自定义配置有值）")


class ConfigCreateRequest(BaseModel):
    """新增配置文件请求"""

    name: str = Field(..., description="配置文件名称")
    path: str = Field(..., description="服务器上的文件路径")
    category: str = Field("application", description="配置分类: server/database/llm/application")
    content: str = Field("", description="初始内容（可为空）")
    description: str = Field("", description="配置描述")


class ConfigFileContent(BaseModel):
    """配置文件内容"""

    path: str = Field(..., description="文件路径")
    content: str = Field(..., description="文件内容")
    format: str = Field(..., description="文件格式")
    size: int = Field(0, description="文件大小（字节）")


class ConfigSaveRequest(BaseModel):
    """配置保存请求"""

    file_path: str = Field(..., description="文件路径")
    content: str = Field(..., description="文件内容")


class ConfigRollbackRequest(BaseModel):
    """配置回滚请求"""

    backup_id: int = Field(..., description="备份 ID")


class ConfigBackupInfo(BaseModel):
    """配置备份信息"""

    id: int = Field(..., description="备份 ID")
    server_host: str = Field(..., description="服务器地址")
    file_path: str = Field(..., description="文件路径")
    version: int = Field(..., description="版本号")
    modified_by: str = Field("", description="修改人")
    modified_at: datetime = Field(..., description="修改时间")
    is_rolled_back: bool = Field(..., description="是否已回滚")
