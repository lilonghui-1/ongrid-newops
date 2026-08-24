---
AIGC:
  ContentProducer: '001191110102MAD55U9H0F10002'
  ContentPropagator: '001191110102MAD55U9H0F10002'
  Label: '1'
  ProduceID: '35353912-b603-42e7-8180-17ba825ed05c'
  PropagateID: '35353912-b603-42e7-8180-17ba825ed05c'
  ReservedCode1: 'ce723641-5cac-4278-bb3e-1ad69943e60b'
  ReservedCode2: 'ce723641-5cac-4278-bb3e-1ad69943e60b'
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
servers:
  - name: "kubernetes-mcp"
    command: "python"
    args: ["-m", "mcp_server_k8s"]
    env:
      KUBECONFIG: "${KUBECONFIG_PATH}"
    enabled: true
  - name: "cloud-mcp"
    url: "http://localhost:8080/mcp"
    transport: "streamable-http"
    enabled: true
```

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

### 7.1 Prometheus

```bash
# 使用 deploy/prometheus/prometheus.yml 配置
cd deploy
docker-compose up -d prometheus
```

访问 `http://localhost:9090`，在 Agent 配置中设置 `prometheus_url`。

### 7.2 Loki

```bash
cd deploy
docker-compose up -d loki
```

访问 `http://localhost:3100`，在 Agent 配置中设置 `loki_url`。

### 7.3 Grafana

```bash
cd deploy
docker-compose up -d grafana
```

访问 `http://localhost:3000`（默认 admin/admin）。Dashboard provisioning 已预配置在 `deploy/grafana/provisioning/`。

### 7.4 Docker Compose 全量部署

```bash
cd deploy
docker-compose up -d
```

包含：后端 + Prometheus + Loki + Grafana。

## 八、IM 通道与 MCP 注册

### 8.1 IM 渠道配置

在 `.env` 或 `config.yaml` 的 `im_channels` 段配置各渠道 Webhook/Token（详见 4.1）。

### 8.2 MCP Server 注册

编辑 `config/mcp.yaml`，添加外部 MCP Server（详见 4.4）。MCP 工具自动注册进 ToolRegistry，供 Agent 调用。

### 8.3 技能启用/停用

编辑 `config/skills.yaml`：

```yaml
skills:
  - name: "ssh-readonly"
    enabled: true
  - name: "restart-service"
    enabled: true
  - name: "bash"
    enabled: false   # 停用本地命令技能
```

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