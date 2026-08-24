"""知识库单元测试"""

import pytest
from pathlib import Path

from src.knowledge.knowledge_base import KnowledgeBase, KnowledgeEntry


class TestKnowledgeEntry:
    """KnowledgeEntry 测试"""

    def test_create_entry(self):
        entry = KnowledgeEntry(
            category="system",
            symptom="CPU 使用率过高",
            possible_causes=["死循环", "恶意进程"],
            diagnosis_steps=["top -bn1"],
            solutions=["终止进程"],
            severity="high",
        )
        assert entry.category == "system"
        assert len(entry.possible_causes) == 2
        assert entry.severity == "high"

    def test_default_severity(self):
        entry = KnowledgeEntry(
            category="database",
            symptom="连接数过多",
            possible_causes=["连接泄漏"],
            diagnosis_steps=["SHOW PROCESSLIST"],
            solutions=["增加连接数"],
        )
        assert entry.severity == "medium"


class TestKnowledgeBase:
    """KnowledgeBase 测试"""

    def test_load_from_yaml(self, tmp_path):
        """测试从 YAML 文件加载知识"""
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text("""
entries:
  - category: system
    symptom: CPU 使用率过高
    possible_causes:
      - 死循环
      - 恶意进程
    diagnosis_steps:
      - top -bn1
    solutions:
      - 终止进程
    severity: high

  - category: database
    symptom: MySQL 连接数耗尽
    possible_causes:
      - 连接泄漏
    diagnosis_steps:
      - SHOW PROCESSLIST
    solutions:
      - 增加连接数
    severity: critical
""", encoding="utf-8")

        kb = KnowledgeBase(knowledge_dir=str(tmp_path))
        assert len(kb.entries) == 2

    def test_search_by_keyword(self, tmp_path):
        """测试关键词搜索"""
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text("""
entries:
  - category: system
    symptom: CPU 使用率持续超过 80%
    possible_causes:
      - 死循环
      - 恶意进程
    diagnosis_steps:
      - top -bn1
    solutions:
      - 终止进程
    severity: high

  - category: database
    symptom: MySQL 慢查询数量激增
    possible_causes:
      - 缺少索引
    diagnosis_steps:
      - EXPLAIN
    solutions:
      - 添加索引
    severity: medium
""", encoding="utf-8")

        kb = KnowledgeBase(knowledge_dir=str(tmp_path))

        # 搜索 CPU 相关
        results = kb.search("CPU 使用率过高")
        assert len(results) >= 1
        assert results[0].category == "system"

        # 搜索 MySQL 相关
        results = kb.search("MySQL 慢查询")
        assert len(results) >= 1
        assert results[0].category == "database"

    def test_search_with_category_filter(self, tmp_path):
        """测试分类过滤"""
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text("""
entries:
  - category: system
    symptom: CPU 使用率过高
    possible_causes: [死循环]
    diagnosis_steps: [top]
    solutions: [终止]
  - category: database
    symptom: CPU 使用率过高
    possible_causes: [慢查询]
    diagnosis_steps: [EXPLAIN]
    solutions: [优化]
""", encoding="utf-8")

        kb = KnowledgeBase(knowledge_dir=str(tmp_path))

        # 只搜索 system 分类
        results = kb.search("CPU", category="system")
        assert len(results) == 1
        assert results[0].category == "system"

    def test_search_limit(self, tmp_path):
        """测试搜索结果限制"""
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text("""
entries:
  - category: system
    symptom: CPU 使用率过高
    possible_causes: [死循环]
    diagnosis_steps: [top]
    solutions: [终止]
  - category: system
    symptom: CPU 温度过高
    possible_causes: [散热故障]
    diagnosis_steps: [sensors]
    solutions: [清理灰尘]
  - category: system
    symptom: CPU 频率异常
    possible_causes: [电源问题]
    diagnosis_steps: [检查频率]
    solutions: [更换电源]
""", encoding="utf-8")

        kb = KnowledgeBase(knowledge_dir=str(tmp_path))
        results = kb.search("CPU", limit=2)
        assert len(results) <= 2

    def test_get_context_for_agent(self, tmp_path):
        """测试为 Agent 生成上下文"""
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text("""
entries:
  - category: system
    symptom: 内存泄漏
    possible_causes: [缓存未释放]
    diagnosis_steps: [检查进程内存]
    solutions: [重启服务]
    severity: high
""", encoding="utf-8")

        kb = KnowledgeBase(knowledge_dir=str(tmp_path))
        context = kb.get_context_for_agent("内存泄漏")
        assert "内存泄漏" in context
        assert "缓存未释放" in context

    def test_empty_knowledge_dir(self):
        """测试空知识库目录"""
        kb = KnowledgeBase(knowledge_dir="/nonexistent/path")
        assert len(kb.entries) == 0
        context = kb.get_context_for_agent("CPU")
        assert "未找到" in context

    def test_get_all_categories(self, tmp_path):
        """测试获取所有分类"""
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text("""
entries:
  - category: system
    symptom: CPU 高
    possible_causes: [a]
    diagnosis_steps: [b]
    solutions: [c]
  - category: database
    symptom: 连接多
    possible_causes: [d]
    diagnosis_steps: [e]
    solutions: [f]
  - category: system
    symptom: 内存高
    possible_causes: [g]
    diagnosis_steps: [h]
    solutions: [i]
""", encoding="utf-8")

        kb = KnowledgeBase(knowledge_dir=str(tmp_path))
        categories = kb.get_all_categories()
        assert "system" in categories
        assert "database" in categories
