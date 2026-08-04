"""审计中间件 - 记录所有 HTTP 请求的审计日志

功能：
- 记录 method / path / status_code / ip_address
- 对 POST/PUT/DELETE/PATCH 请求缓存并记录请求体摘要（敏感字段自动脱敏）
- 从 Authorization 头解析 JWT 获取操作用户名
- 将审计记录异步写入数据库 AuditLog 表（不阻塞响应，失败仅记录日志）
"""

import asyncio
import json
import logging
from typing import Any, Dict, Optional, Set

from fastapi import Request
from fastapi.responses import Response

# ---------------------------------------------------------------------------
# 配置常量
# ---------------------------------------------------------------------------
# 需要记录请求体的 HTTP 方法
BODY_METHODS: Set[str] = {"POST", "PUT", "DELETE", "PATCH"}

# 敏感字段名（小写匹配），自动替换为 ***
SENSITIVE_FIELDS: Set[str] = {
    "password",
    "old_password",
    "new_password",
    "confirm_password",
    "secret",
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "private_key",
}

# 请求体摘要最大长度（字节）
MAX_BODY_SUMMARY_LENGTH: int = 2048

logger = logging.getLogger("audit")

# 后台任务引用集合，防止 asyncio 任务被 GC 回收
_background_tasks: Set[asyncio.Task] = set()


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def _mask_sensitive(data: Any) -> Any:
    """递归地将字典中的敏感字段值替换为 ***。

    Args:
        data: 任意可序列化数据（dict / list / 标量）

    Returns:
        脱敏后的数据
    """
    if isinstance(data, dict):
        masked: Dict[str, Any] = {}
        for key, value in data.items():
            if isinstance(key, str) and key.lower() in SENSITIVE_FIELDS:
                masked[key] = "***"
            else:
                masked[key] = _mask_sensitive(value)
        return masked
    if isinstance(data, list):
        return [_mask_sensitive(item) for item in data]
    return data


def _summarize_body(body_bytes: bytes) -> Optional[str]:
    """将请求体字节转换为脱敏后的摘要字符串。

    - JSON 体：解析后脱敏再序列化
    - 非 JSON 体：截断后以字符串形式返回

    Args:
        body_bytes: 原始请求体字节

    Returns:
        摘要字符串；空体返回 None
    """
    if not body_bytes:
        return None

    # 尝试作为 JSON 解析并脱敏
    try:
        parsed = json.loads(body_bytes)
        masked = _mask_sensitive(parsed)
        summary = json.dumps(masked, ensure_ascii=False, default=str)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        # 非 JSON 请求体，直接截断为文本
        try:
            summary = body_bytes[:MAX_BODY_SUMMARY_LENGTH].decode("utf-8", errors="replace")
        except Exception:
            summary = f"<binary {len(body_bytes)} bytes>"

    # 长度兜底截断
    if len(summary) > MAX_BODY_SUMMARY_LENGTH:
        summary = summary[:MAX_BODY_SUMMARY_LENGTH] + "...(truncated)"
    return summary


