"""声明式 Agent 加载器 - 解析 agents/*.md 的 YAML frontmatter，注册可路由专家

设计参考 ongrid 的声明式 Agent 概念（agents/*.md + frontmatter 强约束），
正文为中文原创重写，仅吸收「frontmatter 声明 + 运行时强约束」的设计思路。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

# frontmatter 分隔符（--- 开头与结尾）
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)


@dataclass
class Capability:
    """能力卡：描述 Agent 的一项能力与可用工具"""
    id: str
    description: str = ""
    tools: List[str] = field(default_factory=list)
    max_tool_calls: int = 10


@dataclass
class AgentSpec:
    """一个声明式 Agent 的完整规格"""
    name: str
    description: str = ""
    role: str = ""
    when_to_use: str = ""
    tools: List[str] = field(default_factory=list)
    disallowed_tools: List[str] = field(default_factory=list)
    capabilities: List[Capability] = field(default_factory=list)
    permission_mode: str = "read-only"      # read-only | read | write
    max_turns: int = 10
    confirm_required: bool = False          # True → 所有 mutating 动作需 reviewer 审批
    background: bool = False
    model: Optional[str] = None
    system_prompt: str = ""                 # md 正文（渲染后作为 system prompt）
    source_file: str = ""

    @property
    def allowed_tools(self) -> List[str]:
        """可用工具（白名单）"""
        return list(self.tools)

    @property
    def is_write(self) -> bool:
        return self.permission_mode in ("write",)


class AgentsLoader:
    """agents/*.md 加载器：解析 frontmatter 与正文，构建 AgentSpec 注册表"""

    def __init__(self, agents_dir: str = "agents"):
        self.agents_dir = Path(agents_dir)
        self._specs: Dict[str, AgentSpec] = {}

    def load(self, agents_dir: Optional[str] = None) -> Dict[str, AgentSpec]:
        """扫描并解析 agents/*.md"""
        if agents_dir:
            self.agents_dir = Path(agents_dir)
        self._specs.clear()
        if not self.agents_dir.exists():
            logger.warning(f"agents 目录不存在: {self.agents_dir}")
            return self._specs

        for md_file in sorted(self.agents_dir.glob("*.md")):
            try:
                spec = self._parse_file(md_file)
                if spec:
                    self._specs[spec.name] = spec
                    logger.info(f"声明式 Agent 已加载: {spec.name} (mode={spec.permission_mode}, tools={len(spec.tools)})")
            except Exception as e:
                logger.error(f"解析 agents/{md_file.name} 失败: {e}")
        return self._specs

    def _parse_file(self, md_file: Path) -> Optional[AgentSpec]:
        text = md_file.read_text(encoding="utf-8")
        m = _FRONTMATTER_RE.match(text)
        if not m:
            logger.warning(f"{md_file.name} 缺少 frontmatter，跳过")
            return None
        fm_text, body = m.group(1), m.group(2)
        fm = yaml.safe_load(fm_text) or {}
        name = str(fm.get("name") or md_file.stem)
        tools = [str(t) for t in (fm.get("tools") or [])]
        disallowed = [str(t) for t in (fm.get("disallowed_tools") or [])]
        caps = []
        for c in (fm.get("capabilities") or []):
            if isinstance(c, dict):
                caps.append(Capability(
                    id=str(c.get("id") or c.get("name") or ""),
                    description=str(c.get("description") or ""),
                    tools=[str(t) for t in (c.get("tools") or [])],
                    max_tool_calls=int(c.get("max_tool_calls") or 10),
                ))
        return AgentSpec(
            name=name,
            description=str(fm.get("description") or ""),
            role=str(fm.get("role") or ""),
            when_to_use=str(fm.get("when_to_use") or ""),
            tools=tools,
            disallowed_tools=disallowed,
            capabilities=caps,
            permission_mode=str(fm.get("permission_mode") or "read-only"),
            max_turns=int(fm.get("max_turns") or 10),
            confirm_required=bool(fm.get("confirm_required") or False),
            background=bool(fm.get("background") or False),
            model=str(fm["model"]) if fm.get("model") else None,
            system_prompt=body.strip(),
            source_file=str(md_file),
        )

    def get(self, name: str) -> Optional[AgentSpec]:
        return self._specs.get(name)

    def all(self) -> Dict[str, AgentSpec]:
        return dict(self._specs)

    def names(self) -> List[str]:
        return list(self._specs.keys())

    def filter_write(self) -> List[AgentSpec]:
        """返回可执行写操作的 Agent（需要 reviewer 审批）"""
        return [s for s in self._specs.values() if s.is_write]


def load_agents(agents_dir: str = "agents") -> Dict[str, AgentSpec]:
    """便捷入口：加载 agents 目录"""
    return AgentsLoader(agents_dir).load()