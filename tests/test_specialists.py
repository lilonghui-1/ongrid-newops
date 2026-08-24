"""声明式专家 Agent 测试 - SpecialistAgent / ReviewerAgent / ReporterAgent"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.tools.base import ToolRegistry, ToolResult
from src.agent.specialists import (
    SpecialistAgent,
    ReviewerAgent,
    ReporterAgent,
    _build_langchain_tools,
    _compose_system_prompt,
)
from src.agents_loader import AgentSpec, AgentsLoader


def _make_spec(name="specialist-ops", tools=None, permission_mode="write",
               confirm_required=True, system_prompt="[能力: 服务运维]"):
    return AgentSpec(
        name=name,
        description="测试专家",
        role="ops",
        when_to_use="服务异常",
        tools=tools or ["service_control"],
        permission_mode=permission_mode,
        confirm_required=confirm_required,
        max_turns=12,
        system_prompt=system_prompt,
    )


class TestSpecialistAgent:
    """声明式专家运行器测试"""

    def setup_method(self):
        ToolRegistry.clear()
        # 注册 mock 工具
        mock_tool = MagicMock()
        mock_tool.name = "test"
        mock_tool.parameters = []
        mock_tool.description = "test tool"
        mock_tool.execute_with_logging.return_value = ToolResult(
            success=True, data={"stdout": "ok"}, error=None, metadata={}
        )
        ToolRegistry.register(mock_tool)

    @pytest.mark.asyncio
    async def test_run_specialist(self):
        """专家任务执行"""
        with patch("src.agent.specialists.LLMFactory") as mock_factory, \
             patch("langgraph.prebuilt.create_react_agent") as mock_create:

            mock_llm = MagicMock()
            mock_factory.create_for_agent.return_value = mock_llm

            mock_agent = AsyncMock()
            mock_msg = MagicMock()
            mock_msg.content = "服务状态正常，无需重启"
            mock_msg.tool_calls = []
            mock_agent.ainvoke.return_value = {"messages": [mock_msg]}
            mock_create.return_value = mock_agent

            spec = _make_spec()
            agent = SpecialistAgent(MagicMock(), spec)
            result = await agent.run("检查 nginx 服务状态")

            assert result["agent"] == "specialist-ops"
            assert "服务状态" in result["result"]
            assert result["tool_calls"] == []

    def test_build_langchain_tools_filters(self):
        spec = _make_spec(tools=["test", "missing_tool"])
        tools = _build_langchain_tools(spec)
        # 只保留已注册的 "test"
        assert len(tools) == 1
        assert tools[0].name == "test"

    def test_compose_prompt_contains_constraints(self):
        spec = _make_spec()
        prompt = _compose_system_prompt(spec)
        assert "permission_mode=write" in prompt
        assert "confirm_required=True" in prompt
        assert "服务运维" in prompt


class TestReviewerAgent:
    """审批专家测试"""

    def setup_method(self):
        self.reviewer = ReviewerAgent()

    def test_approve_known_sop(self):
        r = self.reviewer.approve("建议重启 nginx 服务")
        assert r["decision"] == "approve"
        assert "重启" in r["reason"]

    def test_reject_empty(self):
        r = self.reviewer.approve("")
        assert r["decision"] == "reject"

    def test_reject_destructive(self):
        r = self.reviewer.approve("删除数据库表 drop table users")
        assert r["decision"] == "reject"

    def test_reject_stop_without_start(self):
        r = self.reviewer.approve("停止 nginx 服务")
        assert r["decision"] == "reject"

    def test_reject_unknown(self):
        r = self.reviewer.approve("执行某个奇怪的操作")
        assert r["decision"] == "reject"


class TestReporterAgent:
    """报告 Agent 测试"""

    @pytest.mark.asyncio
    async def test_run_reporter(self):
        reporter = ReporterAgent()
        result = await reporter.run(
            "生成巡检报告",
            {"巡检结果": "所有指标正常", "诊断结果": "无需诊断"},
        )
        assert result["agent"] == "reporter"
        assert "所有指标正常" in result["result"]
        assert "无需诊断" in result["result"]
        assert result["tool_calls"] == []


class TestAgentsLoader:
    """声明式加载器测试"""

    def test_parse_agent_md(self, tmp_path):
        (tmp_path / "specialist-ops.md").write_text(
            """---
name: specialist-ops
description: 服务专家
permission_mode: write
confirm_required: true
tools: [service_control, ssh_execute]
max_turns: 12
---

[能力: 服务运维]
正文内容
""",
            encoding="utf-8",
        )
        loader = AgentsLoader(str(tmp_path))
        specs = loader.load()
        assert "specialist-ops" in specs
        spec = specs["specialist-ops"]
        assert spec.permission_mode == "write"
        assert spec.confirm_required
        assert spec.tools == ["service_control", "ssh_execute"]