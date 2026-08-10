"""Pydantic Schema 集合 - 导出所有请求/响应模型"""

from .auth import (
    LoginRequest,
    RefreshTokenRequest,
    TokenResponse,
    UserResponse,
)
from .chat import (
    ChatMessage,
    ChatSession,
    CreateSessionRequest,
    ModelInfo,
    SendMessageRequest,
)
from .config_file import (
    ConfigBackupInfo,
    ConfigFileContent,
    ConfigFileInfo,
    ConfigRollbackRequest,
    ConfigSaveRequest,
)
from .heal_rule import (
    HealRuleCreate,
    HealRuleListResponse,
    HealRuleResponse,
    HealRuleUpdate,
    RuleAction,
)
from .knowledge import (
    CategoryOption,
    KnowledgeEntryCreate,
    KnowledgeEntryListResponse,
    KnowledgeEntryResponse,
    KnowledgeEntryUpdate,
)
from .log import (
    LogExportRequest,
    LogPlatformQueryRequest,
    LogSearchRequest,
    LogSearchResponse,
)
from .server import (
    CPUInfo,
    DiskInfo,
    MemInfo,
    MetricHistoryResponse,
    PowerRequest,
    ServerInfo,
    ServerStatusResponse,
    ThresholdConfig,
)
from .service import (
    BatchServiceOperationRequest,
    ServiceInfo,
    ServiceListResponse,
    ServiceOperationRequest,
)

__all__ = [
    # auth
    "LoginRequest",
    "RefreshTokenRequest",
    "TokenResponse",
    "UserResponse",
    # chat
    "ChatMessage",
    "ChatSession",
    "CreateSessionRequest",
    "ModelInfo",
    "SendMessageRequest",
    # config_file
    "ConfigBackupInfo",
    "ConfigFileContent",
    "ConfigFileInfo",
    "ConfigRollbackRequest",
    "ConfigSaveRequest",
    # heal_rule
    "HealRuleCreate",
    "HealRuleListResponse",
    "HealRuleResponse",
    "HealRuleUpdate",
    "RuleAction",
    # knowledge
    "CategoryOption",
    "KnowledgeEntryCreate",
    "KnowledgeEntryListResponse",
    "KnowledgeEntryResponse",
    "KnowledgeEntryUpdate",
    # log
    "LogExportRequest",
    "LogPlatformQueryRequest",
    "LogSearchRequest",
    "LogSearchResponse",
    # server
    "CPUInfo",
    "DiskInfo",
    "MemInfo",
    "MetricHistoryResponse",
    "PowerRequest",
    "ServerInfo",
    "ServerStatusResponse",
    "ThresholdConfig",
    # service
    "BatchServiceOperationRequest",
    "ServiceInfo",
    "ServiceListResponse",
    "ServiceOperationRequest",
]
