# 应用部署及更新指南

## 环境要求

| 组件 | 版本要求 | 说明 |
|------|---------|------|
| Python | >= 3.10 | 后端运行环境 |
| Node.js | >= 18 | 前端构建环境 |
| npm | >= 9 | 前端包管理 |
| Git | - | 代码拉取和更新 |

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
# pip install oracledb>=2.0.0       # Oracle
# pip install dmPython>=2.4.0       # 达梦（需从官网下载 whl）
# pip install ksycopg2>=2.8.0       # 人大金仓
```

### 3. 配置环境变量

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

### 4. 构建前端

```bash
cd web
npm install
npm run build
cd ..
```

构建完成后，前端静态文件将输出到 `web/dist/` 目录，后端会自动挂载。

### 5. 启动服务

```bash
# 启动 Web 管理平台（默认监听 0.0.0.0:8000）
python main.py
# 或
uvicorn src.web.app:create_app --host 0.0.0.0 --port 8000 --factory
```

首次启动会自动创建 SQLite 数据库（`ops-agent/data/ops_agent_web.db`）和默认管理员账号（admin / admin123）。

### 6. 访问

打开浏览器访问 `http://<服务器IP>:8000`，使用默认管理员账号登录后请立即修改密码。

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