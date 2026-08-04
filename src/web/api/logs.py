"""日志路由 - 日志搜索、导出、日志平台查询

端点：
- POST /search   : 搜索服务器日志文件
- POST /export   : 导出日志（TXT/CSV 格式，StreamingResponse）
- POST /platform : 通过日志平台 API 查询日志
"""

import asyncio
import csv
import io
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..core.deps import get_current_active_user
from ..database import get_db
from ..models.user import User
from ..schemas.log import (
    LogExportRequest,
    LogPlatformQueryRequest,
    LogSearchRequest,
    LogSearchResponse,
)
from ...tools.base import ToolRegistry

logger = logging.getLogger(__name__)

router = APIRouter(tags=["日志管理"])


@router.post("/search", response_model=LogSearchResponse, summary="搜索日志")
async def search_logs(
    request: LogSearchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """搜索服务器上的日志文件内容。

    调用 log_fetch 工具读取日志文件，支持 tail/head/grep 模式。

    Args:
        request: 日志搜索请求
        db: 数据库会话
        current_user: 当前登录用户

    Returns:
        LogSearchResponse: 日志内容
    """
    if not request.server_host:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="server_host 不能为空",
        )

    if not request.log_file:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="log_file 不能为空",
        )

    tool = ToolRegistry.get("log_fetch")
    if not tool:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="日志获取工具未注册",
        )

    # 如果有关键词且模式为 tail，自动切换为 grep 模式
    mode = request.mode
    if request.keyword and mode == "tail":
        mode = "grep"

    result = await asyncio.to_thread(
        tool.execute_with_logging,
        host=request.server_host,
        file_path=request.log_file,
        mode=mode,
        lines=request.lines,
        pattern=request.keyword,
    )

    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"日志获取失败: {result.error}",
        )

    content = (result.data or {}).get("content", "")
    log_lines = [line for line in content.split("\n") if line.strip()]

    return LogSearchResponse(
        total=len(log_lines),
        logs=log_lines,
        server_host=request.server_host,
        file_path=request.log_file,
    )


@router.post("/export", summary="导出日志")
async def export_logs(
    request: LogExportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """导出日志内容，支持 TXT 和 CSV 格式。

    Args:
        request: 日志导出请求
        db: 数据库会话
        current_user: 当前登录用户

    Returns:
        StreamingResponse: 文件流响应
    """
    if not request.server_host or not request.log_file:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="server_host 和 log_file 不能为空",
        )

    tool = ToolRegistry.get("log_fetch")
    if not tool:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="日志获取工具未注册",
        )

    mode = request.mode
    if request.keyword and mode == "tail":
        mode = "grep"

    result = await asyncio.to_thread(
        tool.execute_with_logging,
        host=request.server_host,
        file_path=request.log_file,
        mode=mode,
        lines=request.lines,
        pattern=request.keyword,
    )

    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"日志获取失败: {result.error}",
        )

    content = (result.data or {}).get("content", "")
    log_lines = [line for line in content.split("\n") if line.strip()]

    # 生成文件名
    safe_host = request.server_host.replace(".", "_")
    safe_file = request.log_file.replace("/", "_").lstrip("_")

    if request.format.lower() == "csv":
        # CSV 格式
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["序号", "日志内容"])
        for idx, line in enumerate(log_lines, 1):
            writer.writerow([idx, line])

        content_bytes = output.getvalue().encode("utf-8-sig")  # BOM 头兼容 Excel
        filename = f"{safe_host}_{safe_file}.csv"
        media_type = "text/csv"
    else:
        # TXT 格式
        content_bytes = "\n".join(log_lines).encode("utf-8")
        filename = f"{safe_host}_{safe_file}.txt"
        media_type = "text/plain"

    return StreamingResponse(
        io.BytesIO(content_bytes),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/platform", summary="日志平台查询")
async def platform_query(
    request: LogPlatformQueryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """通过日志平台 API 查询日志（ELK/Loki）。

    Args:
        request: 日志平台查询请求
        db: 数据库会话
        current_user: 当前登录用户

    Returns:
        查询结果
    """
    tool = ToolRegistry.get("log_platform_query")
    if not tool:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="日志平台查询工具未注册",
        )

    result = await asyncio.to_thread(
        tool.execute_with_logging,
        platform=request.platform,
        query=request.query,
        app_name=request.app_name,
        time_range=request.time_range,
    )

    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"日志平台查询失败: {result.error}",
        )

    return result.data
