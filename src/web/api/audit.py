"""审计日志路由 - 查询操作审计记录

端点：
- GET / : 分页查询审计日志，支持按 user_id / action / 时间范围筛选
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core.deps import get_current_active_user
from ..database import get_db
from ..models.audit_log import AuditLog
from ..models.user import User

router = APIRouter(tags=["审计日志"])


# ---------------------------------------------------------------------------
# 响应模型
# ---------------------------------------------------------------------------
class AuditLogItem(BaseModel):
    """审计日志条目"""

    id: int = Field(..., description="日志 ID")
    user_id: Optional[int] = Field(None, description="用户 ID")
    username: Optional[str] = Field(None, description="用户名")
    action: str = Field(..., description="操作动作")
    target: Optional[str] = Field(None, description="操作目标")
    method: Optional[str] = Field(None, description="HTTP 方法")
    path: Optional[str] = Field(None, description="请求路径")
    status_code: Optional[int] = Field(None, description="HTTP 状态码")
    ip_address: Optional[str] = Field(None, description="请求来源 IP")
    detail: Optional[str] = Field(None, description="详情")
    created_at: datetime = Field(..., description="创建时间")


class AuditLogPage(BaseModel):
    """审计日志分页响应"""

    total: int = Field(..., description="总记录数")
    page: int = Field(..., description="当前页码")
    page_size: int = Field(..., description="每页条数")
    items: List[AuditLogItem] = Field(default_factory=list, description="日志列表")


@router.get("", response_model=AuditLogPage, summary="查询审计日志")
def list_audit_logs(
    user_id: Optional[int] = Query(None, description="按用户 ID 筛选"),
    action: Optional[str] = Query(None, description="按操作动作筛选（模糊匹配）"),
    start_time: Optional[str] = Query(None, description="起始时间（ISO 格式，如 2024-01-01T00:00:00）"),
    end_time: Optional[str] = Query(None, description="结束时间（ISO 格式）"),
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """分页查询审计日志，支持多维度筛选。

    Args:
        user_id: 按用户 ID 筛选
        action: 按操作动作筛选（模糊匹配）
        start_time: 起始时间
        end_time: 结束时间
        page: 页码
        page_size: 每页条数
        db: 数据库会话
        current_user: 当前登录用户（需要活跃用户权限）

    Returns:
        AuditLogPage: 分页审计日志
    """
    query = db.query(AuditLog)

    if user_id is not None:
        query = query.filter(AuditLog.user_id == user_id)

    if action:
        query = query.filter(AuditLog.action.ilike(f"%{action}%"))

    if start_time:
        try:
            start_dt = datetime.fromisoformat(start_time)
            query = query.filter(AuditLog.created_at >= start_dt)
        except ValueError:
            pass

    if end_time:
        try:
            end_dt = datetime.fromisoformat(end_time)
            query = query.filter(AuditLog.created_at <= end_dt)
        except ValueError:
            pass

    # 按时间倒序排列
    query = query.order_by(AuditLog.created_at.desc())

    total = query.count()
    offset = (page - 1) * page_size
    logs = query.offset(offset).limit(page_size).all()

    items = [
        AuditLogItem(
            id=log.id,
            user_id=log.user_id,
            username=log.username,
            action=log.action,
            target=log.target,
            method=log.method,
            path=log.path,
            status_code=log.status_code,
            ip_address=log.ip_address,
            detail=log.detail,
            created_at=log.created_at,
        )
        for log in logs
    ]

    return AuditLogPage(
        total=total,
        page=page,
        page_size=page_size,
        items=items,
    )
