---
AIGC:
  ContentProducer: '001191110102MAD55U9H0F10002'
  ContentPropagator: '001191110102MAD55U9H0F10002'
  Label: '1'
  ProduceID: '28b23867-9d63-4cad-a12d-815bd0cc9278'
  PropagateID: '28b23867-9d63-4cad-a12d-815bd0cc9278'
  ReservedCode1: 'e8561490-64b6-4696-83c7-6038978dd594'
  ReservedCode2: 'e8561490-64b6-4696-83c7-6038978dd594'
---

# 运维 Agent 部署手册

[TOC]

## 一、部署架构与端口

### 1.1 架构概览

运维 Agent 采用前后端分离架构，可选集成可观测性组件：

| 组件 | 技术栈 | 端口 | 说明 |
|------|--------|------|------|
| 后端 | Python (FastAPI + LangGraph) | 8000 | Web API + WebSocket + 静态文件挂载 |
| 前端 | Vue3 + Vite | (构建产物) | 由后端挂载 `web/dist/` |
| 数据库 | SQLite (默认) / MySQL | - | 存储用户/审计/告警/知识等 |
| Redis | redis-py | 6379 | 缓存（可选） |
| Prometheus | Go | 9090 | 指标采集（可选） |
| Loki | Go | 3100 | 日志聚合（可选） |
| Grafana | Go | 3000 | 可视化面板（可选） |

### 1.2 数据流

```
用户 → Nginx(可选) → FastAPI(8000) → Agent层 → 工具层 → SSH/DB/IM/Prometheus/Loki
                         ↓
                    SQLite/MySQL
```

## 二、环境要求

| 组件 | 版本要求 | 说明 |
|------|---------|------|
| Python | >= 3.10 | 后端运行环境（推荐 3.12） |
| Node.js | >= 18 | 前端构建环境（推荐 20+） |
| npm | >= 9 | 前端包管理 |
| Git | >= 2.0 | 代码拉取与 submodule |
| 网络 | 可访问目标服务器 SSH 端口 | 远程巡检/运维必需 |
| 网络 | 可访问 LLM API | Agent 与 AI 对话必需 |

> 如需连接国产数据库，还需按需安装驱动（见 3.4 后端部署）。

## 三、快速安装

### 3.1 克隆代码

```bash
# 克隆仓库（含 submodule）
git clone --recurse-submodules https://github.com/lilonghui-1/ongrid-ops.git
cd ongrid-ops
```

> 如已克隆但未带 submodule，执行 `git submodule update --init`。

### 3.2 后端依赖安装

```bash
# 推荐创建虚拟环境
python3 -m venv venv
source venv/bin/activate    # Linux/Mac
# 或 venv\Scripts\activate   # Windows

# 安装依赖
pip install -r requirements.txt
```

### 3.3 国产数据库驱动（可选）

```bash
# 按需安装
pip install oracledb>=2.0.0       # Oracle（纯 Python，无需客户端）
pip install dmPython>=2.4.0       # 达梦（需从官网下载 whl，设置 DM_HOME）
pip install ksycopg2>=2.8.0       # 人大金仓（纯 Python）
```

### 3.4 前端构建

```bash
cd web
npm install
npm run build
cd ..
```

构建产物输出到 `web/dist/`，后端自动挂载。

### 3.5 配置文件

系统使用以下配置文件（位于 `config/` 目录）：

| 文件 | 职责 |
|------|------|
| config.yaml | LLM、通知渠道、调度、日志平台、Web、邮件、告警阈值、可观测性、IM 渠道 |
| servers.yaml | 服务器列表、SSH 连接、数据库连接 |
| rules.yaml | 自愈规则（触发条件 + 执行操作 + 确认级别） |
| mcp.yaml | MCP Server 注册 |
| skills.yaml | 技能启用/停用 |
| triggers.yaml | 事件触发器 |

### 3.6 环境变量

复制 `.env.example` 为 `.env` 并填写：

