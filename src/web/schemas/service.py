"""应用服务相关 Pydantic 模型

包含服务信息、服务列表、服务操作请求等数据结构。
"""

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
