---
AIGC:
  ContentProducer: '001191110102MAD55U9H0F10002'
  ContentPropagator: '001191110102MAD55U9H0F10002'
  Label: '1'
  ProduceID: '0085f094-5268-48e5-881c-dfe7181fbe65'
  PropagateID: '0085f094-5268-48e5-881c-dfe7181fbe65'
  ReservedCode1: '10e8800c-a52d-4b96-b643-b9f2927eddcf'
  ReservedCode2: '10e8800c-a52d-4b96-b643-b9f2927eddcf'
---

# ongrid-ops（中文说明）

新一代智能运维 Agent：以 Python 版 `ops-agent` 为底座，融合 ongrid 的
声明式 Agent、技能目录、MCP、可观测性、多渠道通知、拓扑/RCA 与命令安全等能力。

> 能力来源 [ongridio/ongrid](https://github.com/ongridio/ongrid)（AGPL-3.0）以 git submodule
> 形式挂载于 `reference/ongrid`，仅作参考、不参与编译。本项目自研代码采用 MIT License。

## 功能特性

- **智能调度**：巡检 / 诊断 / 日志 / 自愈 / 复合任务自动路由，支持巡检→诊断(RCA)→自愈端到端链路。
- **声明式 Agent**：`agents/*.md`（YAML frontmatter + 中文提示词），`src/agents_loader.py`
  自动注册可路由专家；支持工具白名单、禁用清单、回合预算、只读/写权限模式。
- **技能目录**：`skills/*/SKILL.md`，运行时 `src/skills/` 支持 `function` 与 `subprocess` 两种
  执行模式，自动注册进 `ToolRegistry`。
- **MCP 接入**：官方 `mcp` SDK 客户端，`config/mcp.yaml` 注册外部 MCP server，其 tools
  包装进 `ToolRegistry` 供 Agent 调用。
- **可观测性**：`PrometheusQueryTool`（PromQL 即时/区间）、`LokiQueryTool`（LogQL 查询与标签）、
  `GrafanaTool`（dashboard 转跳），`config.yaml → observability` 配置地址。
- **多渠道通知**：企微、钉钉、飞书（Lark）、Telegram、Slack、邮件，统一 `Notifier` 抽象与重试。
- **拓扑 / RCA**：`TopologyGraph` 属性图（节点/边/关联边/依赖方向），`expand_topology` 影响面
  BFS 分析、`find_topology_node` 搜索；Master 诊断链路接入拓扑相关性上下文。
- **命令安全**：`CommandPolicy` 只读沙箱——denylist 命令（rm/sh/sudo/重定向等）、stdout 上限
  （64KiB）、超时控制，自愈动作经 reviewer 门槛。
- **Web 管理平台**：FastAPI + Vue3 + Element Plus，覆盖服务器 / 服务 / 告警 / 审计 / 对话 /
  自愈规则 / 知识库 / 日志 / 配置 / 参数 / 技能 / MCP / 拓扑页面。
- **自愈与审批**：自愈动作 `confirm_required` 审批门槛；定时任务（APScheduler）；告警通知。

## 技术栈

| 组件 | 选型 |
|---|---|
| Agent 框架 | LangGraph + LangChain（create_react_agent） |
| LLM | ChatOpenAI（OpenAI / Qwen / DeepSeek / vLLM / Ollama） |
| Web | FastAPI + Vue3 + Element Plus |
| 存储 | SQLAlchemy 2.0（SQLite）+ Redis |
| 调度 | APScheduler |
| 可观测性 | Prometheus / Loki / Grafana |
| MCP | 官方 mcp SDK（Streamable HTTP / SSE） |
| 拓扑 | networkx（可选依赖） |

## 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+（构建 Web）
- 可选：Prometheus / Loki / Grafana、外部 MCP server、Redis

### 克隆

```bash
git clone --recurse-submodules https://github.com/lilonghui-1/ongrid-ops.git
cd ongrid-ops
```

### 后端启动

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows
.venv\Scripts\activate

pip install -r requirements.txt
cp .env.example .env      # 配置密钥（LLM/SSH/DB/IM/可观测性/MCP）
python -m src.main
```

### 前端构建

```bash
cd web
npm install
npm run build
```

### Docker Compose（可选）

```bash
docker compose -f deploy/docker-compose.yml up -d
```

## 目录结构

```
ongrid-ops/
├── agents/                  # 声明式 Agent 定义（*.md）
├── skills/                  # 技能目录（SKILL.md）
├── src/
│   ├── agent/               # Master / 专业 Agent / 专家运行器
│   ├── agents_loader.py     # agents/*.md 解析与注册
│   ├── knowledge/           # 知识库 + 拓扑
│   ├── mcp/                 # MCP 客户端
│   ├── models/              # LLM 工厂 / 提示词
│   ├── skills/              # 技能运行时
│   ├── tools/               # 工具层
│   ├── utils/               # 工具函数
│   └── web/                 # FastAPI 后端
├── web/                     # Vue3 前端
├── config/                  # 配置
├── knowledge/               # 知识库 YAML
├── deploy/                  # 部署资产
├── reference/ongrid/        # ongrid submodule（AGPL-3.0，仅参考）
├── docs/                    # 操作手册 / 部署手册
├── LICENSE                  # MIT
└── NOTICE                   # 许可证与融合声明
```

## 许可证

- 本项目代码：MIT（见 LICENSE）
- `reference/ongrid` submodule：AGPL-3.0（见 NOTICE，仅作参考，不参与编译）

## 相关链接

- 底座：lilonghui-1/ops-agent（trae/agent-sQ6GOz）
- 能力参考：ongridio/ongrid（AGPL-3.0）

> AI生成