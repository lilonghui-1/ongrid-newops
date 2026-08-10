"""运维知识库 - 存储和检索常见运维问题的诊断规则和处理方案"""

import json
import yaml
import logging
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class KnowledgeEntry(BaseModel):
    """知识条目"""
    category: str              # 分类：system, database, network, application
    symptom: str               # 症状描述
    possible_causes: List[str]  # 可能原因
    diagnosis_steps: List[str]  # 诊断步骤
    solutions: List[str]        # 解决方案
    severity: str = "medium"    # 严重程度：low, medium, high, critical


class KnowledgeBase:
    """运维知识库 - 基于关键词匹配的检索"""

    def __init__(self, knowledge_dir: str = "knowledge"):
        self._entries: List[KnowledgeEntry] = []
        self._load_from_db()
        if not self._entries:
            self._load_from_yaml(knowledge_dir)

    def _load_from_db(self):
        """从数据库加载知识条目"""
        try:
            from src.web.database import SessionLocal
            from src.web.models.knowledge_entry import KnowledgeEntry as DBKnowledgeEntry

            db = SessionLocal()
            try:
                db_entries = db.query(DBKnowledgeEntry).all()
                for entry in db_entries:
                    self._entries.append(KnowledgeEntry(
                        category=entry.category,
                        symptom=entry.symptom,
                        possible_causes=json.loads(entry.possible_causes) if entry.possible_causes else [],
                        diagnosis_steps=json.loads(entry.diagnosis_steps) if entry.diagnosis_steps else [],
                        solutions=json.loads(entry.solutions) if entry.solutions else [],
                        severity=entry.severity,
                    ))
                if db_entries:
                    logger.info(f"从数据库加载了 {len(db_entries)} 条知识条目")
            finally:
                db.close()
        except Exception as e:
            logger.debug(f"从数据库加载知识条目失败（可忽略）: {e}")

    def _load_from_yaml(self, knowledge_dir: str):
        """从 YAML 文件加载知识条目"""
        path = Path(knowledge_dir)
        if not path.exists():
            logger.warning(f"知识库目录不存在: {knowledge_dir}")
            return

        for yaml_file in sorted(path.glob("*.yaml")):
            try:
                with open(yaml_file, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f) or {}
                entries = data.get('entries', [])
                for entry_data in entries:
                    try:
                        self._entries.append(KnowledgeEntry(**entry_data))
                    except Exception as e:
                        logger.warning(f"知识条目解析失败: {e}")
                logger.info(f"从 {yaml_file.name} 加载了 {len(entries)} 条知识")
            except Exception as e:
                logger.error(f"加载知识文件失败 {yaml_file}: {e}")

        logger.info(f"知识库加载完成，共 {len(self._entries)} 条知识")

    @property
    def entries(self) -> List[KnowledgeEntry]:
        return self._entries

    def search(self, query: str, category: Optional[str] = None, limit: int = 5) -> List[KnowledgeEntry]:
        """基于关键词匹配搜索相关知识

        Args:
            query: 搜索查询（关键词）
            category: 可选分类过滤
            limit: 最大返回条数

        Returns:
            按相关度排序的知识条目列表
        """
        query_lower = query.lower()
        query_keywords = query_lower.split()

        scored = []
        for entry in self._entries:
            if category and entry.category != category:
                continue

            score = 0
            # 症状匹配（权重最高）
            for keyword in query_keywords:
                if keyword in entry.symptom.lower():
                    score += 3

            # 原因匹配
            for keyword in query_keywords:
                for cause in entry.possible_causes:
                    if keyword in cause.lower():
                        score += 2

            # 分类匹配
            if category and entry.category == category:
                score += 1

            if score > 0:
                scored.append((score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in scored[:limit]]

    def get_context_for_agent(self, symptoms: str, category: str = None) -> str:
        """为 Agent 生成知识库上下文文本

        Args:
            symptoms: 症状描述
            category: 可选分类过滤

        Returns:
            格式化的知识库上下文文本
        """
        entries = self.search(symptoms, category, limit=5)
        if not entries:
            return "未找到相关知识条目。"

        context_parts = ["## 相关运维知识\n"]
        for i, entry in enumerate(entries, 1):
            context_parts.append(f"### {i}. [{entry.category.upper()}] {entry.symptom}")
            context_parts.append(f"- 可能原因: {'; '.join(entry.possible_causes)}")
            context_parts.append(f"- 诊断步骤: {'; '.join(entry.diagnosis_steps)}")
            context_parts.append(f"- 解决方案: {'; '.join(entry.solutions)}")
            context_parts.append(f"- 严重程度: {entry.severity}\n")

        return "\n".join(context_parts)

    def get_all_categories(self) -> List[str]:
        """获取所有分类"""
        return list(set(e.category for e in self._entries))