```bash
# LLM
OPENAI_API_KEY=sk-xxxxxx
OPENAI_BASE_URL=https://api.openai.com/v1

# Web 安全
OPS_AGENT_SECRET_KEY=your-secret-key-here

# SSH
SSH_PRIVATE_KEY_PATH=/path/to/id_rsa

# 数据库
MYSQL_PASSWORD=your-password

# 通知渠道
WECOM_WEBHOOK=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx
DINGTALK_WEBHOOK=https://oapi.dingtalk.com/robot/send?access_token=xxx
FEISHU_WEBHOOK=https://open.feishu.cn/open-apis/bot/v2/hook/xxx
TELEGRAM_BOT_TOKEN=xxxxxx
TELEGRAM_CHAT_ID=xxxxxx
SLACK_WEBHOOK=https://hooks.slack.com/services/xxx

# 可观测性
PROMETHEUS_URL=http://localhost:9090
LOKI_URL=http://localhost:3100
GRAFANA_URL=http://localhost:3000

# MCP
KUBECONFIG_PATH=/path/to/kubeconfig
```

### 3.7 初始化与启动

```bash
# 启动后端（默认监听 0.0.0.0:8000）
python main.py
# 或
uvicorn src.web.app:create_app --host 0.0.0.0 --port 8000 --factory
```

首次启动自动创建 SQLite 数据库和默认管理员（admin / admin123）。

### 3.8 访问验证

浏览器访问 `http://<服务器IP>:8000`，使用默认管理员登录后立即修改密码。

## 四、配置说明

### 4.1 config.yaml — 主配置

| 配置段 | 说明 | 关键字段 |
|--------|------|---------|
| llm | LLM 服务 | provider、api_key、base_url、model、temperature、max_tokens |
| llm_models | Web 端 AI 对话可选模型 | gpt-4 / qwen-plus / deepseek-chat 等 |
| notify | 通知渠道 | wecom_webhook、dingtalk_webhook |
| email | 邮件通知 | smtp_host、smtp_port、smtp_user/password、from_addr、to_addrs |
| log_level | 日志级别 | DEBUG / INFO / WARNING / ERROR |
| log_platforms | 日志平台（ES/Loki） | type、url、index、username/password |
| schedule | 定时巡检/日志分析 | cron 表达式、enabled |
| web | Web 平台 | host、port、secret_key、默认账号 |
| thresholds | 告警阈值 | cpu、memory、disk |
| observability | 可观测性 | prometheus_url、loki_url、grafana_url |
| im_channels | IM 渠道 | feishu_webhook、telegram_bot_token、slack_webhook |

### 4.2 servers.yaml — 服务器配置

```yaml
servers:
  - name: "web-server-01"
    host: "192.168.1.10"
    port: 22
    username: "ops"
    private_key_path: "${SSH_PRIVATE_KEY_PATH}"
    os_type: "linux"
    tags: ["web", "production"]
    databases:
      - type: "mysql"
        host: "127.0.0.1"
        port: 3306
        username: "monitor"
        password: "${MYSQL_PASSWORD}"
        name: "app_db"
```

### 4.3 rules.yaml — 自愈规则

```yaml
heal_rules:
  - name: "restart_nginx"
    condition: "nginx_status == 'stopped'"
    actions:
      - tool: "service_control"
        params:
          service_name: "nginx"
          action: "restart"
        confirm_required: false
    description: "Nginx 停止时自动重启"
```

### 4.4 mcp.yaml — MCP Server 注册

```yaml
mcp_servers:
  - name: "kubernetes-mcp"
    url: "http://localhost:9001/mcp"
    headers:
      Authorization: "Bearer ${MCP_HTTP_TOKEN}"
    enabled: true
  - name: "monitor"
    url: "http://monitor-mcp:9002/mcp"
    headers: {}
    enabled: true
```

> 注意：顶层键名为 `mcp_servers`（非 `servers`），实际仓库 `config/mcp.yaml` 中示例均使用该键名。

### 4.5 .env — 环境变量

所有密钥通过 `.env` 注入，配置文件中使用 `${ENV_VAR}` 占位符递归解析。参考 `.env.example` 模板。

## 五、后端部署

### 5.1 systemd 服务（推荐生产环境）

