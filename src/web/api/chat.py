"""AI 对话路由 - 会话管理、消息发送（流式）、模型列表、上下文上传

端点：
- GET  /sessions                : 查询当前用户的对话会话列表
- POST /sessions                : 创建新会话
- GET  /models                  : 返回可用模型列表
- GET  /{session_id}/messages   : 获取会话历史消息
- POST /{session_id}/send       : 发送消息并流式返回 LLM 响应
- POST /{session_id}/upload     : 上传上下文内容
"""

import logging
import uuid
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..core.deps import get_current_active_user
from ..database import SessionLocal, get_db
from ..models.chat_history import ChatHistory
from ..models.user import User
from ..schemas.chat import (
    ChatMessage,
    ChatSession,
    CreateSessionRequest,
    ModelInfo,
    SendMessageRequest,
    UploadContextRequest,
)
from ...utils.config_loader import ConfigLoader

logger = logging.getLogger(__name__)

router = APIRouter(tags=["AI 对话"])

# 系统提示词
SYSTEM_PROMPT = (
    "你是一个专业的运维助手，帮助用户解决服务器管理、数据库运维、"
    "日志分析、服务监控等运维问题。请提供准确、简洁、可操作的建议。"
)


@router.get("/sessions", response_model=List[ChatSession], summary="获取会话列表")
def list_sessions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """查询当前用户的对话会话列表。

    按 session_id 分组，返回每个会话的标题、创建时间和最后一条消息。
    """
    # 按 session_id 分组查询
    sessions = (
        db.query(
            ChatHistory.session_id,
            func.min(ChatHistory.created_at).label("created_at"),
            func.max(ChatHistory.id).label("last_id"),
        )
        .filter(ChatHistory.user_id == current_user.id)
        .group_by(ChatHistory.session_id)
        .order_by(func.max(ChatHistory.created_at).desc())
        .all()
    )

    result: List[ChatSession] = []
    for session_id, created_at, last_id in sessions:
        # 获取第一条用户消息作为标题
        first_msg = (
            db.query(ChatHistory)
            .filter(
                ChatHistory.session_id == session_id,
                ChatHistory.role == "user",
            )
            .order_by(ChatHistory.created_at.asc())
            .first()
        )
        title = "新对话"
        if first_msg and first_msg.content:
            title = first_msg.content[:50]

        # 获取最后一条消息
        last_msg = db.query(ChatHistory).filter(ChatHistory.id == last_id).first()
        last_message = None
        if last_msg and last_msg.content:
            last_message = last_msg.content[:100]

        result.append(ChatSession(
            id=session_id,
            title=title,
            created_at=created_at,
            last_message=last_message,
        ))

    return result


@router.post("/sessions", response_model=ChatSession, summary="创建新会话")
def create_session(
    request: CreateSessionRequest,
    current_user: User = Depends(get_current_active_user),
):
    """创建新的对话会话。

    生成唯一的 session_id 并返回。会话在第一条消息发送时持久化到数据库。

    Args:
        request: 创建会话请求（可选 title）
        current_user: 当前登录用户

    Returns:
        ChatSession: 新建的会话信息
    """
    session_id = str(uuid.uuid4())
    title = request.title or "新对话"

    return ChatSession(
        id=session_id,
        title=title,
        created_at=datetime.now(),
        last_message=None,
    )


@router.get("/models", response_model=List[ModelInfo], summary="获取可用模型列表")
def list_models(
    current_user: User = Depends(get_current_active_user),
):
    """返回可用的 LLM 模型列表。

    优先从 config.llm_models 读取，若未配置则返回默认模型列表。
    """
    try:
        config = ConfigLoader.get_instance().config
    except RuntimeError:
        config = None

    # 尝试从 config.llm_models 读取
    llm_models = getattr(config, "llm_models", None) if config else None

    if llm_models:
        models: List[ModelInfo] = []
        for m in llm_models:
            if isinstance(m, dict):
                models.append(ModelInfo(
                    name=m.get("name", m.get("model", "Unknown")),
                    model=m.get("model", ""),
                    available=m.get("available", True),
                ))
            elif isinstance(m, str):
                models.append(ModelInfo(name=m, model=m, available=True))
        if models:
            return models

    # 默认模型列表
    default_models = [
        ModelInfo(name="GPT-4", model="gpt-4", available=True),
        ModelInfo(name="GPT-4 Turbo", model="gpt-4-turbo", available=True),
        ModelInfo(name="GPT-3.5 Turbo", model="gpt-3.5-turbo", available=True),
    ]

    # 如果 config 中配置了 llm，将其置于列表首位
    if config and hasattr(config, "llm") and config.llm.model:
        default_models.insert(0, ModelInfo(
            name=config.llm.model,
            model=config.llm.model,
            available=True,
        ))

    return default_models


