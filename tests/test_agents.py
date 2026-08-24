"""Agent 单元测试"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

from src.tools.base import ToolRegistry, ToolResult


class TestInspectAgent:
    """巡检 Agent 测试"""

    def setup_method(self):
        ToolRegistry.clear()

    @pytest.mark.asyncio
    async def test_run_inspection(self):
        """测试巡检任务执行"""
        with patch('src.agent.inspect_agent.LLMFactory') as mock_factory, \
             patch('langgraph.prebuilt.create_react_agent') as mock_create:

            mock_llm = MagicMock()
            mock_factory.create_for_agent.return_value = mock_llm

            mock_agent = AsyncMock()
            mock_msg = MagicMock()
            mock_msg.content = "巡检完成，所有指标正常"
            mock_msg.tool_calls = []
            mock_agent.ainvoke.return_value = {"messages": [mock_msg]}
            mock_create.return_value = mock_agent

            from src.agent.inspect_agent import InspectAgent

            config = MagicMock()
            config.llm = MagicMock()
            config.llm.model = "gpt-4"
            config.llm.api_key = "test"
            config.llm.base_url = None
            config.llm.temperature = 0.1
            config.llm.max_tokens = 4096

            agent = InspectAgent(config)
            result = await agent.run("巡检服务器 192.168.1.10")

            assert result["agent"] == "inspect"
            assert "巡检完成" in result["result"]


class TestDiagnoseAgent:
    """诊断 Agent 测试"""

    def setup_method(self):
        ToolRegistry.clear()

    @pytest.mark.asyncio
    async def test_run_diagnosis(self):
        """测试诊断任务执行"""
        with patch('src.agent.diagnose_agent.LLMFactory') as mock_factory, \
             patch('langgraph.prebuilt.create_react_agent') as mock_create:

            mock_llm = MagicMock()
            mock_factory.create_for_agent.return_value = mock_llm

            mock_agent = AsyncMock()
            mock_msg = MagicMock()
            mock_msg.content = '{"summary": "CPU使用率过高", "severity": "high"}'
            mock_msg.tool_calls = []
            mock_agent.ainvoke.return_value = {"messages": [mock_msg]}
            mock_create.return_value = mock_agent

            from src.agent.diagnose_agent import DiagnoseAgent

            config = MagicMock()
            config.llm = MagicMock()
            config.llm.model = "gpt-4"
            config.llm.api_key = "test"
            config.llm.base_url = None
            config.llm.temperature = 0.1
            config.llm.max_tokens = 4096

            agent = DiagnoseAgent(config)
            result = await agent.run("诊断 CPU 异常")

            assert result["agent"] == "diagnose"
            assert "CPU" in result["result"]


class TestMasterAgent:
    """Master Agent 测试"""

    def setup_method(self):
        ToolRegistry.clear()

    @pytest.mark.asyncio
    async def test_analyze_task(self):
        """测试任务类型分析"""
        with patch('src.agent.master_agent.LLMFactory') as mock_factory, \
             patch('src.agent.inspect_agent.InspectAgent'), \
             patch('src.agent.diagnose_agent.DiagnoseAgent'), \
             patch('src.agent.log_agent.LogAgent'), \
             patch('src.agent.heal_agent.HealAgent'):

            mock_llm = AsyncMock()
            mock_response = MagicMock()
            mock_response.content = "inspect"
            mock_llm.ainvoke.return_value = mock_response
            mock_factory.create_for_agent.return_value = mock_llm

            from src.agent.master_agent import MasterAgent

            config = MagicMock()
            config.llm = MagicMock()
            config.llm.model = "gpt-4"
            config.llm.api_key = "test"
            config.llm.base_url = None
            config.llm.temperature = 0.1
            config.llm.max_tokens = 4096
            config.servers = []

            agent = MasterAgent(config)
            task_type = await agent._analyze_task("巡检所有机器的运行状态")
            assert task_type == "inspect"

    def test_need_diagnosis(self):
        """测试是否需要诊断的判断"""
        with patch('src.agent.master_agent.LLMFactory') as mock_factory, \
             patch('src.agent.inspect_agent.InspectAgent'), \
             patch('src.agent.diagnose_agent.DiagnoseAgent'), \
             patch('src.agent.log_agent.LogAgent'), \
             patch('src.agent.heal_agent.HealAgent'):

            mock_llm = MagicMock()
            mock_factory.create_for_agent.return_value = mock_llm

            from src.agent.master_agent import MasterAgent

            config = MagicMock()
            config.llm = MagicMock()
            config.llm.model = "gpt-4"
            config.llm.api_key = "test"
            config.llm.base_url = None
            config.llm.temperature = 0.1
            config.llm.max_tokens = 4096
            config.servers = []

            agent = MasterAgent(config)

            # 正常结果不需要诊断
            assert agent._need_diagnosis("所有指标正常") is False
            # 异常结果需要诊断
            assert agent._need_diagnosis("CPU使用率异常告警") is True
            assert agent._need_diagnosis("发现 ERROR 级别错误") is True

    def test_generate_report(self):
        """测试报告生成"""
        with patch('src.agent.master_agent.LLMFactory') as mock_factory, \
             patch('src.agent.inspect_agent.InspectAgent'), \
             patch('src.agent.diagnose_agent.DiagnoseAgent'), \
             patch('src.agent.log_agent.LogAgent'), \
             patch('src.agent.heal_agent.HealAgent'):

            mock_llm = MagicMock()
            mock_factory.create_for_agent.return_value = mock_llm

            from src.agent.master_agent import MasterAgent

            config = MagicMock()
            config.llm = MagicMock()
            config.llm.model = "gpt-4"
            config.llm.api_key = "test"
            config.llm.base_url = None
            config.llm.temperature = 0.1
            config.llm.max_tokens = 4096
            config.servers = []

            agent = MasterAgent(config)

            result = {
                "input": "巡检服务器",
                "task_type": "inspect",
                "inspection_result": "CPU正常，内存正常",
            }
            report = agent._generate_report(result)
            assert "巡检服务器" in report
            assert "CPU正常" in report