```bash
sudo tee /etc/systemd/system/ongrid-ops.service << 'EOF'
[Unit]
Description=Ongrid-Ops Agent Web Management Platform
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/opt/ongrid-ops
EnvironmentFile=/opt/ongrid-ops/.env
ExecStart=/opt/ongrid-ops/venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable ongrid-ops
sudo systemctl start ongrid-ops
```

### 5.2 常用管理命令

```bash
sudo systemctl status ongrid-ops    # 查看状态
sudo systemctl restart ongrid-ops   # 重启
sudo systemctl stop ongrid-ops      # 停止
sudo journalctl -u ongrid-ops -f     # 查看日志
```

### 5.3 数据库迁移

默认使用 SQLite（`data/ops_agent_web.db`），自动创建。如需使用 MySQL：

1. 在 `config.yaml` 或环境变量中配置 MySQL 连接
2. 运行 `python -m src.web.database init_db` 初始化表结构
3. 重启服务

### 5.4 Docker 部署

```bash
# 使用 docker-compose 一键部署
cd deploy
docker-compose up -d
```

详见 `deploy/docker-compose.yml`。

## 六、前端构建与 Nginx

### 6.1 构建前端

```bash
cd web
npm install
npm run build
cd ..
```

### 6.2 Nginx 反向代理（可选）

```nginx
server {
    listen 80;
    server_name ops.example.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    location /ws {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

## 七、可观测性组件部署

可观测性组件（Prometheus、Loki、Grafana）为 Agent 提供指标查询（PromQL）、日志查询（LogQL）与可视化面板能力。仓库 `deploy/` 目录已预置全部配置文件，推荐使用 Docker Compose 一键部署。

### 7.1 部署架构

```
┌─────────────────────────────────────────────────────────┐
│                     docker-compose                      │
│  ┌──────────┐    ┌────────────┐    ┌────────────────┐  │
│  │  ongrid  │    │ Prometheus │    │     Loki       │  │
│  │  -ops    │───▶│   :9090    │    │    :3100       │  │
│  │  :8000   │    └────────────┘    └────────────────┘  │
│  │          │         │                  │             │
│  │          │         ▼                  ▼             │
│  │          │    ┌────────────────┐                    │
│  │          │    │    Grafana     │                    │
│  │          │    │    :3000       │                    │
│  └──────────┘    └────────────────┘                    │
└─────────────────────────────────────────────────────────┘
```

各组件职责：

| 组件 | 端口 | 职责 | Agent 对接配置 |
|------|------|------|---------------|
| Prometheus | 9090 | 指标采集与 PromQL 查询 | `observability.prometheus_url` |
| Loki | 3100 | 日志聚合与 LogQL 查询 | `observability.loki_url` / `log_platforms` |
| Grafana | 3000 | 可视化面板与 Dashboard 跳转 | `observability.grafana_url` |
| Node Exporter | 9100 | 目标服务器指标采集（可选） | Prometheus scrape 目标 |

### 7.2 Prometheus 部署

#### 7.2.1 配置文件说明

仓库已提供 `deploy/prometheus/prometheus.yml`：

```yaml
# Prometheus 采集配置
global:
  scrape_interval: 15s          # 全局采集间隔
  evaluation_interval: 15s      # 规则评估间隔（告警规则用）

scrape_configs:
  - job_name: "prometheus"
    static_configs:
      - targets: ["localhost:9090"]   # 采集 Prometheus 自身

  # ops-agent 自监控（如暴露 /metrics）
  - job_name: "ops-agent"
    static_configs:
      - targets: ["ops-agent:8000"]   # Docker Compose 内网地址
    metrics_path: /metrics

  # 目标服务器 Node Exporter（按需启用）
  # - job_name: "node"
  #   static_configs:
  #     - targets:
  #         - "192.168.1.10:9100"     # 服务器 A 的 Node Exporter
  #         - "192.168.1.20:9100"     # 服务器 B 的 Node Exporter
