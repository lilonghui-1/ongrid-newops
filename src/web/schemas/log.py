"""日志相关 Pydantic 模型

包含日志搜索、导出、日志平台查询等数据结构。
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class LogSearchRequest(BaseModel):
    """日志搜索请求"""

    server_host: Optional[str] = Field(None, description="服务器地址")
    app_name: Optional[str] = Field(None, description="应用名称")
    log_level: Optional[str] = Field(None, description="日志级别: INFO/WARN/ERROR")
    keyword: Optional[str] = Field(None, description="搜索关键词")
    log_file: Optional[str] = Field(None, description="日志文件路径")
    lines: int = Field(200, description="读取行数", ge=1, le=10000)
    mode: str = Field("tail", description="读取模式: tail/head/grep")


class LogSearchResponse(BaseModel):
    """日志搜索响应"""

    total: int = Field(0, description="日志总条数")
    logs: List[str] = Field(default_factory=list, description="日志内容列表")
    server_host: str = Field(..., description="服务器地址")
    file_path: Optional[str] = Field(None, description="文件路径")


class LogExportRequest(BaseModel):
    """日志导出请求"""

    server_host: Optional[str] = Field(None, description="服务器地址")
    app_name: Optional[str] = Field(None, description="应用名称")
    log_level: Optional[str] = Field(None, description="日志级别")
    keyword: Optional[str] = Field(None, description="搜索关键词")
    log_file: Optional[str] = Field(None, description="日志文件路径")
    lines: int = Field(200, description="读取行数", ge=1, le=10000)
    mode: str = Field("tail", description="读取模式: tail/head/grep")
    format: str = Field("txt", description="导出格式: txt/csv")


class LogPlatformQueryRequest(BaseModel):
    """日志平台查询请求"""

    platform: str = Field(..., description="日志平台类型: elasticsearch/loki")
    query: str = Field(..., description="查询语句（ES Query DSL 或 Loki LogQL）")
    app_name: Optional[str] = Field(None, description="应用名称")
    time_range: str = Field("1h", description="时间范围: 1h/6h/24h/7d")
