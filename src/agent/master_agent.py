"""Master Agent - 多 Agent 协作调度中枢（融合声明式专家与拓扑相关性）"""

import logging
from typing import Dict, Any, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from ..agents_loader import AgentsLoader
from ..models.llm_factory import LLMFactory
from ..models.prompts import MASTER_SYSTEM_PROMPT
from ..tools.base import ToolRegistry
from ..utils.logger import get_logger

logger = get_logger("master_agent", agent_name="master")


class MasterAgent:
    """Master Agent - 负责任务理解、分解、调度和结果汇总

    工作流程：
    1. 分析用户任务，判断任务类型（含声明式专家路由）
    2. 路由到对应的专业/声明式 Agent 执行
    3. 诊断链路接入拓扑影响面（expand_topology）作为相关性上下文
    4. 自愈动作经 reviewer 审批门槛（confirm_required 的专家才触发）
    5. 汇总所有结果生成最终报告
    """

    def __init__(self, config):
        self.config = config
        self.llm = LLMFactory.create_for_agent(config, "master")

        # 延迟导入避免循环依赖
        from .inspect_agent import InspectAgent
        from .diagnose_agent import DiagnoseAgent
        from .log_agent import LogAgent
        from .heal_agent import HealAgent
        from .specialists import ReviewerAgent

        self.inspect_agent = InspectAgent(config)
        self.diagnose_agent = DiagnoseAgent(config)
        self.log_agent = LogAgent(config)
        self.heal_agent = HealAgent(config)
        self.reviewer = ReviewerAgent(config)

        # 声明式专家（agents/*.md → AgentSpec → SpecialistAgent）
        self._specialists: Dict[str, object] = {}
        self._load_specialists()

    def _load_specialists(self):
        """加载声明式专家注册表（agents 目录）"""
        from .specialists import build_specialist_agent

        try:
            agents_dir = getattr(getattr(self.config, "agents", None), "dir", "agents")
        except Exception:
            agents_dir = "agents"
        loader = AgentsLoader(agents_dir)
        specs = loader.load()
        for name, spec in specs.items():
            if name in {"inspect", "diagnose", "log", "heal"}:
                continue  # 基础 Agent 走原实现
            try:
                self._specialists[name] = build_specialist_agent(self.config, spec)
                logger.info(f"声明式专家已挂载: {name} (mode={spec.permission_mode})")
            except Exception as e:
                logger.error(f"声明式专家挂载失败 {name}: {e}")

    async def run(self, task: str) -> Dict[str, Any]:
        """执行完整的多 Agent 协作流程

        Args:
            task: 用户任务描述

        Returns:
            包含完整执行结果的字典
        """
        logger.info(f"Master Agent 开始处理任务: {task}")

        result = {
            "input": task,
            "task_type": None,
            "inspection_result": None,
            "diagnosis_result": None,
            "log_analysis_result": None,
            "heal_result": None,
            "specialist_result": None,
            "report_result": None,
            "final_report": None,
        }

        try:
            # 1. 分析任务类型
            task_type = await self._analyze_task(task)
            result["task_type"] = task_type
            logger.info(f"任务类型分析结果: {task_type}")

            # 2. 根据任务类型执行
            if task_type == "inspect":
                await self._run_inspection(task, result)
                if self._need_diagnosis(result.get("inspection_result", "")):
                    await self._run_diagnosis(task, result, context=result["inspection_result"])
                    if self._need_heal(result.get("diagnosis_result", "")):
                        await self._run_heal(task, result)

            elif task_type == "diagnose":
                await self._run_diagnosis(task, result)
                if self._need_heal(result.get("diagnosis_result", "")):
                    await self._run_heal(task, result)

            elif task_type == "log":
                await self._run_log_analysis(task, result)
                if self._need_diagnosis(result.get("log_analysis_result", "")):
                    await self._run_diagnosis(task, result, context=result["log_analysis_result"])
                    if self._need_heal(result.get("diagnosis_result", "")):
                        await self._run_heal(task, result)

            elif task_type == "heal":
                await self._run_heal(task, result)

            elif task_type == "specialist":
                await self._run_specialist(task, result)

            elif task_type == "report":
                await self._run_report(task, result)

            elif task_type == "composite":
                # 复合任务：巡检 → 诊断 → 自愈
                await self._run_inspection(task, result)
                if self._need_diagnosis(result.get("inspection_result", "")):
                    await self._run_diagnosis(task, result, context=result["inspection_result"])
                    if self._need_heal(result.get("diagnosis_result", "")):
                        await self._run_heal(task, result)

            # 3. 生成最终报告
            result["final_report"] = self._generate_report(result)

            # 4. 发送通知（如果有异常）
            if self._has_critical_issue(result):
                await self._send_alert(result)

        except Exception as e:
            logger.error(f"Master Agent 执行失败: {e}")
            result["final_report"] = f"任务执行失败: {type(e).__name__}: {e}"
            result["error"] = str(e)

        return result

    async def _analyze_task(self, task: str) -> str:
        """分析任务类型（含声明式专家关键词路由）"""
        # 本地关键词预判（避免 LLM 误判且更快）
        task_lower = task.lower()
        specialist_hits = self._match_specialist(task_lower)
        if specialist_hits:
            return "specialist"

        report_keywords = ["报告", "总结", "汇总", "日报", "周报", "report", "summary"]
        if any(k in task_lower for k in report_keywords):
            return "report"

        try:
            response = await self.llm.ainvoke([
                SystemMessage(content=f"""分析以下运维任务，判断任务类型。

任务类型说明：
- inspect: 服务器/数据库巡检
- diagnose: 故障诊断
- log: 日志分析
- heal: 自愈处理
- specialist: 需要特定领域专家（如网络、磁盘、计算、SRE、运维服务）
- report: 结果汇总/生成报告
- composite: 复合任务（需要多个 Agent 协作）

任务: {task}

只返回任务类型关键词（inspect/diagnose/log/heal/specialist/report/composite），不要其他内容。"""),
            ])
            task_type = response.content.strip().lower()
            valid_types = {"inspect", "diagnose", "log", "heal", "specialist", "report", "composite"}
            if task_type in valid_types:
                return task_type
            for vt in valid_types:
                if vt in task_type:
                    return vt
            return "inspect"  # 默认巡检
        except Exception as e:
            logger.warning(f"任务类型分析失败，默认使用巡检: {e}")
            return "inspect"

    def _match_specialist(self, task_lower: str) -> Optional[str]:
        """关键词匹配声明式专家"""
        keyword_map = {
            "specialist-network": ["网络", "network", "延迟", "丢包", "dns", "防火墙", "路由"],
            "specialist-disk": ["磁盘", "磁盘满", "空间不足", "inode", "分区", "disk"],
            "specialist-compute": ["cpu", "内存", "负载", "进程", "compute", "性能"],
            "specialist-sre": ["sre", "稳定性", "高可用", "容量", "容量规划"],
            "specialist-ops": ["服务", "systemd", "重启", "启动", "停止", "端口"],
        }
        for name, kws in keyword_map.items():
            if any(k in task_lower for k in kws):
                return name
        return None

    async def _run_specialist(self, task: str, result: dict):
        """路由到声明式专家执行"""
        spec_name = self._match_specialist(task.lower())
        if not spec_name:
            # 无命中关键词时用 LLM 再判断
            spec_name = await self._llm_pick_specialist(task)
        if not spec_name:
            result["specialist_result"] = "未找到匹配的声明式专家，回退到通用巡检"
            return

        specialist = self._specialists.get(spec_name)
        if not specialist:
            result["specialist_result"] = f"专家 [{spec_name}] 未加载"
            return

        logger.info(f"路由到声明式专家: {spec_name}")
        spec_result = await specialist.run(task)
        result["specialist_result"] = spec_result.get("result", "")
        result["specialist_name"] = spec_name

        # 专家为 write 模式（confirm_required=True）：所有 mutating 提案过 reviewer 门槛
        spec = self._get_spec(spec_name)
        if spec and spec.confirm_required:
            review = self.reviewer.approve(result["specialist_result"])
            if review["decision"] != "approve":
                logger.warning(f"声明式专家 [{spec_name}] 提案被 reviewer 拒绝: {review['reason']}")
                result["review_result"] = f"提案被 reviewer 拒绝: {review['reason']}"
            else:
                result["review_result"] = "提案已通过 reviewer 审批"

    def _get_spec(self, name: str):
        from ..agents_loader import AgentsLoader
        loader = AgentsLoader(getattr(getattr(self.config, "agents", None), "dir", "agents"))
        return loader.get(name) or None

    async def _llm_pick_specialist(self, task: str) -> Optional[str]:
        try:
            response = await self.llm.ainvoke([
                SystemMessage(content=f"""从以下声明式专家中选择最合适的一个执行任务（只返回名字，不返回其他）：
可用专家: {', '.join(self._specialists.keys())}
任务: {task}"""),
            ])
            name = response.content.strip()
            if name in self._specialists:
                return name
            for n in self._specialists:
                if n in name:
                    return n
        except Exception as e:
            logger.warning(f"LLM 专家推荐失败: {e}")
        return None

    async def _run_report(self, task: str, result: dict):
        """报告/汇总任务"""
        from .specialists import ReporterAgent
        reporter = ReporterAgent(self.config)
        sections = {}
        if result.get("inspection_result"):
            sections["巡检结果"] = result["inspection_result"]
        if result.get("diagnosis_result"):
            sections["诊断结果"] = result["diagnosis_result"]
        if result.get("log_analysis_result"):
            sections["日志分析结果"] = result["log_analysis_result"]
        if result.get("specialist_result"):
            sections["专家结果"] = result["specialist_result"]
        rep_result = await reporter.run(task, sections)
        result["report_result"] = rep_result.get("result", "")
        result["final_report"] = rep_result.get("result", "")

    async def _run_inspection(self, task: str, result: dict):
        """执行巡检"""
        logger.info("执行巡检...")
        inspect_result = await self.inspect_agent.run(task)
        result["inspection_result"] = inspect_result.get("result", "巡检完成")

    async def _run_diagnosis(self, task: str, result: dict, context: str = None):
        """执行诊断（接入拓扑相关性）"""
        logger.info("执行诊断...")
        topology_context = self._topology_context(task)
        if context and topology_context:
            context = f"{context}\n\n## 拓扑相关性\n{topology_context}"
        elif topology_context:
            context = f"## 拓扑相关性\n{topology_context}"

        diagnose_result = await self.diagnose_agent.run(task, context=context)
        result["diagnosis_result"] = diagnose_result.get("result", "诊断完成")

    def _topology_context(self, node_hint: str = "", max_nodes: int = 12) -> str:
        """从拓扑图获取相关性上下文（供诊断参考）

        Args:
            node_hint: 任务中可能的节点关键词（如服务名/主机名），为空则跳过
            max_nodes: 返回节点数上限
        """
        if not node_hint:
            return ""
        try:
            tool = ToolRegistry.get("expand_topology")
            if not tool:
                return ""
            # 用任务关键词展开拓扑影响面；失败则静默跳过
            r = tool.execute(node=node_hint, depth=1, only_propagating=True)
            if not r.success or not r.data:
                return ""
            nodes = r.data.get("hits", [])[:max_nodes]
            if not nodes:
                return ""
            return "; ".join(
                f"{h['node_name']}({h['node_type']}, {h['semantics']} via {h['reached_via']})"
                for h in nodes
            )
        except Exception as e:
            logger.warning(f"拓扑上下文获取失败: {e}")
            return ""

    async def _run_log_analysis(self, task: str, result: dict):
        """执行日志分析"""
        logger.info("执行日志分析...")
        log_result = await self.log_agent.run(task)
        result["log_analysis_result"] = log_result.get("result", "日志分析完成")

    async def _run_heal(self, task: str, result: dict):
        """执行自愈（先过 reviewer 门槛）"""
        logger.info("执行自愈处理...")
        proposal = task or result.get("diagnosis_result", "") or result.get("specialist_result", "")
        review = self.reviewer.approve(proposal)
        if review["decision"] != "approve":
            logger.warning(f"自愈提案被 reviewer 拒绝: {review['reason']}")
            result["heal_result"] = f"自愈操作被 reviewer 拒绝（{review['reason']}），需人工确认后执行"
            return

        heal_result = await self.heal_agent.run(
            task,
            diagnosis_result=result.get("diagnosis_result"),
        )
        result["heal_result"] = heal_result.get("result", "自愈处理完成")

    def _need_diagnosis(self, inspect_result: str) -> bool:
        """判断巡检结果是否需要进一步诊断"""
        if not inspect_result:
            return False
        critical_keywords = ['异常', '告警', '警告', 'error', 'critical', 'high', '失败', '故障']
        return any(kw in inspect_result.lower() for kw in critical_keywords)

    def _need_heal(self, diagnosis_result: str) -> bool:
        """判断诊断结果是否需要自愈"""
        if not diagnosis_result:
            return False
        heal_keywords = ['need_heal', 'true', '建议自愈', '建议重启', '建议清理', '建议修复']
        return any(kw in diagnosis_result.lower() for kw in heal_keywords)

    def _has_critical_issue(self, result: dict) -> bool:
        """判断结果中是否有严重问题需要告警"""
        for key in ['inspection_result', 'diagnosis_result', 'log_analysis_result']:
            content = result.get(key, '')
            if content and 'critical' in content.lower():
                return True
        return False

    def _generate_report(self, result: dict) -> str:
        """汇总所有结果生成最终报告"""
        parts = [f"# 运维任务报告\n\n## 原始任务\n{result['input']}\n"]
        parts.append(f"## 任务类型\n{result.get('task_type', '未知')}\n")

        if result.get('inspection_result'):
            parts.append(f"## 巡检结果\n{result['inspection_result']}\n")
        if result.get('diagnosis_result'):
            parts.append(f"## 诊断结果\n{result['diagnosis_result']}\n")
        if result.get('log_analysis_result'):
            parts.append(f"## 日志分析结果\n{result['log_analysis_result']}\n")
        if result.get('heal_result'):
            parts.append(f"## 自愈处理结果\n{result['heal_result']}\n")
        if result.get('specialist_result'):
            parts.append(f"## 专家处理结果\n{result['specialist_result']}\n")
        if result.get('report_result'):
            parts.append(f"## 报告\n{result['report_result']}\n")

        report = "\n".join(parts)
        logger.info("最终报告已生成")
        return report

    async def _send_alert(self, result: dict):
        """发送告警通知"""
        notify_tool = ToolRegistry.get("send_notification")
        if not notify_tool:
            return

        try:
            report = result.get('final_report', '')
            # 截断过长的报告
            content = report[:2000] if len(report) > 2000 else report
            await notify_tool.execute(
                title="运维告警 - 发现严重问题",
                content=content,
                level="critical",
                channel="all",
            )
            logger.info("告警通知已发送")
        except Exception as e:
            logger.error(f"发送告警通知失败: {e}")