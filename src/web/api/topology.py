"""拓扑 / RCA 管理路由 - 查看拓扑图、展开影响面、搜索节点

端点：
- GET  /           : 拓扑图概览（节点+关系摘要）
- GET  /expand     : 展开某节点的影响面（BFS）
- GET  /search     : 按名称搜索节点
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..core.deps import get_current_active_user
from ..models.user import User
from ...knowledge.topology import TopologyGraph
from ...tools.base import ToolRegistry
from ...utils.config_loader import ConfigLoader

logger = logging.getLogger(__name__)

router = APIRouter(tags=["拓扑管理"])


def _get_graph() -> TopologyGraph:
    """加载拓扑图（按配置定位 yaml 路径）"""
    try:
        config = ConfigLoader.get_instance().config
        yaml_path = getattr(config.topology, "yaml_path", "knowledge/topology.yaml")
    except Exception:
        yaml_path = "knowledge/topology.yaml"
    try:
        return TopologyGraph.from_yaml(yaml_path)
    except Exception as e:
        logger.error(f"拓扑加载失败: {e}")
        return TopologyGraph()


@router.get("/", summary="拓扑图概览")
def get_topology(
    current_user: User = Depends(get_current_active_user),
):
    """返回拓扑节点与关系摘要"""
    graph = _get_graph()
    return {
        "node_count": len(graph.nodes),
        "relation_count": len(graph.relations),
        "nodes": [
            {"node_id": n.id, "type": n.type, "name": n.name, "props": n.props}
            for n in graph.nodes.values()
        ],
        "relations": [
            {"src": r.src_id, "dst": r.dst_id, "type": r.type}
            for r in graph.relations
        ],
    }


@router.get("/expand", summary="展开影响面")
def expand_topology(
    node: str = Query(..., description="节点名称关键词或节点 id"),
    depth: int = Query(2, ge=1, le=5, description="展开深度"),
    direction: str = Query("both", pattern="^(both|downstream|upstream)$"),
    only_propagating: bool = Query(True, description="只保留传播故障的边"),
    current_user: User = Depends(get_current_active_user),
):
    """展开指定节点的上下游影响面（BFS）"""
    tool = ToolRegistry.get("expand_topology")
    if not tool:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="拓扑工具未注册")
    result = tool.execute(
        node=node, depth=depth, direction=direction, only_propagating=only_propagating,
    )
    if not result.success:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=result.error)
    return result.data


@router.get("/search", summary="搜索节点")
def search_topology(
    keyword: str = Query(..., description="节点名称关键词"),
    current_user: User = Depends(get_current_active_user),
):
    """按名称/别名搜索拓扑节点"""
    graph = _get_graph()
    matches = graph.find_by_name(keyword)
    return {
        "keyword": keyword,
        "total": len(matches),
        "nodes": [
            {"node_id": n.id, "type": n.type, "name": n.name, "props": n.props}
            for n in matches
        ],
    }