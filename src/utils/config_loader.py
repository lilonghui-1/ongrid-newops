"""配置加载模块 - 支持 YAML 配置文件加载、环境变量替换、Pydantic 校验"""

import os
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, field_validator


class LLMConfig(BaseModel):
    """LLM 配置"""
    provider: str = "openai"  # openai / qwen / deepseek
    api_key: str = ""
    base_url: Optional[str] = None
    model: str = "gpt-4"
    temperature: float = 0.1
    max_tokens: int = 4096


class DatabaseConfig(BaseModel):
    """数据库配置"""
    type: str  # mysql / postgresql / redis
    host: str = "127.0.0.1"
    port: int = 3306
    username: str = ""
    password: str = ""
    name: str = ""


class ServerConfig(BaseModel):
    """服务器配置"""
    name: str = ""
    host: str
    port: int = 22
    username: str
    password: Optional[str] = None
    private_key_path: Optional[str] = None
    os_type: str = "linux"  # linux / windows
    tags: List[str] = []
    databases: List[DatabaseConfig] = []


class NotifyConfig(BaseModel):
    """通知配置"""
    wecom_webhook: Optional[str] = None
    dingtalk_webhook: Optional[str] = None


class ScheduleConfig(BaseModel):
    """调度配置"""
    cron: str = "0 */6 * * *"
    enabled: bool = False


class ScheduleGroupConfig(BaseModel):
    """调度分组配置"""
    inspection: Optional[ScheduleConfig] = None
    log_analysis: Optional[ScheduleConfig] = None


class LLMModelConfig(BaseModel):
    """多模型配置"""
    name: str
    provider: str = "openai"
    api_key: str = ""
    base_url: Optional[str] = None
    model: str = ""
    temperature: float = 0.1
    max_tokens: int = 4096


class WebConfig(BaseModel):
    """Web 管理平台配置"""
    host: str = "0.0.0.0"
    port: int = 8000
    secret_key: str = "ops-agent-secret-key-change-in-production"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    default_admin: str = "admin"
    default_password: str = "admin123"


class EmailConfig(BaseModel):
    """邮件通知配置"""
    smtp_host: Optional[str] = None
    smtp_port: int = 465
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    from_addr: Optional[str] = None
    to_addrs: List[str] = []
    use_ssl: bool = True


class AppConfig(BaseModel):
    """应用总配置"""
    llm: LLMConfig
    servers: List[ServerConfig] = []
    notify: NotifyConfig = NotifyConfig()
    email: EmailConfig = EmailConfig()
    log_level: str = "INFO"
    schedule: Dict[str, Any] = {}
    llm_models: List[LLMModelConfig] = []    # 新增：多模型配置
    web: WebConfig = WebConfig()             # 新增：Web 配置
    thresholds: dict = {"cpu": 80, "memory": 85, "disk": 90}  # 新增：告警阈值


class ConfigLoader:
    """配置加载器 - 单例模式"""

    _instance: Optional['ConfigLoader'] = None
    _config: Optional[AppConfig] = None

    def __init__(self, config_dir: str = "config"):
        self.config_dir = Path(config_dir)

    @classmethod
    def get_instance(cls) -> 'ConfigLoader':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls):
        """重置单例（用于测试）"""
        cls._instance = None
        cls._config = None

    def load(self, config_dir: str = None) -> AppConfig:
        """加载并合并所有配置文件"""
        if config_dir:
            self.config_dir = Path(config_dir)

        raw: Dict[str, Any] = {}
        for yaml_file in ["config.yaml", "servers.yaml", "rules.yaml"]:
            path = self.config_dir / yaml_file
            if path.exists():
                with open(path, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f) or {}
                raw.update(data)

        # 环境变量替换
        raw = self._resolve_env_vars(raw)
        self._config = AppConfig(**raw)
        return self._config

    @property
    def config(self) -> AppConfig:
        if self._config is None:
            raise RuntimeError("配置未加载，请先调用 load() 方法")
        return self._config

    def _resolve_env_vars(self, obj: Any) -> Any:
        """递归替换配置中的 ${ENV_VAR} 占位符"""
        if isinstance(obj, str):
            if obj.startswith("${") and obj.endswith("}"):
                env_key = obj[2:-1]
                return os.environ.get(env_key, obj)
            # 处理字符串中内嵌的环境变量 ${VAR}
            import re
            def _replace(match):
                return os.environ.get(match.group(1), match.group(0))
            return re.sub(r'\$\{(\w+)\}', _replace, obj)
        elif isinstance(obj, dict):
            return {k: self._resolve_env_vars(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._resolve_env_vars(item) for item in obj]
        return obj
