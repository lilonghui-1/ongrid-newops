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
    from .api.knowledge import router as knowledge_router
    from .api.heal_rules import router as heal_rules_router
    from .api.skills import router as skills_router
    from .api.mcp import router as mcp_router
    from .api.topology import router as topology_router
    from .api.users import router as users_router
    from .api.roles import router as roles_router
    from .api.feishu import router as feishu_router
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
    app.include_router(knowledge_router, prefix="/api/knowledge", tags=["知识库管理"])
    app.include_router(heal_rules_router, prefix="/api/heal-rules", tags=["自愈规则管理"])
    app.include_router(skills_router, prefix="/api/skills", tags=["技能目录"])
    app.include_router(mcp_router, prefix="/api/mcp", tags=["MCP 工具"])
    app.include_router(topology_router, prefix="/api/topology", tags=["拓扑管理"])
    app.include_router(users_router, prefix="/api/users", tags=["用户管理"])
    app.include_router(roles_router, prefix="/api/roles", tags=["角色管理"])
    app.include_router(feishu_router, prefix="/api/feishu", tags=["飞书事件"])
    app.include_router(ws_log_router, prefix="/ws", tags=["WebSocket"])
    app.include_router(ws_monitor_router, prefix="/ws", tags=["WebSocket"])

    # 健康检查
    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    # 初始化数据库 + 默认管理员 + 内置角色
    init_database()
    _create_default_admin(config)
    _init_builtin_roles()

    # 启动飞书长连接（后台线程，如配置了 use_ws 且有 app_id/app_secret）
    from .api.feishu_ws import start_in_background as _start_feishu_ws
    _start_feishu_ws()

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


def _init_builtin_roles():
    """首次启动创建内置角色（admin / operator / viewer），并分配默认权限。"""
    from .models.role import Role
    from .models.role_permission import RolePermission
    from .models.user_role import UserRole
    from .schemas.role import ALL_PERMISSIONS

    builtin = {
        "admin": {
            "description": "系统管理员，拥有全部权限",
            "permissions": set(ALL_PERMISSIONS),
        },
        "operator": {
            "description": "操作员，可执行运维操作，不可管理用户和角色",
            "permissions": set(ALL_PERMISSIONS) - {"user:manage", "role:manage"},
        },
        "viewer": {
            "description": "观察者，仅可查看，不可修改",
            "permissions": {p for p in ALL_PERMISSIONS if p.endswith(":read")},
        },
    }

    db = SessionLocal()
    try:
        for name, spec in builtin.items():
            role = db.query(Role).filter(Role.name == name).first()
            if not role:
                role = Role(
                    name=name,
                    description=spec["description"],
                    is_system=True,
                )
                db.add(role)
                db.commit()
                db.refresh(role)
                logger.info(f"内置角色 '{name}' 已创建")
            # 如果角色没有权限记录，则补充默认权限
            existing_perms = (
                db.query(RolePermission.permission)
                .filter(RolePermission.role_id == role.id)
                .all()
            )
            existing_set = {p[0] for p in existing_perms}
            for perm in spec["permissions"]:
                if perm not in existing_set:
                    db.add(RolePermission(role_id=role.id, permission=perm))
            db.commit()

        # 为已有的 admin 用户分配 admin 角色（迁移）
        admin_role = db.query(Role).filter(Role.name == "admin").first()
        if admin_role:
            admin_users = db.query(User).filter(User.role == "admin").all()
            for au in admin_users:
                existing = (
                    db.query(UserRole)
                    .filter(UserRole.user_id == au.id, UserRole.role_id == admin_role.id)
                    .first()
                )
                if not existing:
                    db.add(UserRole(user_id=au.id, role_id=admin_role.id))
            db.commit()
    finally:
        db.close()
