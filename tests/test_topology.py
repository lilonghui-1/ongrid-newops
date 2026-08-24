"""拓扑/RCA 模块测试 - TopologyGraph 构建、BFS 展开、工具封装"""

import pytest
from unittest.mock import MagicMock, patch

from src.knowledge.topology import (
    TopologyGraph,
    TopologyNode,
    TopologyRelation,
    ExpandTopologyTool,
    FindTopologyNodeTool,
)
from src.tools.base import ToolRegistry


def _build_sample_graph() -> TopologyGraph:
    """构建示例拓扑：
    gateway → app-a, app-b（depends_on，传播）
    app-a   → db-mysql（depends_on，传播）
    app-a   → cache-redis（depends_on，传播）
    cluster-1 member_of app-a（聚合，不传播）
    """
    g = TopologyGraph()
    g.add_node(TopologyNode(id=1, type="service", name="gateway"))
    g.add_node(TopologyNode(id=2, type="service", name="app-a"))
    g.add_node(TopologyNode(id=3, type="service", name="app-b"))
    g.add_node(TopologyNode(id=4, type="database", name="db-mysql"))
    g.add_node(TopologyNode(id=5, type="cache", name="cache-redis"))
    g.add_node(TopologyNode(id=6, type="cluster", name="app-cluster"))

    g.add_relation(TopologyRelation(src_id=1, dst_id=2, type="depends_on"))
    g.add_relation(TopologyRelation(src_id=1, dst_id=3, type="depends_on"))
    g.add_relation(TopologyRelation(src_id=2, dst_id=4, type="depends_on"))
    g.add_relation(TopologyRelation(src_id=2, dst_id=5, type="depends_on"))
    g.add_relation(TopologyRelation(src_id=6, dst_id=2, type="member_of"))
    return g


class TestTopologyGraph:
    """图结构与遍历测试"""

    def test_build_and_query(self):
        g = _build_sample_graph()
        assert len(g.nodes) == 6
        assert len(g.relations) == 5
        assert len(g.find_by_name("app")) == 3  # app-a / app-b / app-cluster

    def test_expand_downstream_propagating(self):
        g = _build_sample_graph()
        result = g.expand(node_id=1, depth=2, only_propagating=True, direction="downstream")
        # gateway 下游：app-a、app-b（1跳），db-mysql、cache-redis（2跳，经 app-a）
        names = {h.node_name for h in result.hits}
        assert names == {"app-a", "app-b", "db-mysql", "cache-redis"}
        # member_of 不传播，app-cluster 不应出现
        assert "app-cluster" not in names

    def test_expand_upstream(self):
        g = _build_sample_graph()
        result = g.expand(node_id=4, depth=2, only_propagating=True, direction="upstream")
        names = {h.node_name for h in result.hits}
        # db-mysql 上游：app-a（1跳）、gateway（2跳）
        assert "app-a" in names
        assert "gateway" in names

    def test_expand_missing_node(self):
        g = _build_sample_graph()
        result = g.expand(node_id=999, depth=2)
        assert result.count == 0
        assert "不存在" in result.note

    def test_load_from_yaml(self, tmp_path):
        yaml_path = tmp_path / "topology.yaml"
        yaml_path.write_text(
            """nodes:
  - {id: 1, type: service, name: gateway}
  - {id: 2, type: database, name: db}
relations:
  - {src: 1, dst: 2, type: depends_on}
""",
            encoding="utf-8",
        )
        g = TopologyGraph.from_yaml(str(yaml_path))
        assert len(g.nodes) == 2
        assert len(g.relations) == 1


class TestTopologyTools:
    """拓扑工具封装测试"""

    def setup_method(self):
        ToolRegistry.clear()

    def test_expand_tool_by_name(self, tmp_path):
        (tmp_path / "topology.yaml").write_text(
            """nodes:
  - {id: 1, type: service, name: gateway}
  - {id: 2, type: service, name: app-a}
  - {id: 3, type: database, name: db-mysql}
relations:
  - {src: 1, dst: 2, type: depends_on}
  - {src: 2, dst: 3, type: depends_on}
""",
            encoding="utf-8",
        )
        config = MagicMock()
        config.topology = MagicMock()
        config.topology.yaml_path = str(tmp_path / "topology.yaml")

        tool = ExpandTopologyTool(config)
        result = tool.execute(node="gateway", depth=2)
        assert result.success
        assert result.data["count"] == 2  # app-a + db-mysql

    def test_find_tool(self, tmp_path):
        (tmp_path / "topology.yaml").write_text(
            """nodes:
  - {id: 1, type: service, name: gateway}
  - {id: 2, type: service, name: app-a}
relations: []
""",
            encoding="utf-8",
        )
        config = MagicMock()
        config.topology = MagicMock()
        config.topology.yaml_path = str(tmp_path / "topology.yaml")

        tool = FindTopologyNodeTool(config)
        result = tool.execute(keyword="app")
        assert result.success
        assert result.data["count"] == 1

    def test_tool_missing_graph(self):
        tool = ExpandTopologyTool(None)
        result = tool.execute(node="不存在的节点")
        assert not result.success