@router.get("/{session_id}/messages", response_model=List[ChatMessage], summary="获取会话消息")
def get_messages(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取指定会话的历史消息列表。

    Args:
        session_id: 会话 ID
        db: 数据库会话
        current_user: 当前登录用户

    Returns:
        ChatMessage 列表
    """
    messages = (
        db.query(ChatHistory)
        .filter(
            ChatHistory.session_id == session_id,
            ChatHistory.user_id == current_user.id,
        )
        .order_by(ChatHistory.created_at.asc())
        .all()
    )

    return [
        ChatMessage(
            id=msg.id,
            role=msg.role,
            content=msg.content or "",
            model=msg.model,
            created_at=msg.created_at,
        )
        for msg in messages
    ]


@router.post("/{session_id}/send", summary="发送消息（流式响应）")
async def send_message(
    session_id: str,
    request: SendMessageRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """发送消息并流式返回 LLM 响应。

    使用 LangChain ChatOpenAI 调用 LLM，通过 StreamingResponse 流式返回。
    用户消息和 AI 响应都会持久化到 ChatHistory 表。

    Args:
        session_id: 会话 ID
        request: 发送消息请求
        db: 数据库会话
        current_user: 当前登录用户

    Returns:
        StreamingResponse: 流式文本响应
    """
    # 延迟导入 LangChain，避免模块加载时强依赖
    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LangChain 未安装，请执行: pip install langchain-openai",
        )

    # 获取 LLM 配置
    try:
        config = ConfigLoader.get_instance().config
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="配置未加载",
        )

    # 保存用户消息
    user_msg = ChatHistory(
        session_id=session_id,
        user_id=current_user.id,
        role="user",
        content=request.message,
        context_type=request.context_type,
        context_content=request.context_content,
    )
    db.add(user_msg)
    db.commit()

    # 加载历史消息
    history = (
        db.query(ChatHistory)
        .filter(
            ChatHistory.session_id == session_id,
            ChatHistory.user_id == current_user.id,
        )
        .order_by(ChatHistory.created_at.asc())
        .all()
    )

    # 构建 LangChain 消息列表
    system_content = SYSTEM_PROMPT
    if request.context_type and request.context_content:
        system_content += f"\n\n上下文信息（{request.context_type}）：\n{request.context_content}"

    messages = [SystemMessage(content=system_content)]

    for msg in history:
        if msg.role == "user" and msg.content:
            messages.append(HumanMessage(content=msg.content))
        elif msg.role == "assistant" and msg.content:
            messages.append(AIMessage(content=msg.content))

    # 确保最后一条是当前用户消息
    if not messages or not isinstance(messages[-1], HumanMessage):
        messages.append(HumanMessage(content=request.message))

    # 创建 ChatOpenAI 实例
    llm_kwargs = {
        "model": request.model,
        "temperature": config.llm.temperature,
    }
    api_key = config.llm.api_key
    if api_key and not api_key.startswith("${"):
        llm_kwargs["api_key"] = api_key
    base_url = config.llm.base_url
    if base_url and not base_url.startswith("${"):
        llm_kwargs["base_url"] = base_url

    try:
        llm = ChatOpenAI(**llm_kwargs)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"LLM 初始化失败: {e}",
        )

    # 流式响应生成器
    async def response_generator():
        full_response = ""
        try:
            async for chunk in llm.astream(messages):
                content = chunk.content
                if content:
                    full_response += content
                    yield content
        except Exception as e:
            error_msg = f"\n\n[LLM 调用错误: {e}]"
            full_response += error_msg
            yield error_msg

        # 流式结束后保存 AI 响应到数据库
        if full_response.strip():
            # 使用独立数据库会话，避免请求会话已关闭的问题
            save_db = SessionLocal()
            try:
                assistant_msg = ChatHistory(
                    session_id=session_id,
                    user_id=current_user.id,
                    role="assistant",
                    content=full_response,
                    model=request.model,
                )
                save_db.add(assistant_msg)
                save_db.commit()
            except Exception as e:
                logger.error(f"保存 AI 响应失败: {e}")
            finally:
                save_db.close()

    return StreamingResponse(
        response_generator(),
        media_type="text/plain",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/{session_id}/upload", summary="上传上下文内容")
async def upload_context(
    session_id: str,
    request: UploadContextRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """上传上下文内容（JSON body）。

    将用户粘贴的文本内容存储为该会话的上下文信息。

    Args:
        session_id: 会话 ID
        request: 包含 type 和 content 的上传请求
        db: 数据库会话
        current_user: 当前登录用户

    Returns:
        上传结果
    """
    text = request.content
    # 限制内容大小（最大 1MB）
    max_size = 1024 * 1024
    if len(text.encode("utf-8")) > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="内容大小超过限制（最大 1MB）",
        )

    # 存储为上下文消息
    msg = ChatHistory(
        session_id=session_id,
        user_id=current_user.id,
        role="user",
        content=f"[上传上下文: {request.type}]\n{text[:5000]}",
        context_type=request.type,
        context_content=text,
    )
    db.add(msg)
    db.commit()

    return {
        "success": True,
        "message": f"上下文已上传（类型: {request.type}）",
        "session_id": session_id,
        "type": request.type,
        "size": len(text.encode("utf-8")),
    }