```

#### 7.2.2 启动 Prometheus

```bash
cd deploy
docker-compose up -d prometheus
```

#### 7.2.3 验证

1. 访问 `http://localhost:9090`，进入 Prometheus Web UI
2. 点击 **Status → Targets**，确认 `prometheus` 与 `ops-agent` 两个 job 均为 **UP**
3. 在 **Graph** 页输入 PromQL 验证查询，例如：

```promql
up{job="ops-agent"}
```

返回值为 `1` 表示采集正常。

#### 7.2.4 Agent 对接

编辑 `config/config.yaml`：

```yaml
observability:
  prometheus_url: "${PROMETHEUS_URL}"   # 如 http://localhost:9090 或 http://prometheus:9090
```

- 本机部署填 `http://localhost:9090`
- Docker Compose 内填 `http://prometheus:9090`（服务名）
- 修改后触发配置热重载（Web「本地配置管理」或重启服务）

#### 7.2.5 目标服务器 Node Exporter（可选）

如需采集被管服务器的 CPU/内存/磁盘指标，在每台目标服务器安装 Node Exporter：

```bash
# 在目标服务器上
wget https://github.com/prometheus/node_exporter/releases/download/v1.8.2/node_exporter-1.8.2.linux-amd64.tar.gz
tar zxvf node_exporter-1.8.2.linux-amd64.tar.gz
cd node_exporter-1.8.2.linux-amd64
nohup ./node_exporter --web.listen-address=:9100 &

# 验证
curl http://localhost:9100/metrics | head
```

然后在 `prometheus.yml` 中取消 `node` job 的注释，添加目标服务器 IP，重启 Prometheus。

### 7.3 Loki 部署

#### 7.3.1 配置文件

仓库中 `deploy/loki/loki.yaml`（单实例、文件系统存储、TSDB 索引）：

```yaml
# Loki 配置（单实例模式）
auth_enabled: false

server:
  http_listen_port: 3100

common:
  path_prefix: /loki
  storage:
    filesystem:
      chunks_directory: /loki/chunks
      rules_directory: /loki/rules
  replication_factor: 1
  ring:
    instance_addr: 127.0.0.1
    kvstore:
      store: inmemory

schema_config:
  configs:
    - from: 2024-01-01
      store: tsdb
      object_store: filesystem
      schema: v13
      index:
        prefix: index_
        period: 24h

limits_config:
  allow_structured_metadata: true
```

#### 7.3.2 启动 Loki

```bash
cd deploy
docker-compose up -d loki
```

#### 7.3.3 验证

1. 访问 `http://localhost:3100/ready`，返回 `ready` 表示就绪
2. 用 LogQL 查询验证（需有日志流入）：

```bash
curl -G 'http://localhost:3100/loki/api/v1/query_range' \
  --data-urlencode 'query={job="app"}' \
  --data-urlencode 'start=2026-08-24T00:00:00Z' \
  --data-urlencode 'end=2026-08-24T23:59:59Z'
```

#### 7.3.4 Agent 对接

方式一：作为日志平台接入（`config/config.yaml`）：

```yaml
log_platforms:
  - name: "loki"
    type: "loki"
    url: "${LOKI_URL}"            # 如 http://localhost:3100
```

方式二：作为可观测性配置接入：

```yaml
observability:
  loki_url: "${LOKI_URL}"         # 如 http://localhost:3100
```

两种方式二选一或同时配置均可，Agent 的 LokiQueryTool 会自动发现并使用。

#### 7.3.5 日志采集（Promtail / 应用直推）

Loki 本身不采集日志，需要采集器推送。常见方案：

- **Promtail**（官方）：部署在各服务器，读取日志文件推送至 Loki
- **Docker 日志驱动**：`docker run --log-driver=loki` 直接推送容器日志
- **应用直推**：应用调用 Loki Push API（`POST /loki/api/v1/push`）

Promtail 示例配置（`promtail.yaml`）：

```yaml
server:
  http_listen_port: 9080
  grpc_listen_port: 0

positions:
  filename: /tmp/positions.yaml

clients:
  - url: http://loki:3100/loki/api/v1/push

scrape_configs:
  - job_name: app-logs
    static_configs:
      - targets: [localhost]
        labels:
          job: app
          __path__: /var/log/app/*.log
```

