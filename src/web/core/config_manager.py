"""应用级配置管理器 - 提供热重载功能

负责在运行时重新加载配置、重新注册工具、重新创建 Agent 和重启调度器。
"""

import asyncio
import logging
from typing import Optional

from ...tools import register_all_tools
from ...tools.base import ToolRegistry
from ...tools.ssh_tools import SSHConnectionPool
from ...utils.config_loader import ConfigLoader

logger = logging.getLogger(__name__)


class AppConfigManager:
    """应用配置管理器 - 单例模式

    持有全局 OpsAgentApp 实例的引用，提供配置热重载能力。
    """

    _instance: Optional['AppConfigManager'] = None
    _app_ref = None  # 持有 OpsAgentApp 实例引用

    def __init__(self):
        self.config_dir = "config"

    @classmethod
    def get_instance(cls) -> 'AppConfigManager':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def init_app(cls, app):
        """初始化时绑定 OpsAgentApp 实例"""
        cls._app_ref = app
        inst = cls.get_instance()
        inst.config_dir = app.config_loader.config_dir if hasattr(app.config_loader, 'config_dir') else "config"

    def reload_config(self) -> dict:
        """热重载配置

        流程：
        1. 重新加载 YAML 配置文件
        2. 重新注册所有工具
        3. 重新创建 Master Agent 和 Heal Agent
        4. 重启调度器

        Returns:
            dict: 包含重载结果和详细信息的字典
        """
        details = {}
        errors = []

        try:
            # 1. 重新加载配置
            ConfigLoader.reset()
            new_config = ConfigLoader.get_instance().load(self.config_dir)
            logger.info("配置已重新加载")
            details["config_loaded"] = True

            # 2. 更新 AppConfig
            old_config = getattr(self._app_ref, 'config', None)
            if old_config:
                old_server_count = len(old_config.servers)
                new_server_count = len(new_config.servers)
                details["servers"] = f"{old_server_count} -> {new_server_count}"
            self._app_ref.config = new_config

            # 3. 重新注册工具
            ToolRegistry.clear()
            register_all_tools(new_config)
            tool_names = ToolRegistry.get_names()
            details["tools"] = list(tool_names)
            logger.info(f"工具已重新注册: {tool_names}")

            # 4. 重新创建 Master Agent
            from ...agent.master_agent import MasterAgent
            self._app_ref.master_agent = MasterAgent(new_config)
            details["master_agent"] = "recreated"
            logger.info("Master Agent 已重新创建")

            # 5. 重启调度器
            scheduler = getattr(self._app_ref, 'scheduler', None)
            if scheduler:
                scheduler.stop()
            from ...scheduler import OpsScheduler
            self._app_ref.scheduler = OpsScheduler(self._app_ref.master_agent, new_config)
            self._app_ref.scheduler.start()
            details["scheduler"] = "restarted"
            logger.info("调度器已重启")

            # 6. 关闭旧 SSH 连接（下次使用时会自动重建）
            SSHConnectionPool.close_all()
            details["ssh_pool"] = "cleared"

            return {
                "success": True,
                "message": "配置已热重载，所有组件已更新",
                "details": details,
            }

        except Exception as e:
            logger.error(f"配置热重载失败: {e}")
            errors.append(str(e))
            return {
                "success": False,
                "message": f"配置热重载失败: {e}",
                "details": {"errors": errors},
            }