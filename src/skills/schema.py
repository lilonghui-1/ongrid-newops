"""技能运行时 - schema 定义

技能清单（skills/*/SKILL.md）的 frontmatter 元数据模型。
设计参考 ongrid 技能目录概念（SKILL.md + frontmatter + activation），
本实现为全新 Python 定义。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class SkillMetadata:
    """技能 frontmatter 元数据"""
    os: List[str] = field(default_factory=list)
    scope: str = "remote"                    # remote | local | cloud
    activation_mode: str = "always"          # always | keyword
    keywords: List[str] = field(default_factory=list)
    security_class: str = "read-only"        # read-only | mutating | outbound
    confirm_required: bool = False
    deny: List[str] = field(default_factory=list)
    sql_only: List[str] = field(default_factory=list)
    extra: Dict[str, object] = field(default_factory=dict)


@dataclass
class SkillManifest:
    """一个技能清单（SKILL.md 解析结果）"""
    name: str
    description: str = ""
    when_to_use: str = ""
    body: str = ""                           # md 正文（给 LLM 的说明）
    metadata: SkillMetadata = field(default_factory=SkillMetadata)
    source: str = ""                        # 来源文件路径

    @property
    def is_mutating(self) -> bool:
        return self.metadata.security_class == "mutating"

    @property
    def activation_mode(self) -> str:
        return self.metadata.activation_mode

    def matches_keywords(self, text: str) -> bool:
        """keyword 模式：命中关键词则激活"""
        return any(k in text for k in self.metadata.keywords)