### 7.4 Grafana 部署

#### 7.4.1 配置文件

仓库 `deploy/grafana/provisioning/` 已预置数据源与 Dashboard 自动加载：

**数据源**（`datasources/datasources.yml`）：

```yaml
apiVersion: 1

datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
    editable: false

  - name: Loki
    type: loki
    access: proxy
    url: http://loki:3100
    editable: false
```

**Dashboard 自动加载**（`dashboards/providers.yml`）：

```yaml
apiVersion: 1

providers:
  - name: 'ops-agent'
    orgId: 1
    folder: ''
    type: file
    disableDeletion: false
    updateIntervalSeconds: 30
    allowUiUpdates: true
    options:
      path: /var/lib/grafana/dashboards   # 将 JSON 格式 Dashboard 放入该目录
      foldersFromFilesStructure: true
```

#### 7.4.2 启动 Grafana

```bash
cd deploy
docker-compose up -d grafana
```

#### 7.4.3 访问与验证

1. 访问 `http://localhost:3000`，默认账号密码 `admin / admin123`（可通过环境变量 `GF_SECURITY_ADMIN_PASSWORD` 覆盖）
2. 首次登录提示修改密码
3. 进入 **Configuration → Data Sources**，确认 Prometheus 与 Loki 数据源状态为 **OK**
4. 如需自定义 Dashboard，将 JSON 文件放入 `deploy/grafana/dashboards/` 目录，30 秒内自动加载

#### 7.4.4 Agent 对接

```yaml
observability:
  grafana_url: "${GRAFANA_URL}"     # 如 http://localhost:3000
```

配置后 Agent 的 GrafanaTool 可生成 Dashboard 跳转链接，在诊断结果中一键直达相关面板。

### 7.5 Docker Compose 全量部署

```bash
cd deploy
docker-compose up -d
```

启动全部服务（后端 + Prometheus + Loki + Grafana），各服务自动加入 `ops-net` 网络：

| 服务 | 容器内地址 | 宿主机端口 |
|------|-----------|-----------|
| ongrid-ops | ongrid-ops:8000 | 8000 |
| prometheus | prometheus:9090 | 9090 |
| loki | loki:3100 | 3100 |
| grafana | grafana:3000 | 3000 |

查看状态：

```bash
docker-compose ps
docker-compose logs -f ongrid-ops
```

停止服务：

```bash
docker-compose down          # 停止并删除容器（保留数据卷）
docker-compose down -v       # 停止并删除容器与数据卷（数据清空，慎用）
```

### 7.6 常见排障

| 问题 | 排查方法 |
|------|---------|
| Prometheus 目标 DOWN | 检查抓取地址、网络连通、Node Exporter 是否运行 |
| Loki 查询无数据 | 检查是否有日志流入（promtail/直推）、时间范围是否正确 |
| Grafana 数据源报错 | 容器内需用服务名 `http://prometheus:9090`，宿主机用 `localhost` |
| 端口冲突 | 修改 `docker-compose.yml` 中宿主机端口映射 |
| 数据丢失 | 检查数据卷 `ops_agent_data` 是否存在，勿用 `down -v` 误删 |

## 八、IM 通道与 MCP 注册

本章介绍如何配置即时通讯（IM）告警/通知通道、注册外部 MCP Server、以及启停技能。系统支持**企业微信 / 钉钉 / 飞书 / Telegram / Slack** 五种 IM 渠道，全部通过 `.env` 注入密钥，配置文件中使用 `${ENV_VAR}` 占位符。

### 8.1 IM 渠道配置

所有 IM 渠道的密钥统一在 `.env` 中配置（参考 `.env.example`），配置文件 `config/config.yaml` 中已声明对应占位符，无需修改。渠道分为两类：

| 分类 | 配置段 | 渠道 |
|------|--------|------|
| 基础通知 | `notify` | 企业微信、钉钉 |
| 即时通讯 | `im_channels` | 飞书、Telegram、Slack |

#### 8.1.1 企业微信（notify.wecom_webhook）

