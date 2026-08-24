"""声明式专家 Agent 运行器 - 按 AgentSpec 加载白名单工具并执行任务

设计参考 ongrid 声明式 Agent 概念（frontmatter 强约束 + 工具白名单）：
- 每个 agents/*.md 声明 tools 白名单、permission_mode、confirm_required、max_turns
- 运行时按白名单从 ToolRegistry 取工具，转为 langgraph ReAct Agent
- mutating 专家（confirm_required=True）的写操作需先经 reviewer 审批
- 新增 report 类型任务（report 能力）使用 ReporterAgent 生成报告
"""

import json
import logging
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage

from ..agents_loader import AgentSpec
from ..models.llm_factory import LLMFactory
from ..models.prompts import get_system_prompt
from ..tools.base import ToolRegistry

logger = logging.getLogger(__name__)

# 内置基础 Agent 名称（非声明式，但保留原行为）
BUILTIN_BASE_AGENTS = {"inspect", "diagnose", "log", "heal"}

# 专家 Agent → 基础 Agent 映射（用于组合基础系统提示词）
SPECIALIST_BASE_MAP = {
    "specialist-sre": "diagnose",
    "specialist-ops": "heal",
    "specialist-network": "diagnose",
    "specialist-disk": "diagnose",
    "specialist-compute": "inspect",
}

# report 能力专家 → 报告 Agent（无工具，仅汇总）
SPECIALIST_REPORT_MAP = {
    "reporter": "report",
}


def _build_langchain_tools(spec: AgentSpec) -> list:
    """按 AgentSpec 白名单从 ToolRegistry 取工具并转为 LangChain 工具"""
    langchain_tools = []
    for name in spec.tools:
        tool = ToolRegistry.get(name)
        if not tool:
            logger.warning(f"专家 [{spec.name}] 声明工具未注册: {name}")
            continue
        lc_tool = ToolRegistry._convert_single_tool(tool)
        if lc_tool:
            langchain_tools.append(lc_tool)
    return langchain_tools


def _compose_system_prompt(spec: AgentSpec) -> str:
    """组合系统提示词：基础 Agent prompt + 声明式约束 + md 正文"""
    base_name = SPECIALIST_REPORT_MAP.get(spec.name) or SPECIALIST_BASE_MAP.get(spec.name)
    base_prompt = get_system_prompt(base_name) if base_name in {"inspect", "diagnose", "log", "heal"} else ""
    lines = []
    if base_prompt:
        lines.append(base_prompt.strip())
    lines.append(f"[声明式 Agent 约束] name={spec.name}, permission_mode={spec.permission_mode}")
    lines.append(f"允许工具: {', '.join(spec.tools)}")
    lines.append(f"禁止工具: {', '.join(spec.disallowed_tools) or '无'}")
    lines.append(f"max_turns={spec.max_turns}, confirm_required={spec.confirm_required}")
    if spec.confirm_required:
        lines.append("安全约束: 所有 mutating 动作必须经 reviewer 审批（reviewer_approved=true 才执行）。")
    lines.append(spec.system_prompt)
    return "\n".join(lines)


class SpecialistAgent:
    """声明式专家 Agent 运行器

    用法：
        spec = AgentsLoader(agents_dir).load()["specialist-ops"]
        agent = SpecialistAgent(config, spec)
        result = await agent.run(task)
    """

    def __init__(self, config, spec: AgentSpec):
        self.config = config
        self.spec = spec
        self.llm = LLMFactory.create_for_agent(config, spec.name)
        self.tools = _build_langchain_tools(spec)
        self._agent = None

    def _get_agent(self):
        if self._agent is not None:
            return self._agent
        try:
            from langgraph.prebuilt import create_react_agent
        except ImportError:
            raise ImportError("langgraph 未安装，请执行: pip install langgraph")

        self._agent = create_react_agent(
            model=self.llm,
            tools=self.tools,
            prompt=_compose_system_prompt(self.spec),
        )
        return self._agent

    async def run(self, task: str, context: str = None) -> Dict[str, Any]:
        """执行专家任务

        Args:
            task: 用户任务
            context: 上游上下文（如巡检结果/诊断结论）

        Returns:
            {"agent", "task", "result", "tool_calls"}
        """
        logger.info(f"声明式专家 [{self.spec.name}] 开始任务: {task}")
        agent = self._get_agent()
        full_task = task
        if context:
            full_task = f"{task}\n\n## 已知信息\n{context}"

        try:
            result = await agent.ainvoke({"messages": [HumanMessage(content=full_task)]})
            final_message = result["messages"][-1].content
            tool_calls = self._extract_tool_calls(result["messages"])
            return {
                "agent": self.spec.name,
                "task": task,
                "result": final_message,
                "tool_calls": tool_calls,
            }
        except Exception as e:
            logger.error(f"声明式专家 [{self.spec.name}] 失败: {e}")
            return {
                "agent": self.spec.name,
                "task": task,
                "result": f"执行失败: {type(e).__name__}: {e}",
                "tool_calls": [],
                "error": str(e),
            }

    def _extract_tool_calls(self, messages) -> List[Dict[str, Any]]:
        calls = []
        for msg in messages:
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    calls.append({
                        "tool": tc.get("name", "unknown"),
                        "args": tc.get("args", {}),
                    })
        return calls


