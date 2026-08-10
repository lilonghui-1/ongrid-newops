"""自愈 Agent - 自动处理已诊断的问题"""

import json
import logging
from pathlib import Path

import yaml

from langchain_core.messages import HumanMessage

from ..models.llm_factory import LLMFactory
from ..models.prompts import HEAL_SYSTEM_PROMPT
from ..tools.base import ToolRegistry
from ..utils.logger import get_logger

logger = get_logger("heal_agent", agent_name="heal")


class HealAgent:
    """自愈 Agent - 根据诊断结果执行预定义的安全操作"""

    def __init__(self, config):
        self.config = config
        self.llm = LLMFactory.create_for_agent(config, "heal")
        self._rules = self._load_rules()

        # 自愈 Agent 需要操作和通知工具
        tool_names = ["ssh_execute", "service_control", "db_query", "send_notification"]
        self.tools = [ToolRegistry.get(name) for name in tool_names]
        self.tools = [t for t in self.tools if t is not None]

        self._agent = None

    def _load_rules(self) -> list:
        """从数据库加载自愈规则，若数据库无数据则回退到 rules.yaml"""
        rules = self._load_rules_from_db()
        if rules:
            return rules
        return self._load_rules_from_yaml()

    def _load_rules_from_db(self) -> list:
        """从数据库加载自愈规则"""
        try:
            from src.web.database import SessionLocal
            from src.web.models.heal_rule import HealRule

            db = SessionLocal()
            try:
                db_rules = db.query(HealRule).filter(HealRule.enabled == True).all()
                if not db_rules:
                    return []
                result = []
                for rule in db_rules:
                    actions = json.loads(rule.actions) if rule.actions else []
                    result.append({
                        "name": rule.name,
                        "condition": rule.condition,
                        "description": rule.description or "",
                        "actions": actions,
                    })
                logger.info(f"从数据库加载了 {len(result)} 条自愈规则")
                return result
            finally:
                db.close()
        except Exception as e:
            logger.debug(f"从数据库加载自愈规则失败（可忽略）: {e}")
            return []

    def _load_rules_from_yaml(self) -> list:
        """从 rules.yaml 加载自愈规则"""
        rules_path = Path("config/rules.yaml")
        if rules_path.exists():
            try:
                with open(rules_path, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f) or {}
                rules = data.get('heal_rules', [])
                logger.info(f"从 YAML 加载了 {len(rules)} 条自愈规则")
                return rules
            except Exception as e:
                logger.error(f"加载自愈规则失败: {e}")
        return []

    def _format_rules(self) -> str:
        """将规则格式化为文本，注入到 Prompt 中"""
        if not self._rules:
            return "当前没有配置自愈规则。"

        parts = []
        for i, rule in enumerate(self._rules, 1):
            confirm = "需要确认" if any(
                a.get('confirm_required', False) for a in rule.get('actions', [])
            ) else "自动执行"
            parts.append(f"{i}. **{rule['name']}** (确认级别: {confirm})")
            parts.append(f"   - 条件: {rule['condition']}")
            parts.append(f"   - 描述: {rule['description']}")
            for action in rule.get('actions', []):
                parts.append(f"   - 操作: {action['tool']} -> {action.get('params', {})}")
            parts.append("")

        return "\n".join(parts)

    def _get_agent(self):
        """延迟初始化 Agent"""
        if self._agent is not None:
            return self._agent

        try:
            from langgraph.prebuilt import create_react_agent
        except ImportError:
            raise ImportError("langgraph 未安装，请执行: pip install langgraph")

        langchain_tools = []
        for tool in self.tools:
            lc_tool = ToolRegistry._convert_single_tool(tool)
            if lc_tool:
                langchain_tools.append(lc_tool)

        # 在 Prompt 中注入自愈规则
        rules_text = self._format_rules()
        enhanced_prompt = HEAL_SYSTEM_PROMPT + f"""

## 可用的自愈规则
以下规则已配置，你可以根据诊断结果匹配并执行：

{rules_text}

## 重要提醒
- 只执行上述规则中定义的操作
- 标记为"需要确认"的操作，在执行前必须先说明风险并获得确认
- 每次操作后都要验证结果
- 如果没有匹配的规则，不要自行创造操作，而是建议人工介入
"""
        self._agent = create_react_agent(
            model=self.llm,
            tools=langchain_tools,
            prompt=enhanced_prompt,
        )
        return self._agent

    async def run(self, task: str, diagnosis_result: str = None) -> dict:
        """执行自愈任务

        Args:
            task: 自愈任务描述
            diagnosis_result: 诊断 Agent 的诊断结果

        Returns:
            包含自愈结果的字典
        """
        logger.info(f"开始自愈任务: {task}")
        agent = self._get_agent()

        try:
            # 构建完整的任务描述
            full_task = task
            if diagnosis_result:
                full_task = f"## 诊断结果\n{diagnosis_result}\n\n## 自愈任务\n{task}"

            result = await agent.ainvoke(
                {"messages": [HumanMessage(content=full_task)]}
            )
            final_message = result["messages"][-1].content
            tool_calls = self._extract_tool_calls(result["messages"])

            logger.info(f"自愈完成，执行操作次数: {len(tool_calls)}")
            return {
                "agent": "heal",
                "task": task,
                "result": final_message,
                "tool_calls": tool_calls,
            }
        except Exception as e:
            logger.error(f"自愈任务失败: {e}")
            return {
                "agent": "heal",
                "task": task,
                "result": f"自愈失败: {type(e).__name__}: {e}",
                "tool_calls": [],
                "error": str(e),
            }

    def _extract_tool_calls(self, messages) -> list:
        """提取工具调用记录"""
        calls = []
        for msg in messages:
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                for tc in msg.tool_calls:
                    calls.append({
                        "tool": tc.get('name', 'unknown'),
                        "args": tc.get('args', {}),
                    })
        return calls