1. 登录企业微信管理后台 →「群机器人」→「添加机器人」
2. 复制 Webhook 地址，格式：
   ```
   https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxxxxxxx
   ```
3. 在 `.env` 中配置：
   ```bash
   WECOM_WEBHOOK=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxxxxxxx
   ```
4. 验证：向机器人发送一条测试消息，或在 Web 平台「通知测试」中发送

#### 8.1.2 钉钉（notify.dingtalk_webhook + dingtalk_secret）

1. 钉钉群 →「群设置」→「智能群助手」→「添加机器人」→「自定义」
2. 获取 Webhook，格式：
   ```
   https://oapi.dingtalk.com/robot/send?access_token=xxxxxxxx
   ```
3. 安全设置中选择「加签」，获取 `SEC` 开头的密钥
4. 在 `.env` 中配置：
   ```bash
   DINGTALK_WEBHOOK=https://oapi.dingtalk.com/robot/send?access_token=xxxxxxxx
   DINGTALK_SECRET=SECxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```
5. 验证：钉钉群内发送测试消息

> 若机器人安全设置选择「自定义关键词」，需确保消息文本包含该关键词。

#### 8.1.3 飞书（im_channels.lark_webhook + lark_secret）

1. 飞书群 →「设置」→「群机器人」→「添加机器人」→「自定义机器人」
2. 获取 Webhook（格式 `https://open.feishu.cn/open-apis/bot/v2/hook/xxxx`）
3. 安全设置可选「签名校验」（生成 `Secret`）
4. 在 `.env` 中配置：
   ```bash
   LARK_WEBHOOK=https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxx
   LARK_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx   # 可选，未开启签名可不填
   ```
5. 验证：飞书群内发送测试消息

#### 8.1.4 Telegram（im_channels.telegram_bot_token + telegram_chat_id）

1. 在 Telegram 中向 **@BotFather** 发送 `/newbot`，按提示创建 Bot，获得 `BOT_TOKEN`
2. 与 Bot 建立会话（向你的 Bot 发送任意消息），或通过 `getUpdates` 获取 `chat_id`
3. 在 `.env` 中配置：
   ```bash
   TELEGRAM_BOT_TOKEN=123456789:AAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   TELEGRAM_CHAT_ID=987654321
   ```
4. 验证：Bot 收到一条测试消息

#### 8.1.5 Slack（im_channels.slack_webhook）

1. 访问 Slack API 页面创建 Incoming Webhook（`https://api.slack.com/messaging/webhooks`）
2. 选择目标频道，获取 Webhook（格式 `https://hooks.slack.com/services/xxx/yyy/zzz`）
3. 在 `.env` 中配置：
   ```bash
   SLACK_WEBHOOK=https://hooks.slack.com/services/xxxx/yyyy/zzzz
   ```
4. 验证：指定频道收到测试消息

#### 8.1.6 邮件（email 段）

在 `.env` 中配置 SMTP：

```bash
SMTP_HOST=smtp.example.com
SMTP_PORT=465
SMTP_USER=alerts@example.com
SMTP_PASSWORD=xxxxxxxx
SMTP_FROM=alerts@example.com
ALERT_EMAIL=ops@example.com
```

配置后重启服务使配置生效（`sudo systemctl restart ongrid-ops`）。发送告警时，系统会自动选择合适的已配置渠道。

### 8.2 MCP Server 注册

MCP（Model Context Protocol）允许 Agent 通过标准 **Streamable HTTP** 协议调用外部工具服务器。配置位于 `config/mcp.yaml`，顶层键为 `mcp_servers`：

```yaml
mcp_servers:
  - name: "http-tools"
    url: "http://localhost:9001/mcp"
    headers:
      Authorization: "Bearer ${MCP_HTTP_TOKEN}"
    enabled: true
  - name: "monitor"
    url: "http://monitor-mcp:9002/mcp"
    headers: {}
    enabled: true
```

字段说明：

