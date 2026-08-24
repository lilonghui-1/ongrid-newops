"""工具注册入口 - 初始化并注册所有运维工具"""

import logging

from .base import ToolRegistry
from .ssh_tools import SSHExecuteTool, BashExecuteTool
from .db_tools import DBQueryTool, DBStatusTool, RedisInfoTool
from .log_tools import LogFetchTool, LogAnalyzeTool, LogPlatformQueryTool
from .system_tools import SystemMetricsTool, ServiceControlTool
from .notify_tools import NotifyTool
from .email_tool import EmailTool
from .observability_tools import (
    PrometheusQueryTool,
    LokiQueryTool,
    GrafanaTool,
    register_observability_tools,
)
from ..knowledge.topology import (
    ExpandTopologyTool,
    FindTopologyNodeTool,
    register_topology_tools,
)

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
    ToolRegistry.register(BashExecuteTool(config))

    # 2. 数据库工具（凭证从配置内部读取，不经过 LLM）
    ToolRegistry.register(DBQueryTool(config))
    ToolRegistry.register(DBStatusTool(config))
    ToolRegistry.register(RedisInfoTool(config))

    # 3. 日志工具
    log_fetch_tool = LogFetchTool(ssh_tool, config)
    ToolRegistry.register(log_fetch_tool)
    ToolRegistry.register(LogPlatformQueryTool(config))
    ToolRegistry.register(LogAnalyzeTool())

    # 4. 系统工具（依赖 SSH 工具和配置）
    system_metrics_tool = SystemMetricsTool(ssh_tool, config)
    ToolRegistry.register(system_metrics_tool)
    service_control_tool = ServiceControlTool(ssh_tool, config)
    ToolRegistry.register(service_control_tool)

    # 5. 通知工具（含飞书/Telegram/Slack）
    notify_tool = NotifyTool(config)
    ToolRegistry.register(notify_tool)

    # 6. 邮件工具
    email_tool = EmailTool(config)
    ToolRegistry.register(email_tool)
    notify_tool._set_email_tool(email_tool)
    if email_tool.is_configured:
        logger.info("邮件工具已注册（配置完整）")
    else:
        logger.warning("邮件工具已注册（配置不完整，请设置 SMTP 环境变量）")

    # 7. 可观测性工具（Prometheus/Loki/Grafana）
    register_observability_tools(config)

    # 8. 拓扑/RCA 工具
    register_topology_tools(config)

    # 9. 技能运行时（把技能映射的工具纳入注册表）
    try:
        from ..skills import SkillExecutor
        _skill_executor = SkillExecutor()
        logger.info(f"技能目录已加载: {list(_skill_executor.manifests.keys())}")
    except Exception as e:
        logger.warning(f"技能目录加载失败（不影响核心工具）: {e}")

    # 10. MCP 工具（可选）
    try:
        from ..mcp import register_mcp_tools
        register_mcp_tools()
    except Exception as e:
        logger.warning(f"MCP 工具注册失败（不影响核心工具）: {e}")

    logger.info(f"所有工具注册完成，共 {len(ToolRegistry.get_all())} 个工具: {ToolRegistry.get_names()}")