"""工具注册入口 - 初始化并注册所有运维工具"""

import logging

from .base import ToolRegistry
from .ssh_tools import SSHExecuteTool
from .db_tools import DBQueryTool, DBStatusTool, RedisInfoTool
from .log_tools import LogFetchTool, LogAnalyzeTool, LogPlatformQueryTool
from .system_tools import SystemMetricsTool, ServiceControlTool
from .notify_tools import NotifyTool
from .email_tool import EmailTool

logger = logging.getLogger(__name__)


def register_all_tools(config):
    """初始化并注册所有工具到 ToolRegistry

    Args:
        config: AppConfig 配置实例
    """
    ToolRegistry.clear()

    # 1. SSH 工具（其他工具依赖它）
    ssh_tool = SSHExecuteTool(config)
    ToolRegistry.register(ssh_tool)

    # 2. 数据库工具（凭证从配置内部读取，不经过 LLM）
    # 支持: mysql, postgresql, oracle, dm(达梦), kingbase(人大金仓), redis
    ToolRegistry.register(DBQueryTool(config))
    ToolRegistry.register(DBStatusTool(config))
    ToolRegistry.register(RedisInfoTool(config))

    # 3. 日志工具
    # SSH 文件读取
    log_fetch_tool = LogFetchTool(ssh_tool, config)
    ToolRegistry.register(log_fetch_tool)
    # 日志平台 API 查询（ELK/Loki）
    ToolRegistry.register(LogPlatformQueryTool(config))
    # 日志分析
    ToolRegistry.register(LogAnalyzeTool())

    # 4. 系统工具（依赖 SSH 工具和配置）
    system_metrics_tool = SystemMetricsTool(ssh_tool, config)
    ToolRegistry.register(system_metrics_tool)
    service_control_tool = ServiceControlTool(ssh_tool, config)
    ToolRegistry.register(service_control_tool)

    # 5. 通知工具
    ToolRegistry.register(NotifyTool(config))

    # 6. 邮件工具
    email_tool = EmailTool(config)
    ToolRegistry.register(email_tool)
    if email_tool.is_configured:
        logger.info("邮件工具已注册（配置完整）")
    else:
        logger.warning("邮件工具已注册（配置不完整，请设置 SMTP 环境变量）")

    logger.info(f"所有工具注册完成，共 {len(ToolRegistry.get_all())} 个工具: {ToolRegistry.get_names()}")
