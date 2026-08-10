"""FastAPI 应用工厂"""
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .database import init_database
from .core.audit_middleware import audit_middleware
from .core.security import get_password_hash
from .models.user import User
from .database import SessionLocal

logger = logging.getLogger(__name__)


def create_app(app_instance) -> FastAPI:
    """创建 FastAPI 应用

    Args:
        app_instance: OpsAgentApp 实例（包含 config, master_agent, scheduler 等）
    """
    config = app_instance.config
    app = FastAPI(title="ops-agent Web 管理平台", version="2.0.0")

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 审计中间件
    @app.middleware("http")
    async def audit(request, call_next):
        return await audit_middleware(request, call_next)

    # 注册路由
    from .api.auth import router as auth_router
    from .api.servers import router as servers_router
    from .api.logs import router as logs_router
    from .api.services import router as services_router
    from .api.configs import router as configs_router
    from .api.local_configs import router as local_configs_router
    from .api.chat import router as chat_router
    from .api.audit import router as audit_router
    from .api.alert import router as alert_router
    from .api.parameters import router as parameters_router
    from .websocket.log_stream import router as ws_log_router
    from .websocket.server_monitor import router as ws_monitor_router

    app.include_router(auth_router, prefix="/api/auth", tags=["认证"])
    app.include_router(servers_router, prefix="/api/servers", tags=["服务器"])
    app.include_router(logs_router, prefix="/api/logs", tags=["日志"])
    app.include_router(services_router, prefix="/api/services", tags=["应用服务"])
    app.include_router(configs_router, prefix="/api/configs", tags=["配置文件"])
    app.include_router(local_configs_router, prefix="/api/local-configs", tags=["本地配置管理"])
    app.include_router(parameters_router, prefix="/api/parameters", tags=["参数管理"])
    app.include_router(chat_router, prefix="/api/chat", tags=["AI对话"])
    app.include_router(alert_router, prefix="/api/alert", tags=["告警管理"])
    app.include_router(audit_router, prefix="/api/audit", tags=["审计日志"])
    app.include_router(ws_log_router, prefix="/ws", tags=["WebSocket"])
    app.include_router(ws_monitor_router, prefix="/ws", tags=["WebSocket"])

    # 健康检查
    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    # 初始化数据库 + 默认管理员
    init_database()
    _create_default_admin(config)

    # 挂载前端静态资源（必须在所有 API 路由之后）
    dist = Path(__file__).resolve().parents[2] / "web" / "dist"
    if dist.exists():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="frontend")
        logger.info(f"前端静态资源已挂载: {dist}")
    else:
        logger.warning(f"前端构建目录不存在: {dist}，请先执行 npm run build")

    return app


def _create_default_admin(config):
    """首次启动创建默认管理员"""
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.username == config.web.default_admin).first()
        if not admin:
            admin = User(
                username=config.web.default_admin,
                password_hash=get_password_hash(config.web.default_password),
                display_name="管理员",
                role="admin",
            )
            db.add(admin)
            db.commit()
            logger.info("默认管理员已创建")
    finally:
        db.close()
