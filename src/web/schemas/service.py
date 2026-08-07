"""应用服务相关 Pydantic 模型

包含服务信息、服务列表、服务操作请求等数据结构。
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class ServiceInfo(BaseModel):
    """服务信息"""

    name: str = Field(..., description="服务名称")
    status: str = Field(..., description="服务状态: active/inactive/failed")
    pid: Optional[int] = Field(None, description="进程 ID")
    start_time: Optional[str] = Field(None, description="启动时间")
    cpu: Optional[float] = Field(None, description="CPU 使用率（%）")
    memory: Optional[float] = Field(None, description="内存使用率（%）")


class ServiceListResponse(BaseModel):
    """服务列表响应"""

    host: str = Field(..., description="主机地址")
    services: List[ServiceInfo] = Field(default_factory=list, description="服务列表")


class ServiceOperationRequest(BaseModel):
    """服务操作请求"""

    service_name: str = Field(..., description="服务名称")
    action: str = Field(..., description="操作: start/stop/restart")


class BatchServiceOperationRequest(BaseModel):
    """批量服务操作请求"""

    service_names: List[str] = Field(..., description="服务名称列表")
    action: str = Field(..., description="操作: start/stop/restart")


# ---------------------------------------------------------------------------
# 服务定义管理（后台维护的服务元数据）
# ---------------------------------------------------------------------------


class AppServiceCreate(BaseModel):
    """新增服务定义请求"""

    server_host: str = Field(..., description="所属服务器地址")
    name: str = Field(..., description="服务名称（systemctl 服务名）")
    display_name: str = Field("", description="服务显示名称（友好名称）")
    description: str = Field("", description="服务描述")
    category: str = Field("application", description="服务分类: web/middleware/database/application/custom")
    port: Optional[int] = Field(None, description="服务端口")
    enabled: bool = Field(True, description="是否启用监控")


class AppServiceUpdate(BaseModel):
    """更新服务定义请求"""

    name: Optional[str] = Field(None, description="服务名称")
    display_name: Optional[str] = Field(None, description="服务显示名称")
    description: Optional[str] = Field(None, description="服务描述")
    category: Optional[str] = Field(None, description="服务分类")
    port: Optional[int] = Field(None, description="服务端口")
    enabled: Optional[bool] = Field(None, description="是否启用监控")


class AppServiceResponse(BaseModel):
    """服务定义响应"""

    id: int = Field(..., description="服务 ID")
    server_host: str = Field(..., description="所属服务器地址")
    name: str = Field(..., description="服务名称")
    display_name: str = Field("", description="服务显示名称")
    description: str = Field("", description="服务描述")
    category: str = Field(..., description="服务分类")
    port: Optional[int] = Field(None, description="服务端口")
    enabled: bool = Field(..., description="是否启用监控")
    created_by: str = Field("", description="创建人")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: Optional[datetime] = Field(None, description="更新时间")