| 字段 | 必填 | 说明 |
|------|------|------|
| name | 是 | 唯一名称，展示在 Web「MCP 管理」页面 |
| url | 是 | MCP Server 的 Streamable HTTP 端点 |
| headers | 否 | 额外 HTTP 请求头，用于鉴权（如 `Authorization: Bearer ...`） |
| enabled | 否 | 是否启用，默认 `true` |

配置步骤：

1. 编辑 `config/mcp.yaml`，取消示例注释或新增条目（注意键名是 `mcp_servers`，不是 `servers`）
2. 将请求头中的密钥放入 `.env`：
   ```bash
   MCP_HTTP_TOKEN=xxxxxxxx
   ```
3. 保存后重启服务，或触发配置热重载

验证与排错：

- 在 Web「MCP 管理」页面确认新增 Server 出现在列表中，且工具列表已加载
- 调用测试：在 AI 对话中让 Agent 调用该 MCP 工具，观察返回
- 排错：
  - 工具不可用：检查 URL 是否可访问、服务是否启动
  - 认证失败：检查 `headers` 中 Token 是否正确、.env 是否已加载
  - 连接超时：确认网络连通性（容器内互访用服务名，跨主机用 IP）

MCP 工具注册后自动进入 ToolRegistry，供 Agent 在诊断/自愈流程中调用。

### 8.3 技能启用/停用

技能定义位于 `skills/<技能名>/SKILL.md`（frontmatter + 正文）。全局开关与禁用列表在 `config/skills.yaml`：

```yaml
skills:
  dir: "skills"
  enabled: true
  disabled: []          # 在此处添加需要停用的技能名
```

- `dir`：技能目录路径（相对项目根目录）
- `enabled`：技能系统总开关（`false` 时全部技能停用）
- `disabled`：需要单独停用的技能名列表

配置示例：

```yaml
skills:
  dir: "skills"
  enabled: true
  disabled:
    - "bash"              # 停用本地命令技能
    - "restart-service"   # 停用服务重启技能
```

停止技能后，该技能的工具将从 ToolRegistry 中移除，Agent 将无法调用。修改后重启服务生效。

> 注意：`disabled` 列表中配置的技能需要与 `skills/` 目录下的实际技能名保持一致。

## 九、安全加固

### 9.1 修改默认密码

首次登录后立即修改 admin 密码，在 Web 平台用户管理中操作。

### 9.2 密钥管理

- 所有密钥通过 `.env` 注入，不硬编码到配置文件
- `.env` 文件不入库（已在 `.gitignore` 中排除）
- 生产环境使用强随机密钥

### 9.3 网络安全

- 生产环境使用 HTTPS（通过 Nginx 或负载均衡）
- 限制 SSH 端口访问范围
- 数据库端口不对外暴露

### 9.4 命令安全

SSH 工具内置只读沙箱策略（denylist / 禁重定向 / 禁 shell 元字符 / stdout 上限 / 超时），详见操作手册第十二章。

## 十、升级与回滚

### 10.1 升级流程

```bash
cd /opt/ongrid-ops

# 1. 拉取最新代码
git pull origin main
git submodule update --init

# 2. 更新 Python 依赖
source venv/bin/activate
pip install -r requirements.txt --upgrade

# 3. 重新构建前端
cd web
npm install
npm run build
cd ..

# 4. 重启服务
sudo systemctl restart ongrid-ops

# 5. 确认服务正常
sudo systemctl status ongrid-ops
```

### 10.2 回滚

```bash
# 查看提交历史，回退到上一个稳定版本
git log --oneline -5
git checkout <stable-commit-hash>
git submodule update --init

# 重建前端并重启
cd web && npm run build && cd ..
sudo systemctl restart ongrid-ops
```

## 十一、监控与健康检查

### 11.1 健康检查端点

```
GET http://<服务器IP>:8000/healthz
```

返回 `{"status": "ok"}` 表示服务正常。

### 11.2 日志监控

```bash
# 实时查看后端日志
sudo journalctl -u ongrid-ops -f

# 查看 Agent 执行日志
sudo journalctl -u ongrid-ops | grep "master_agent"
```

### 11.3 Prometheus 指标

如部署了 Prometheus，可在 Grafana 中查看后端 HTTP 请求量、响应时间等指标。