class ReviewerAgent:
    """高危操作审批专家 - 对 mutating 提案做静态审查（不执行任何命令）

    决策规则：
    - 缺少提案内容 / 明确破坏性（delete/truncate/drop）→ reject
    - 含自愈规则覆盖（heal_rule / restart / clean 等 SOP 关键词）→ approve
    - 不确定 → reject（安全默认）
    """

    def __init__(self, config=None):
        self.config = config

    def approve(self, proposal: str, context: str = "") -> Dict[str, Any]:
        """静态审批一个 mutating 提案

        Args:
            proposal: 拟执行的操作描述（如 "重启 nginx 服务"）
            context: 诊断/巡检上下文（可选）

        Returns:
            {"decision": "approve"|"reject", "reason": str, "gates": [...]}
        """
        proposal = (proposal or "").strip().lower()
        gates = []
        if not proposal:
            return {
                "decision": "reject",
                "reason": "缺少提案内容",
                "gates": ["无提案，拒绝"],
            }

        destructive = ["delete", "drop", "truncate", "rm ", "格式化", "清空", "移除"]
        if any(k in proposal for k in destructive):
            gates.append("破坏性操作，默认拒绝")
            return {
                "decision": "reject",
                "reason": f"检测到破坏性操作关键词: {[k for k in destructive if k in proposal]}",
                "gates": gates,
            }

        known_sop = ["restart", "重启", "clean", "清理", "heal", "自愈", "start", "stop"]
        hit = [k for k in known_sop if k in proposal]
        if hit:
            gates.append(f"命中已知自愈/SOP 操作: {hit}")
            if "stop" in proposal and "start" not in proposal:
                gates.append("仅停止无重启动作，需人工确认")
                return {
                    "decision": "reject",
                    "reason": "仅停止服务未提供恢复方案",
                    "gates": gates,
                }
            return {
                "decision": "approve",
                "reason": f"命中已知 SOP: {hit}",
                "gates": gates,
            }

        return {
            "decision": "reject",
            "reason": "未命中已知 SOP，安全默认拒绝",
            "gates": ["SOP 覆盖: 未覆盖"],
        }


class ReporterAgent:
    """报告 Agent - 汇总多源结果生成最终报告（不调用工具，纯汇总）"""

    def __init__(self, config=None):
        self.config = config

    async def run(self, task: str, sections: Dict[str, str]) -> Dict[str, Any]:
        """汇总各环节结果生成报告

        Args:
            task: 原始任务描述
            sections: 各环节结果 {"巡检结果": ..., "诊断结果": ..., ...}

        Returns:
            {"agent": "reporter", "task": task, "result": str, "tool_calls": []}
        """
        parts = [f"# 运维任务报告\n\n## 原始任务\n{task}\n"]
        for title, content in sections.items():
            if content:
                parts.append(f"## {title}\n{content}\n")
        return {
            "agent": "reporter",
            "task": task,
            "result": "\n".join(parts),
            "tool_calls": [],
        }


def build_specialist_agent(config, spec: AgentSpec):
    """按 AgentSpec 构建对应运行器

    - reporter → ReporterAgent
    - reviewer → ReviewerAgent
    - 其它 → SpecialistAgent
    """
    if spec.name == "reporter":
        return ReporterAgent(config)
    if spec.name == "reviewer":
        return ReviewerAgent(config)
    return SpecialistAgent(config, spec)