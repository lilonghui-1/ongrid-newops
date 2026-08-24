"""技能运行时 - loader

扫描 skills/*/SKILL.md，解析 frontmatter 与正文为 SkillManifest。
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from .schema import SkillManifest, SkillMetadata

logger = logging.getLogger(__name__)

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)


class SkillLoader:
    """SKILL.md 加载器"""

    def __init__(self, skills_dir: str = "skills"):
        self.skills_dir = Path(skills_dir)

    def load(self, skills_dir: Optional[str] = None) -> Dict[str, SkillManifest]:
        """加载所有技能"""
        if skills_dir:
            self.skills_dir = Path(skills_dir)
        manifests: Dict[str, SkillManifest] = {}
        if not self.skills_dir.exists():
            logger.warning(f"skills 目录不存在: {self.skills_dir}")
            return manifests

        for skill_file in sorted(self.skills_dir.glob("*/SKILL.md")):
            try:
                manifest = self._parse_file(skill_file)
                manifests[manifest.name] = manifest
                logger.info(
                    f"技能已加载: {manifest.name} "
                    f"(class={manifest.metadata.security_class}, "
                    f"activation={manifest.activation_mode})"
                )
            except Exception as e:
                logger.error(f"解析技能 {skill_file} 失败: {e}")
        return manifests

    def _parse_file(self, skill_file: Path) -> SkillManifest:
        text = skill_file.read_text(encoding="utf-8")
        m = _FRONTMATTER_RE.match(text)
        if not m:
            raise ValueError(f"{skill_file} 缺少 frontmatter")
        fm_text, body = m.group(1), m.group(2)
        fm = yaml.safe_load(fm_text) or {}
        meta_raw = fm.get("metadata") or {}
        security = meta_raw.get("security") or {}
        activation = meta_raw.get("activation") or {}
        return SkillManifest(
            name=str(fm.get("name") or skill_file.parent.name),
            description=str(fm.get("description") or ""),
            when_to_use=str(fm.get("when_to_use") or ""),
            body=body.strip(),
            metadata=SkillMetadata(
                os=[str(x) for x in (meta_raw.get("os") or [])],
                scope=str(meta_raw.get("scope") or "remote"),
                activation_mode=str(activation.get("mode") or "always"),
                keywords=[str(k) for k in (activation.get("keywords") or [])],
                security_class=str(security.get("class") or "read-only"),
                confirm_required=bool(security.get("confirm_required") or False),
                deny=[str(d) for d in (security.get("deny") or [])],
                sql_only=[str(s) for s in (security.get("sql_only") or [])],
                extra={k: v for k, v in meta_raw.items() if k not in ("os", "scope", "activation", "security")},
            ),
            source=str(skill_file),
        )