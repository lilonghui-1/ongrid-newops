"""拓扑 / RCA 模块 - TopologyGraph + expand_topology / find_topology_node 工具

设计参考 ongrid 的拓扑管理概念（typed property graph + BFS 影响面展开），
本实现基于自实现邻接表（networkx 可选）全新编写。
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

from ..tools.base import BaseTool, ToolParameter, ToolResult, ToolRegistry

logger = logging.getLogger(__name__)


@dataclass
class TopologyNode:
    id: int
    type: str            # app/service/cluster/device/rack
    name: str
    props: Dict[str, object] = field(default_factory=dict)


@dataclass
class TopologyRelation:
    src_id: int
    dst_id: int
    type: str            # member_of/depends_on/deployed_on/replicates_to/monitors/routes_to/connected_to
    props: Dict[str, object] = field(default_factory=dict)


# 内置边语义（propagates=True 的边用于故障传播影响面计算）
RELATION_TYPES = {
    "member_of":      {"propagates": False, "semantics": "aggregation"},
    "depends_on":     {"propagates": True,  "semantics": "hard_dep"},
    "deployed_on":    {"propagates": True,  "semantics": "runtime_dep"},
    "replicates_to":  {"propagates": False, "semantics": "redundancy"},
    "monitors":       {"propagates": False, "semantics": "observation"},
    "routes_to":      {"propagates": True,  "semantics": "traffic"},
    "connected_to":   {"propagates": False, "semantics": "observation"},
}


@dataclass
class TopologyHit:
    """一次展开命中的扁平结构（LLM 友好）"""
    node_id: int
    node_name: str
    node_type: str
    hops: int
    relation_type: str
    semantics: str
    propagates: bool
    reached_via: str          # downstream | upstream | center
    via_node_id: Optional[int] = None
    via_node_name: Optional[str] = None


@dataclass
class ExpandResult:
    center: TopologyHit
    hops: int
    count: int
    hits: List[TopologyHit] = field(default_factory=list)
    note: str = ""


class TopologyGraph:
    """内存属性图：节点 + 有向边（边带类型与传播语义）"""

    def __init__(self):
        self.nodes: Dict[int, TopologyNode] = {}
        self.relations: List[TopologyRelation] = []
        self._adj: Dict[int, List[Tuple[int, TopologyRelation]]] = {}
        self._rev: Dict[int, List[Tuple[int, TopologyRelation]]] = {}

    # ---------- 构建 ----------
    def add_node(self, node: TopologyNode) -> None:
        self.nodes[node.id] = node
        self._adj.setdefault(node.id, [])
        self._rev.setdefault(node.id, [])

    def add_relation(self, rel: TopologyRelation) -> None:
        self.relations.append(rel)
        self._adj.setdefault(rel.src_id, []).append((rel.dst_id, rel))
        self._rev.setdefault(rel.dst_id, []).append((rel.src_id, rel))

    # ---------- 查询 ----------
    def find_by_name(self, keyword: str) -> List[TopologyNode]:
        """按名称/别名子串搜索节点"""
        kw = keyword.lower()
        result = []
        for n in self.nodes.values():
            if kw in n.name.lower() or kw in str(n.props.get("alias", "")).lower():
                result.append(n)
        return result

    def expand(self, node_id: int, depth: int = 2, only_propagating: bool = True,
               direction: str = "both") -> ExpandResult:
        """BFS 影响面展开（爆炸半径）

        出边（src→dst）为 downstream，入边为 upstream。
        only_propagating=True 时只保留 propagates=True 的边。
        """
        if node_id not in self.nodes:
            return ExpandResult(
                center=TopologyHit(node_id, "?", "?", 0, "", "", False, "center"),
                hops=0, count=0, hits=[], note="节点不存在",
            )
        center = self.nodes[node_id]
        center_hit = TopologyHit(
            node_id=node_id, node_name=center.name, node_type=center.type,
            hops=0, relation_type="", semantics="", propagates=True, reached_via="center",
        )

        depth = max(1, min(int(depth), 5))
        visited: Dict[int, TopologyHit] = {node_id: center_hit}
        queue = deque([(node_id, 0)])
        hits: List[TopologyHit] = []

        while queue:
            cur, cur_depth = queue.popleft()
            if cur_depth >= depth:
                continue

            edges: List[Tuple[int, TopologyRelation, str]] = []
            if direction in ("both", "downstream"):
                for (dst, rel) in self._adj.get(cur, []):
                    edges.append((dst, rel, "downstream"))
            if direction in ("both", "upstream"):
                for (src, rel) in self._rev.get(cur, []):
                    edges.append((src, rel, "upstream"))

            for nid, rel, via in edges:
                meta = RELATION_TYPES.get(rel.type, {"propagates": False, "semantics": "annotation"})
                if only_propagating and not meta["propagates"]:
                    continue
                if nid in visited or nid not in self.nodes:
                    continue
                target = self.nodes[nid]
                hit = TopologyHit(
                    node_id=nid, node_name=target.name, node_type=target.type,
                    hops=cur_depth + 1,
                    relation_type=rel.type,
                    semantics=meta["semantics"],
                    propagates=meta["propagates"],
                    reached_via=via,
                    via_node_id=cur,
                    via_node_name=visited[cur].node_name if visited[cur] else None,
                )
                visited[nid] = hit
                hits.append(hit)
                queue.append((nid, cur_depth + 1))

        note = "已过滤非传播边" if only_propagating else "含全部边"
        if not hits:
            note = "无传播可达节点" if only_propagating else "无可达节点"
        return ExpandResult(
            center=center_hit, hops=depth, count=len(hits), hits=hits, note=note,
        )

    # ---------- 加载 ----------
    @classmethod
    def from_yaml(cls, path: str = "knowledge/topology.yaml") -> "TopologyGraph":
        graph = cls()
        p = Path(path)
        if not p.exists():
            logger.warning(f"拓扑文件不存在: {path}")
            return graph
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        for n in data.get("nodes") or []:
            graph.add_node(TopologyNode(
                id=int(n["id"]), type=str(n.get("type", "device")),
                name=str(n["name"]), props=dict(n.get("props") or {}),
            ))
        for r in data.get("relations") or []:
            graph.add_relation(TopologyRelation(
                src_id=int(r["src"]), dst_id=int(r["dst"]),
                type=str(r.get("type", "connected_to")),
                props=dict(r.get("props") or {}),
            ))
        return graph


class ExpandTopologyTool(BaseTool):
    """拓扑影响面展开工具"""

    name = "expand_topology"
    description = "展开拓扑影响面：输入节点名或 id，返回受影响上下游节点（BFS）"
    parameters = [
        ToolParameter(name="node", type="string", description="节点名称关键词或节点 id"),
        ToolParameter(name="depth", type="integer", description="展开深度（1-5，默认 2）", required=False, default=2),
        ToolParameter(name="direction", type="string", description="方向: both/downstream/upstream（默认 both）", required=False, default="both"),
        ToolParameter(name="only_propagating", type="boolean", description="只保留传播故障的边（默认 true）", required=False, default=True),
    ]

    def __init__(self, config=None):
        path = self._resolve_path(config)
        try:
            self._graph = TopologyGraph.from_yaml(path)
        except Exception as e:
            logger.error(f"拓扑加载失败: {e}")
            self._graph = TopologyGraph()

    @staticmethod
    def _resolve_path(config) -> str:
        if config and hasattr(config, "topology"):
            return getattr(config.topology, "yaml_path", "knowledge/topology.yaml")
        return "knowledge/topology.yaml"

    def execute(self, **kwargs) -> ToolResult:
        node_key = str(kwargs["node"])
        depth = int(kwargs.get("depth", 2))
        direction = kwargs.get("direction", "both")
        only_propagating = bool(kwargs.get("only_propagating", True))

        if node_key.isdigit():
            nid = int(node_key)
        else:
            matches = self._graph.find_by_name(node_key)
            if not matches:
                return ToolResult(success=False, error=f"未找到拓扑节点: {node_key}")
            nid = matches[0].id

        result = self._graph.expand(nid, depth=depth, only_propagating=only_propagating, direction=direction)
        return ToolResult(
            success=True,
            data={
                "center": {
                    "node_id": result.center.node_id,
                    "node_name": result.center.node_name,
                    "node_type": result.center.node_type,
                },
                "depth": result.hops,
                "count": result.count,
                "hits": [
                    {
                        "node_id": h.node_id, "node_name": h.node_name, "node_type": h.node_type,
                        "hops": h.hops, "relation_type": h.relation_type, "semantics": h.semantics,
                        "propagates": h.propagates, "reached_via": h.reached_via,
                        "via_node_id": h.via_node_id, "via_node_name": h.via_node_name,
                    }
                    for h in result.hits
                ],
                "note": result.note,
            },
            metadata={"node": node_key, "depth": depth, "direction": direction},
        )


class FindTopologyNodeTool(BaseTool):
    """拓扑节点搜索工具"""

    name = "find_topology_node"
    description = "按名称关键词搜索拓扑节点（返回节点 id/type/名称）"
    parameters = [
        ToolParameter(name="keyword", type="string", description="节点名称关键词"),
    ]

    def __init__(self, config=None):
        path = ExpandTopologyTool._resolve_path(config)
        try:
            self._graph = TopologyGraph.from_yaml(path)
        except Exception:
            self._graph = TopologyGraph()

    def execute(self, **kwargs) -> ToolResult:
        keyword = str(kwargs["keyword"])
        matches = self._graph.find_by_name(keyword)
        return ToolResult(
            success=True,
            data={
                "count": len(matches),
                "nodes": [
                    {"node_id": n.id, "type": n.type, "name": n.name, "props": n.props}
                    for n in matches
                ],
            },
        )


def register_topology_tools(config=None) -> None:
    ToolRegistry.register(ExpandTopologyTool(config))
    ToolRegistry.register(FindTopologyNodeTool(config))