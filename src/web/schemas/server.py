"""服务器相关 Pydantic 模型

包含服务器信息、状态、指标历史、电源操作、阈值配置等数据结构。
"""

from typing import List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 子模型
# ---------------------------------------------------------------------------
class CPUInfo(BaseModel):
    """CPU 信息"""

    usage: float = Field(0, description="CPU 使用率（%）")
    cores: int = Field(0, description="CPU 核心数")
    load_avg: str = Field("", description="负载平均值")


class MemInfo(BaseModel):
    """内存信息"""

    total: str = Field("", description="总内存")
    used: str = Field("", description="已用内存")
    free: str = Field("", description="可用内存")
    usage: float = Field(0, description="内存使用率（%）")


class DiskInfo(BaseModel):
    """磁盘信息"""

    total: str = Field("", description="总容量")
    used: str = Field("", description="已用容量")
    free: str = Field("", description="可用容量")
    usage: float = Field(0, description="磁盘使用率（%）")


# ---------------------------------------------------------------------------
# 服务器信息
# ---------------------------------------------------------------------------
class ServerInfo(BaseModel):
    """服务器基本信息"""

    id: str = Field(..., description="服务器标识（host）")
    name: str = Field(..., description="服务器名称")
    host: str = Field(..., description="主机地址")
    port: int = Field(22, description="SSH 端口")
    os_type: str = Field("linux", description="操作系统类型: linux/windows")
    tags: List[str] = Field(default_factory=list, description="标签列表")
    online: bool = Field(False, description="是否在线")
    databases: List[str] = Field(default_factory=list, description="数据库类型列表")


class ServerStatusResponse(BaseModel):
    """服务器实时状态响应"""

    host: str = Field(..., description="主机地址")
    online: bool = Field(..., description="是否在线")
    cpu: CPUInfo = Field(..., description="CPU 信息")
    memory: MemInfo = Field(..., description="内存信息")
    disk: DiskInfo = Field(..., description="磁盘信息")
    uptime: str = Field("", description="运行时长")


class MetricHistoryResponse(BaseModel):
    """指标历史响应"""

    host: str = Field(..., description="主机地址")
    metrics: List[dict] = Field(default_factory=list, description="指标数据列表")
    time_range: str = Field(..., description="时间范围: 1h/24h/7d")


# ---------------------------------------------------------------------------
# 电源操作
# ---------------------------------------------------------------------------
class PowerRequest(BaseModel):
    """电源操作请求"""

    action: str = Field(..., description="操作类型: reboot/shutdown/start")


# ---------------------------------------------------------------------------
# 阈值配置
# ---------------------------------------------------------------------------
class ThresholdConfig(BaseModel):
    """监控阈值配置"""

    cpu_warning: float = Field(80, description="CPU 告警阈值（%）")
    cpu_critical: float = Field(90, description="CPU 严重阈值（%）")
    memory_warning: float = Field(80, description="内存告警阈值（%）")
    memory_critical: float = Field(90, description="内存严重阈值（%）")
    disk_warning: float = Field(80, description="磁盘告警阈值（%）")
    disk_critical: float = Field(90, description="磁盘严重阈值（%）")
