"""告警管理路由 - 邮件发送记录查询、手动发送告警邮件

端点：
- GET  /email-logs              : 获取邮件发送历史
- GET  /email-logs/{log_id}     : 获取邮件发送详情
- POST /send-email              : 手动发送告警邮件
"""

import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import desc
from sqlalchemy.orm import Session

from ..core.deps import get_current_active_user, require_admin, require_operator
from ..database import get_db
from ..models.email_notify import EmailLog
from ..models.user import User
from ...tools.base import ToolRegistry

logger = logging.getLogger(__name__)

router = APIRouter(tags=["告警管理"])


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


class EmailLogResponse(BaseModel):
    """邮件发送记录响应"""

    id: int
    subject: str
    to_addrs: str
    attachment: Optional[str] = None
    status: str
    error_msg: Optional[str] = None
    created_at: datetime


class EmailLogListResponse(BaseModel):
    """邮件发送记录列表响应"""

    total: int
    items: List[EmailLogResponse]


class SendEmailRequest(BaseModel):
    """手动发送告警邮件请求"""

    subject: str = Field(..., description="邮件主题")
    body: str = Field(..., description="邮件内容（支持 HTML 格式）")
    level: str = Field("warning", description="告警级别: info/warning/error/critical")
    to_addrs: str = Field("", description="收件人邮箱，多个用逗号分隔，为空则使用默认配置")


class SendEmailResponse(BaseModel):
    """发送邮件响应"""

    success: bool
    message: str
    email_log_id: Optional[int] = None


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _email_log_to_response(log: EmailLog) -> EmailLogResponse:
    """将 EmailLog ORM 对象转换为响应 Schema"""
    return EmailLogResponse(
        id=log.id,
        subject=log.subject,
        to_addrs=log.to_addrs,
        attachment=log.attachment,
        status=log.status,
        error_msg=log.error_msg,
        created_at=log.created_at,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/email-logs",
    response_model=EmailLogListResponse,
    summary="获取邮件发送历史",
)
def list_email_logs(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    status_filter: Optional[str] = Query(
        None, description="按状态筛选: success/failed"
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取邮件发送历史记录，按时间倒序排列。

    Args:
        page: 页码
        page_size: 每页条数
        status_filter: 状态筛选
        db: 数据库会话
        current_user: 当前登录用户

    Returns:
        EmailLogListResponse: 邮件发送记录列表
    """
    query = db.query(EmailLog)

    if status_filter:
        query = query.filter(EmailLog.status == status_filter)

    total = query.count()
    items = (
        query.order_by(desc(EmailLog.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return EmailLogListResponse(
        total=total,
        items=[_email_log_to_response(item) for item in items],
    )


@router.get(
    "/email-logs/{log_id}",
    response_model=EmailLogResponse,
    summary="获取邮件发送详情",
)
def get_email_log(
    log_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取单条邮件发送记录的详情。

    Args:
        log_id: 邮件记录 ID
        db: 数据库会话
        current_user: 当前登录用户

    Returns:
        EmailLogResponse
    """
    log = db.query(EmailLog).filter(EmailLog.id == log_id).first()
    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"邮件记录不存在: id={log_id}",
        )
    return _email_log_to_response(log)


@router.post(
    "/send-email",
    response_model=SendEmailResponse,
    summary="手动发送告警邮件",
)
def send_alert_email(
    request: SendEmailRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """手动发送告警邮件并记录发送历史。

    支持通过 EmailTool 发送 HTML 格式邮件，发送后自动记录到数据库。

    Args:
        request: 发送邮件请求
        db: 数据库会话
        current_user: 当前登录用户（需要 operator 权限）

    Returns:
        SendEmailResponse
    """
    email_tool = ToolRegistry.get("send_email")
    if not email_tool:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="邮件工具未注册，请检查邮件配置",
        )

    # 发送邮件
    result = email_tool.send_alert(
        subject=request.subject,
        body=request.body,
        level=request.level,
        to_addrs=(
            [a.strip() for a in request.to_addrs.split(",") if a.strip()]
            if request.to_addrs
            else None
        ),
    )

    # 记录发送日志
    email_log = EmailLog(
        subject=request.subject,
        body=request.body,
        to_addrs=", ".join(result["detail"].get("to", [])),
        status="success" if result["success"] else "failed",
        error_msg=None if result["success"] else result["message"],
    )
    db.add(email_log)
    db.commit()
    db.refresh(email_log)

    logger.info(
        f"告警邮件发送: subject={request.subject!r}, "
        f"status={'success' if result['success'] else 'failed'}, "
        f"操作人: {current_user.username}"
    )

    return SendEmailResponse(
        success=result["success"],
        message=result["message"],
        email_log_id=email_log.id,
    )