def _extract_username(request: Request) -> Optional[str]:
    """从 Authorization 头解析 JWT 获取用户名 (sub)。

    Args:
        request: FastAPI Request 对象

    Returns:
        用户名；无法解析时返回 None
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.lower().startswith("bearer "):
        return None

    token = auth_header.split(" ", 1)[1].strip()
    if not token:
        return None

    try:
        # 延迟导入，避免循环依赖
        from .security import decode_token

        payload = decode_token(token)
        username: Optional[str] = payload.get("sub")
        return username
    except Exception:
        # 令牌无效或过期，无法获取用户名
        return None


async def _cache_request_body(request: Request) -> bytes:
    """读取请求体并缓存，使下游处理器仍可正常读取。

    解决 FastAPI/Starlette 中 body 只能读取一次的问题：
    读取后将字节重新写回 request._body 与 request._receive。

    Args:
        request: FastAPI Request 对象

    Returns:
        原始请求体字节
    """
    body_bytes = await request.body()

    # 将 body 重新设置到 request，使下游 call_next / 路由处理器仍能读取
    # 1) 设置 _body 缓存：Request.body() 会优先返回已缓存的 _body
    request._body = body_bytes

    # 2) 替换 _receive：兼容部分 Starlette 版本内部重新读取 receive 流的场景
    async def _receive() -> Dict[str, Any]:
        return {"type": "http.request", "body": body_bytes, "more_body": False}

    request._receive = _receive  # type: ignore[assignment]

    return body_bytes


def _write_audit_log(record: Dict[str, Any]) -> None:
    """将审计记录写入数据库 AuditLog 表（同步函数，在线程池中执行）。

    任何异常都被捕获并记录日志，绝不向上抛出。

    Args:
        record: 审计记录字段字典
    """
    try:
        # 延迟导入，避免在模块加载阶段强依赖 database / models
        from ..database import SessionLocal
        from ..models.audit_log import AuditLog

        db = SessionLocal()
        try:
            log_entry = AuditLog(**record)
            db.add(log_entry)
            db.commit()
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001 - 审计日志写入失败不应影响业务
        logger.warning(
            "审计日志写入数据库失败: %s | 记录内容: %s", exc, record
        )


# ---------------------------------------------------------------------------
# 中间件
# ---------------------------------------------------------------------------
async def audit_middleware(request: Request, call_next) -> Response:
    """审计中间件主函数。

    记录每个请求的 method、path、status_code、ip_address、username，
    以及 POST/PUT/DELETE/PATCH 请求的请求体摘要（脱敏后写入 detail 字段），
    并异步写入数据库 AuditLog 表。数据库写入不阻塞响应，出错时仅记录日志。

    用法::

        from fastapi import FastAPI
        from src.web.core.audit_middleware import audit_middleware

        app = FastAPI()
        app.middleware("http")(audit_middleware)
    """
    method: str = request.method
    path: str = request.url.path

    # ---- 对写操作请求，缓存并提取请求体摘要 ----
    body_summary: Optional[str] = None
    if method in BODY_METHODS:
        try:
            body_bytes = await _cache_request_body(request)
            body_summary = _summarize_body(body_bytes)
        except Exception as exc:  # noqa: BLE001
            logger.debug("读取请求体摘要失败: %s", exc)

    # ---- 执行后续请求处理 ----
    try:
        response = await call_next(request)
    except Exception:
        # 即使下游抛出异常，也尽量记录一条审计日志（status_code 标记为 500）
        username = _extract_username(request)
        ip_address = request.client.host if request.client else None
        _schedule_audit_write(
            method=method,
            path=path,
            status_code=500,
            ip_address=ip_address,
            username=username,
            body_summary=body_summary,
        )
        raise

    # ---- 收集审计信息 ----
    username = _extract_username(request)
    ip_address = request.client.host if request.client else None
    status_code: int = response.status_code

    # ---- 异步写入审计日志（不阻塞响应） ----
    _schedule_audit_write(
        method=method,
        path=path,
        status_code=status_code,
        ip_address=ip_address,
        username=username,
        body_summary=body_summary,
    )

    return response


def _schedule_audit_write(
    *,
    method: str,
    path: str,
    status_code: int,
    ip_address: Optional[str],
    username: Optional[str],
    body_summary: Optional[str],
) -> None:
    """调度异步审计日志写入任务（fire-and-forget）。

    使用 asyncio.to_thread 在线程池中执行同步数据库操作，
    并通过任务集合持有引用防止被垃圾回收。
    """
    record: Dict[str, Any] = {
        "method": method,
        "path": path,
        "status_code": status_code,
        "ip_address": ip_address,
        "username": username,
        "action": f"{method} {path}",
        "target": path,
        "detail": body_summary,
    }

    try:
        task = asyncio.create_task(asyncio.to_thread(_write_audit_log, record))
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
    except RuntimeError:
        # 没有运行中的事件循环（如同步调用场景），降级为直接写入
        _write_audit_log(record)
