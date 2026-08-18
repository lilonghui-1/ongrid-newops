# 应用部署及更新指南

## 环境要求

| 组件 | 版本要求 | 说明 |
|------|---------|------|
| Python | >= 3.10 | 后端运行环境 |
| Node.js | >= 18 | 前端构建环境 |
| npm | >= 9 | 前端包管理 |
| Git | - | 代码拉取和更新 |
| 网络 | 可访问目标服务器 SSH 端口 | 远程巡检/运维必需 |
| 网络 | 可访问 LLM API | Agent 与 AI 对话功能必需 |

> 如需连接国产数据库，还需按对应数据库安装驱动（见下方「后端部署」）。

## 功能与模块

本项目包含两大运行部分：

1. **智能运维 Agent**（核心能力）：
   - 服务器巡检（CPU / 内存 / 磁盘 / 网络）
   - 数据库巡检（MySQL / PostgreSQL / Oracle / 达梦 / 人大金仓 / Redis）
   - 故障诊断（LLM 多维关联分析：指标 + 日志 + 知识库）
   - 日志分析（远程日志、ES / Loki 日志平台查询）
   - 自愈处理（预定义规则驱动的安全自愈）
   - 定时调度（cron 巡检与日志分析）、告警通知（企微 / 钉钉 / 邮件）

2. **Web 管理平台**（配套图形界面，监听 `0.0.0.0:8000`）：
   - 总览仪表盘、服务器监控 / 详情、日志查询、应用服务
   - 配置管理（远程服务器配置文件）、本地配置管理（支持热重载）、参数管理
   - 告警管理、知识库管理、自愈规则管理、AI 运维对话、审计日志

## 一、首次部署

### 1. 克隆代码

```bash
# 从 Git 仓库拉取代码
git clone <仓库地址> ops-agent
cd ops-agent
```

### 2. 后端部署

```bash
# （推荐）创建 Python 虚拟环境
python3 -m venv venv
source venv/bin/activate    # Linux/Mac
# 或 venv\Scripts\activate   # Windows

# 安装 Python 依赖
pip install -r requirements.txt

# 如需连接国产数据库，按需安装对应驱动：
# pip install oracledb>=2.0.0       # Oracle（纯 Python，无需客户端）
# pip install dmPython>=2.4.0       # 达梦（需从官网下载 whl，并设置 DM_HOME）
# pip install ksycopg2>=2.8.0       # 人大金仓（纯 Python）
```

### 3. 配置文件准备

系统使用以下三个 YAML 配置文件（位于 `config/` 目录）：

| 文件 | 职责 |
|------|------|
| `config.yaml` | LLM、通知渠道、调度任务、日志平台、Web 平台、邮件、告警阈值 |
| `servers.yaml` | 服务器列表、SSH 连接信息、数据库连接配置 |
| `rules.yaml` | 自愈规则（触发条件 + 执行操作 + 确认级别） |

> 也可在 Web 管理平台的「本地配置管理」页面在线编辑并在保存后自动触发热重载，无需手动编辑文件。

### 4. 配置环境变量

```bash
# 复制配置模板（如有）或直接编辑 config/config.yaml
# 设置必要的环境变量，例如：
export OPENAI_API_KEY="sk-xxxxxx"
export OPENAI_BASE_URL="https://api.openai.com/v1"
export OPS_AGENT_SECRET_KEY="your-secret-key-here"
```

或创建 `.env` 文件：

```bash
# .env
OPENAI_API_KEY=sk-xxxxxx
OPENAI_BASE_URL=https://api.openai.com/v1
OPS_AGENT_SECRET_KEY=your-secret-key-here
```

### 5. 构建前端

```bash
cd web
npm install
npm run build
cd ..
```

构建完成后，前端静态文件将输出到 `web/dist/` 目录，后端会自动挂载。

### 6. 启动服务

```bash
# 启动 Web 管理平台（默认监听 0.0.0.0:8000）
python main.py
# 或
uvicorn src.web.app:create_app --host 0.0.0.0 --port 8000 --factory
```

首次启动会自动创建 SQLite 数据库（`ops-agent/data/ops_agent_web.db`）和默认管理员账号（admin / admin123）。

### 7. 访问

打开浏览器访问 `http://<服务器IP>:8000`，使用默认管理员账号登录后请立即修改密码。

> 详细的使用说明请参见《操作手册》（`docs/operation.md`）。

## 二、更新应用

### 1. 拉取最新代码

```bash
cd ops-agent

# 查看当前分支
git branch

# 拉取最新代码
git pull origin main

# 如果是在其他分支上开发，合并到主分支
# git checkout main
# git pull origin main
```

### 2. 更新后端依赖

```bash
source venv/bin/activate
pip install -r requirements.txt --upgrade
```

### 3. 重新构建前端

```bash
cd web
npm install        # 如有新增依赖
npm run build
cd ..
```

### 4. 重启服务

```bash
# 找到正在运行的进程并重启
# 如果使用 systemd 管理：
sudo systemctl restart ops-agent

# 如果直接运行：
# 按 Ctrl+C 停止，然后重新启动
python main.py
```

## 三、使用 systemd 管理服务（推荐生产环境）

### 创建 systemd 服务

```bash
sudo tee /etc/systemd/system/ops-agent.service << 'EOF'
[Unit]
Description=Ops Agent Web Management Platform
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/path/to/ops-agent
EnvironmentFile=/path/to/ops-agent/.env
ExecStart=/path/to/ops-agent/venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable ops-agent
sudo systemctl start ops-agent
```

### 常用管理命令

```bash
# 查看状态
sudo systemctl status ops-agent

# 查看日志
sudo journalctl -u ops-agent -f

# 重启
sudo systemctl restart ops-agent

# 停止
sudo systemctl stop ops-agent
```

## 四、Git 更新示例

```bash
# 标准更新流程
cd /opt/ops-agent

# 1. 拉取代码
git pull origin main

# 2. 更新 Python 依赖
source venv/bin/activate
pip install -r requirements.txt --upgrade

# 3. 重新构建前端
cd web
npm install
npm run build
cd ..

# 4. 重启服务
sudo systemctl restart ops-agent

# 5. 确认服务正常运行
sudo systemctl status ops-agent
```

## 五、常见问题

### 构建失败 - vue-tsc 报错

```bash
cd web
npm install   # 确保依赖安装完整
npm run build
```

### 端口被占用

修改 `config/config.yaml` 中的 `web.port` 配置项，或使用环境变量覆盖。

### 数据库问题

数据库文件位于 `ops-agent/data/ops_agent_web.db`。如需重置，删除该文件后重启服务即可自动重建。

### 配置热重载失败

在 Web 管理平台的「本地配置管理」保存配置后会自动触发重载。若重载失败，请检查被改动的配置文件是否有 YAML 语法错误，或重启服务使配置生效。

### 数据库连接报驱动缺失

若连接 Oracle / 达梦 / 人大金仓时提示缺少驱动，请确认已按「后端部署」小节安装对应驱动：
- Oracle：`pip install oracledb>=2.0.0`
- 达梦：`pip install dmPython>=2.4.0`（需从官网下载 whl，并设置 `DM_HOME` 环境变量）
- 人大金仓：`pip install ksycopg2>=2.8.0`

更新代码后若数据库连接失效，请重新执行一次驱动安装命令。

### LLM 对话 / Agent 无响应

检查 `config/config.yaml` 中的 `llm` 配置及环境变量 `OPENAI_API_KEY` / `OPENAI_BASE_URL` 是否正确，并确认网络可访问 LLM API。