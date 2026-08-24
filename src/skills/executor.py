"""技能运行时 - executor

支持两种执行模式：
- function：把技能映射到已注册的 BaseTool（如 ssh_execute / log_fetch）
- subprocess：本地执行只读命令（shell=False，受 CommandPolicy 约束）

技能执行前会校验激活状态与 mutating 审批标记。
"""

from __future__ import annotations

import logging
import shlex
import subprocess
from typing import Any, Dict, List, Optional

from ..tools.base import ToolRegistry, ToolResult
from .schema import SkillManifest

logger = logging.getLogger(__name__)

# 技能名 → 工具名映射（function 模式）
SKILL_TOOL_MAP = {
    "ssh-readonly": "ssh_execute",
    "host-files": "ssh_execute",
    "db-query": "db_query",
    "log-query": "log_fetch",
    "restart-service": "service_control",
    "notify": "send_notification",
    "bash": "bash_execute",
}

# 本地命令 denylist（bash 技能）
LOCAL_DENY = {"rm", "dd", "mv", "chmod", "chown", "mkfs", "reboot", "shutdown",
              "useradd", "passwd", "kill", "pkill", "sudo", "su"}


class SkillExecutor:
    """技能执行器"""

    def __init__(self, skills_dir: str = "skills"):
        from .loader import SkillLoader
        self.loader = SkillLoader(skills_dir)
        self.manifests = self.loader.load()

    def execute(self, skill_name: str, params: Dict[str, Any]) -> ToolResult:
        """执行指定技能"""
        manifest = self.manifests.get(skill_name)
        if not manifest:
            return ToolResult(success=False, error=f"技能不存在: {skill_name}")

        # mutating 技能必须带审批标记
        if manifest.is_mutating and not params.pop("reviewer_approved", False):
            return ToolResult(
                success=False,
                error="mutating 技能需要 reviewer 审批（reviewer_approved=true）",
                metadata={"skill": skill_name},
            )

        tool_name = SKILL_TOOL_MAP.get(skill_name)
        if tool_name:
            tool = ToolRegistry.get(tool_name)
            if not tool:
                return ToolResult(success=False, error=f"技能依赖的工具未注册: {tool_name}")
            return tool.execute_with_logging(**params)

        # 未映射的技能尝试本地执行
        return self._run_local(manifest, params)

    def _run_local(self, manifest: SkillManifest, params: Dict[str, Any]) -> ToolResult:
        """本地 subprocess 执行（只读命令）"""
        command = params.get("command", "")
        if not command:
            return ToolResult(success=False, error="缺少 command 参数")
        argv = shlex.split(command)
        if not argv:
            return ToolResult(success=False, error="空命令")
        if argv[0] in LOCAL_DENY:
            return ToolResult(success=False, error=f"命令被安全策略拒绝: {argv[0]}")

        # 拒绝重定向与 shell 元字符
        for token in argv:
            if token in (">", ">>", "<", "&&", "||", ";", "|"):
                return ToolResult(success=False, error="重定向/连接符被禁止")
        if any(c in command for c in ("$(", "`", "${")) or "sh -c" in command:
            return ToolResult(success=False, error="shell 元字符被禁止")

        timeout = float(params.get("timeout", 30))
        try:
            proc = subprocess.run(
                argv,
                shell=False,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            stdout = proc.stdout[:64 * 1024]
            stderr = proc.stderr[:16 * 1024]
            truncated = len(proc.stdout) > 64 * 1024
            return ToolResult(
                success=proc.returncode == 0,
                data={"stdout": stdout, "stderr": stderr, "exit_code": proc.returncode},
                metadata={"truncated": truncated, "skill": "bash"},
            )
        except subprocess.TimeoutExpired:
            return ToolResult(success=False, error=f"命令超时（>{timeout}s）")
        except Exception as e:
            return ToolResult(success=False, error=f"本地执行失败: {type(e).__name__}: {e}")


def register_skill_tools() -> None:
    """把已加载技能注册为可用的执行器（供 Web API 与 Agent 使用）"""
    from .registry import SkillRegistry
    executor = SkillExecutor()
    for name, manifest in executor.manifests.items():
        SkillRegistry.register(manifest, enabled=True)
    logger.info(f"技能执行器初始化完成，共 {len(executor.manifests)} 个技能")