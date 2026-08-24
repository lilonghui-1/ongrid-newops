---
AIGC:
  ContentProducer: '001191110102MAD55U9H0F10002'
  ContentPropagator: '001191110102MAD55U9H0F10002'
  Label: '1'
  ProduceID: '107722cb-13de-403f-a1ae-e4c803bcb302'
  PropagateID: '107722cb-13de-403f-a1ae-e4c803bcb302'
  ReservedCode1: '5ce75b07-7439-4a55-ad28-e95e564c3de9'
  ReservedCode2: '5ce75b07-7439-4a55-ad28-e95e564c3de9'
---

# ongrid-ops

新一代运维智能 Agent，以 Python 版 `ops-agent` 为底座，融合 ongrid 的声明式 Agent、
技能目录、MCP、可观测性、多渠道通知、拓扑/RCA 与命令安全等能力。

## 功能特性

- **智能调度**：Master Agent 统一调度，支持巡检 / 诊断 / 日志 / 自愈 / 复合任务，自动路由
  **声明式 Agent**（`agents/*.md` + `src/agents_loader.py`）执行。
- **技能目录**：`skills/*/SKILL.md` 声明式注册，`src/skills/` 运行时（manifest/loader/registry/
  executor）执行，自动注册进 `ToolRegistry`。
- **MCP 接入**：官方 `mcp` SDK 客户端，`config/mcp.yaml` 配置，tools 包装进 `ToolRegistry`。
- **可观测性**：Prometheus（PromQL）/ Loki（LogQL）/ Grafana 转跳，httpx 实现。
- **多渠道通知**：企微 / 钉钉 / 飞书 / Telegram / Slack / 邮件，统一 `Notifier` 抽象。
- **拓扑 / RCA**：`TopologyGraph`（节点/边/类型/依赖方向）+ `expand_topology`、`find_topology_node`，
  诊断链路接入影响面相关性。
- **命令安全**：`CommandPolicy` 只读沙箱（denylist、禁写/重定向、stdout 上限、超时）。
- **Web 管理平台**：FastAPI + Vue3，覆盖服务器 / 服务 / 告警 / 审计 / 对话 / 自愈规则 / 知识库 /
  日志 / 配置 / 参数 / 技能 / MCP / 拓扑。
- **自愈与审批**：自愈动作走 reviewer 门槛（`confirm_required`），定时任务 + 告警通知。

## 技术栈

| 组件 | 选型 |
|---|---|
| Agent 框架 | LangGraph + LangChain |
| LLM | ChatOpenAI（兼容 OpenAI/Qwen/DeepSeek/vLLM/Ollama） |
| Web | FastAPI + Vue3 + Element Plus |
| 存储 | SQLAlchemy（SQLite）+ Redis |
| 调度 | APScheduler |
| 可观测性 | Prometheus / Loki / Grafana |
| MCP | 官方 mcp SDK（Streamable HTTP） |

## 快速开始

```bash
# 1. 克隆（含 ongrid submodule）
git clone --recurse-submodules https://github.com/lilonghui-1/ongrid-ops.git
cd ongrid-ops

# 2. 后端
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                # 按需填写密钥
python -m src.main

# 3. 前端（可选，Web 管理）
cd web && npm install && npm run build
```

## 仓库结构

```
src/                 # Python 后端（agent/tools/knowledge/mcp/skills/web）
agents/              # 声明式 Agent 定义（*.md）
skills/              # 技能目录（SKILL.md）
web/                 # Vue3 前端
config/              # 配置文件（config/servers/rules/skills/mcp/triggers）
knowledge/           # 知识库 YAML
deploy/              # 部署资产（docker-compose/prometheus/loki/grafana/systemd）
docs/                # 操作手册 / 部署手册（docx）
reference/ongrid/    # ongrid 参考 submodule（AGPL-3.0，不参与编译）
```

## 许可证

- 本项目代码：MIT License（`LICENSE`）
- ongrid submodule（`reference/ongrid`）：AGPL-3.0，仅作能力参考，不参与编译（详见 `NOTICE`）

## 相关链接

- 底座：[lilonghui-1/ops-agent](https://github.com/lilonghui-1/ops-agent)（分支 trae/agent-sQ6GOz）
- 能力参考：[ongridio/ongrid](https://github.com/ongridio/ongrid)（AGPL-3.0）

> AI生成