"""技能运行时测试 - SkillLoader / SkillExecutor / 安全分类"""

import pytest
from unittest.mock import MagicMock, patch

from src.skills.loader import SkillLoader
from src.skills.executor import SkillExecutor, SKILL_TOOL_MAP, LOCAL_DENY
from src.tools.base import ToolRegistry, ToolResult


class TestSkillLoader:
    """技能加载器测试"""

    @pytest.fixture(autouse=True)
    def _tmp_skills(self, tmp_path):
        """构造临时技能目录"""
        (tmp_path / "ssh-readonly").mkdir(parents=True)
        (tmp_path / "ssh-readonly" / "SKILL.md").write_text(
            """---
name: ssh-readonly
description: 只读 SSH 检查
metadata:
  security:
    class: read-only
  activation:
    mode: always
---

只读检查命令。
""",
            encoding="utf-8",
        )
        (tmp_path / "restart-service").mkdir()
        (tmp_path / "restart-service" / "SKILL.md").write_text(
            """---
name: restart-service
description: 重启服务
metadata:
  security:
    class: mutating
    confirm_required: true
  activation:
    mode: keyword
    keywords: [重启, restart]
---

重启指定服务。
""",
            encoding="utf-8",
        )
        return tmp_path

    def test_load_manifests(self, tmp_path):
        loader = SkillLoader(str(tmp_path))
        manifests = loader.load()
        assert "ssh-readonly" in manifests
        assert "restart-service" in manifests
        assert manifests["ssh-readonly"].metadata.security_class == "read-only"

    def test_mutating_detection(self, tmp_path):
        loader = SkillLoader(str(tmp_path))
        manifests = loader.load()
        assert manifests["restart-service"].is_mutating
        assert not manifests["ssh-readonly"].is_mutating


class TestSkillExecutor:
    """技能执行器测试（mock 底层工具）"""

    def setup_method(self):
        ToolRegistry.clear()

    @pytest.fixture(autouse=True)
    def _tmp_skills(self, tmp_path):
        """构造临时技能目录"""
        (tmp_path / "ssh-readonly").mkdir(parents=True)
        (tmp_path / "ssh-readonly" / "SKILL.md").write_text(
            """---
name: ssh-readonly
description: 只读 SSH 检查
metadata:
  security:
    class: read-only
  activation:
    mode: always
---

只读检查命令。
""",
            encoding="utf-8",
        )
        (tmp_path / "restart-service").mkdir()
        (tmp_path / "restart-service" / "SKILL.md").write_text(
            """---
name: restart-service
description: 重启服务
metadata:
  security:
    class: mutating
    confirm_required: true
  activation:
    mode: keyword
    keywords: [重启, restart]
---

重启指定服务。
""",
            encoding="utf-8",
        )
        return tmp_path

    def test_execute_function_mode(self, tmp_path):
        """function 模式技能：映射到已注册工具"""
        from src.skills.loader import SkillLoader
        from src.skills.executor import SkillExecutor

        loader = SkillLoader(str(tmp_path))
        manifests = loader.load()

        # 注册 mock ssh_execute 工具
        mock_tool = MagicMock()
        mock_tool.execute_with_logging.return_value = ToolResult(
            success=True, data={"stdout": "ok"}, metadata={}
        )
        ToolRegistry.register(mock_tool)

        # 手工构建 SkillExecutor（跳过真实 loader 以避免路径问题）
        executor = SkillExecutor.__new__(SkillExecutor)
        executor.manifests = manifests

        # SKILL_TOOL_MAP 中 ssh-readonly → ssh_execute，但 mock 工具名需要匹配
        mock_tool.name = "ssh_execute"
        ToolRegistry.register(mock_tool)
        result = executor.execute("ssh-readonly", {"host": "10.0.0.1", "command": "df -h"})
        assert result.success

    def test_mutating_requires_approval(self, tmp_path):
        from src.skills.loader import SkillLoader
        from src.skills.executor import SkillExecutor

        loader = SkillLoader(str(tmp_path))
        manifests = loader.load()
        executor = SkillExecutor.__new__(SkillExecutor)
        executor.manifests = manifests

        result = executor.execute("restart-service", {"service_name": "nginx"})
        assert not result.success
        assert "reviewer" in result.error.lower() or "审批" in result.error

    def test_local_deny(self):
        """本地命令 denylist 拒绝"""
        executor = SkillExecutor.__new__(SkillExecutor)
        executor.manifests = {}
        result = executor._run_local(None, {"command": "rm -rf /"})
        assert not result.success
        assert "拒绝" in result.error

    def test_local_shell_meta_rejected(self):
        executor = SkillExecutor.__new__(SkillExecutor)
        executor.manifests = {}
        result = executor._run_local(None, {"command": "cat /etc/passwd | grep root"})
        assert not result.success