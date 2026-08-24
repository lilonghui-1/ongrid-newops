"""技能运行时 - registry

技能注册表：维护已加载技能清单，并按激活模式管理可用技能集合。
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from .schema import SkillManifest

logger = logging.getLogger(__name__)


class SkillRegistry:
    """技能注册表（进程内单例语义，可通过 clear 重置测试）"""

    _manifests: Dict[str, SkillManifest] = {}
    _enabled: set[str] = set()

    @classmethod
    def register(cls, manifest: SkillManifest, enabled: bool = True) -> None:
        cls._manifests[manifest.name] = manifest
        if enabled:
            cls._enabled.add(manifest.name)
        logger.info(f"技能注册: {manifest.name} enabled={enabled}")

    @classmethod
    def load_many(cls, manifests: Dict[str, SkillManifest], enabled_names: Optional[List[str]] = None) -> None:
        """批量注册；enabled_names 为 None 时全部启用"""
        cls.clear()
        for name, manifest in manifests.items():
            enabled = enabled_names is None or name in enabled_names
            cls.register(manifest, enabled=enabled)

    @classmethod
    def get(cls, name: str) -> Optional[SkillManifest]:
        return cls._manifests.get(name)

    @classmethod
    def all(cls) -> Dict[str, SkillManifest]:
        return dict(cls._manifests)

    @classmethod
    def enabled_names(cls) -> List[str]:
        return sorted(cls._enabled)

    @classmethod
    def is_enabled(cls, name: str) -> bool:
        return name in cls._enabled

    @classmethod
    def enable(cls, name: str) -> None:
        if name in cls._manifests:
            cls._enabled.add(name)

    @classmethod
    def disable(cls, name: str) -> None:
        cls._enabled.discard(name)

    @classmethod
    def clear(cls) -> None:
        cls._manifests.clear()
        cls._enabled.clear()

    @classmethod
    def activated_for(cls, text: str) -> List[SkillManifest]:
        """根据会话文本返回激活技能（always 全部 + keyword 命中）"""
        result = []
        for name in sorted(cls._manifests):
            if name not in cls._enabled:
                continue
            m = cls._manifests[name]
            if m.activation_mode == "always" or m.matches_keywords(text):
                result.append(m)
        return result