## 十二、常见排障

| 问题 | 解决方案 |
|------|---------|
| 前端构建失败 | `cd web && npm install && npm run build` |
| 端口被占用 | 修改 `config.yaml` 中 `web.port` 或环境变量 |
| 数据库初始化失败 | 删除 `data/ops_agent_web.db` 后重启 |
| 配置热重载失败 | 检查 YAML 语法 |
| 国产数据库驱动缺失 | 按需安装 oracledb / dmPython / ksycopg2 |
| LLM 无响应 | 检查 `config.yaml` 中 llm 配置及环境变量 |
| SSH 连接失败 | 检查 servers.yaml 中 SSH 配置、网络/防火墙 |
| submodule 缺失 | 执行 `git submodule update --init` |
| Prometheus 查询失败 | 检查 `prometheus_url` 与网络连通性 |
| Loki 查询失败 | 检查 `loki_url` 与日志采集配置 |
| MCP 工具不可用 | 检查 `mcp.yaml` 中 Server 命令/URL 与日志 |
| 专家 Agent 未加载 | 检查 `agents/*.md` frontmatter 格式 |

## 十三、附录

### 13.1 部署检查清单

- [ ] Python >= 3.10 已安装
- [ ] Node.js >= 18 已安装
- [ ] 代码已克隆（含 submodule）
- [ ] Python 依赖已安装（`pip install -r requirements.txt`）
- [ ] 前端已构建（`web/dist/` 存在）
- [ ] `.env` 已配置（LLM / SSH / DB / IM 密钥）
- [ ] `config/config.yaml` 已配置
- [ ] `config/servers.yaml` 已配置目标服务器
- [ ] systemd 服务已注册并启动
- [ ] `/healthz` 返回正常
- [ ] Web 平台可访问且可登录
- [ ] 默认密码已修改

### 13.2 环境变量表

| 变量名 | 说明 | 必填 |
|--------|------|------|
| OPENAI_API_KEY | LLM API Key | 是 |
| OPENAI_BASE_URL | LLM API 地址 | 是 |
| OPS_AGENT_SECRET_KEY | Web 安全密钥 | 是 |
| SSH_PRIVATE_KEY_PATH | SSH 私钥路径 | 按需 |
| MYSQL_PASSWORD | MySQL 密码 | 按需 |
| WECOM_WEBHOOK | 企微 Webhook | 按需 |
| DINGTALK_WEBHOOK | 钉钉 Webhook | 按需 |
| FEISHU_WEBHOOK | 飞书 Webhook | 按需 |
| TELEGRAM_BOT_TOKEN | Telegram Bot Token | 按需 |
| TELEGRAM_CHAT_ID | Telegram Chat ID | 按需 |
| SLACK_WEBHOOK | Slack Webhook | 按需 |
| PROMETHEUS_URL | Prometheus 地址 | 按需 |
| LOKI_URL | Loki 地址 | 按需 |
| GRAFANA_URL | Grafana 地址 | 按需 |
| KUBECONFIG_PATH | Kubernetes 配置路径 | 按需 |

### 13.3 docker-compose 示例

```yaml
# deploy/docker-compose.yml
version: '3.8'
services:
  ongrid-ops:
    build: ..
    ports:
      - "8000:8000"
    env_file: ../.env
    volumes:
      - ../config:/app/config
      - ../knowledge:/app/knowledge
      - ../data:/app/data
    restart: always

  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml
    restart: always

  loki:
    image: grafana/loki:latest
    ports:
      - "3100:3100"
    restart: always

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    volumes:
      - ./grafana/provisioning:/etc/grafana/provisioning
      - ./grafana/dashboards:/var/lib/grafana/dashboards
    restart: always
```

### 13.4 systemd 服务示例

```ini
# /etc/systemd/system/ongrid-ops.service
[Unit]
Description=Ongrid-Ops Agent
After=network.target

[Service]
Type=simple
User=ops
WorkingDirectory=/opt/ongrid-ops
EnvironmentFile=/opt/ongrid-ops/.env
ExecStart=/opt/ongrid-ops/venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

> AI生成