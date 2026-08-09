# Ops Agent 后端配置文件前端管理 + 邮件告警方案

## 一、当前状态分析

### 项目架构
- **后端**: Python FastAPI + SQLAlchemy + SQLite + LangGraph
- **前端**: Vue 3 + TypeScript + Element Plus + CodeMirror
- **配置目录**: `/workspace/config/` 包含三个 YAML 文件

### 配置文件清单

| 文件 | 内容 | 目前管理方式 |
|------|------|-------------|
| [config.yaml](file:///workspace/config/config.yaml) | LLM、通知、调度、Web、阈值 | 本地文件编辑，启动时加载 |
| [servers.yaml](file:///workspace/config/servers.yaml) | 服务器列表、数据库连接信息 | 本地文件编辑，启动时加载 |
| [rules.yaml](file:///workspace/config/rules.yaml) | 自愈规则（条件+操作） | 本地文件编辑，启动时加载 |

### 配置加载机制
- [ConfigLoader](file:///workspace/src/utils/config_loader.py) - 单例模式，`load()` 方法读取三个 YAML 文件合并为 `AppConfig` Pydantic 模型
- `reset()` 方法可重置单例，但**无热重载机制** - 修改后需重启应用
- [HealAgent](file:///workspace/src/agent/heal_agent.py) - 在 `__init__` 中加载规则，运行时无法刷新

### 当前 Web 配置管理
- [configs.py](file:///workspace/src/web/api/configs.py) - 仅管理**远程服务器上的配置文件**（如 nginx.conf），通过 SSH 读写
- **不管理本地后端配置**（config.yaml, servers.yaml, rules.yaml）

### 通知系统
- [notify_tools.py](file:///workspace/src/tools/notify_tools.py) - 仅支持企业微信/钉钉 Webhook，**无邮件通知**

### 服务管理
- [ServiceListView.vue](file:///workspace/web/src/views/ServiceListView.vue) - 已有"动态服务"和"服务定义"两个标签页
- 动态服务通过 SSH 执行 `systemctl list-units` 获取

---

## 二、修改方案

### 方案 1：后端配置文件前端管理（新增 API + 前端页面）

#### 1.1 后端 API - 本地配置管理路由

**新增文件**：[local_configs.py](file:///workspace/src/web/api/local_configs.py)

新增路由前缀 `/api/local-configs`，提供以下端点：

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `/files` | 获取所有本地配置文件列表（config.yaml, servers.yaml, rules.yaml） | 登录用户 |
| GET | `/files/{name}` | 读取指定配置文件内容 | 登录用户 |
| PUT | `/files/{name}` | 保存配置文件内容（写入本地 YAML 文件） | admin |
| POST | `/reload` | 触发配置热重载（重新加载所有 YAML 文件 + 刷新相关组件） | admin |

**热重载机制**：
- 调用 `ConfigLoader.reset()` 和 `ConfigLoader.get_instance().load(config_dir)` 重新加载配置
- 重新初始化 `HealAgent` 加载新规则
- 重新注册工具（如果服务器列表变化）
- 重启调度器（如果调度配置变化）

#### 1.2 新增 Schema

**修改文件**：[local_config.py](file:///workspace/src/web/schemas/local_config.py)（新增）

```python
class LocalConfigFileInfo(BaseModel):
    name: str          # 文件名
    path: str          # 完整路径
    label: str         # 显示名称
    description: str   # 描述
    format: str        # yaml

class LocalConfigContent(BaseModel):
    name: str
    content: str
    format: str

class LocalConfigSaveRequest(BaseModel):
    content: str
```

#### 1.3 在 app.py 注册新路由

**修改文件**：[app.py](file:///workspace/src/web/app.py)

增加 `from .api.local_configs import router as local_configs_router` 和 `app.include_router(local_configs_router, prefix="/api/local-configs", ...)`

#### 1.4 前端 - 本地配置管理页面

**新增文件**：[LocalConfigView.vue](file:///workspace/web/src/views/LocalConfigView.vue)

功能设计：
- 左侧：三个配置文件列表（config.yaml / servers.yaml / rules.yaml），每个带图标和描述
- 右侧：CodeMirror 编辑器（YAML 语法高亮）
- 顶部工具栏：保存按钮（带确认弹窗）、刷新按钮、重载配置按钮
- 保存后自动触发重载配置，并在前端提示"配置已更新，系统已自动重载"

**修改文件**：[router/index.ts](file:///workspace/web/src/router/index.ts)

新增路由 `/local-configs` → `LocalConfigView`，标题"本地配置管理"

**修改文件**：LayoutView.vue（侧边栏菜单）

新增"本地配置管理"菜单项

### 方案 2：配置修改后立即生效

#### 2.1 后端热重载机制

**修改文件**：[local_configs.py](file:///workspace/src/web/api/local_configs.py)

`POST /reload` 端点实现：
1. `ConfigLoader.reset()` + `ConfigLoader.get_instance().load(config_dir)` 重新加载配置
2. 重新注册所有工具（`register_all_tools(new_config)`）
3. 重新初始化 MasterAgent 和 HealAgent
4. 重启调度器

**新增文件**：[config_manager.py](file:///workspace/src/web/core/config_manager.py)

应用级配置管理器，持有全局 `OpsAgentApp` 实例引用，提供 `reload_config()` 方法：
- 重新加载配置
- 重新注册工具
- 重新创建 Agent
- 重启调度器

#### 2.2 前端保存后自动重载

在 `LocalConfigView.vue` 的保存逻辑中，保存成功后自动调用 `POST /api/local-configs/reload` 触发重载。

### 方案 3：邮件通知系统

#### 3.1 新增邮件配置

**修改文件**：[config.yaml](file:///workspace/config/config.yaml)

新增 `email` 配置段：
```yaml
email:
  smtp_host: "${SMTP_HOST}"
  smtp_port: 465
  smtp_user: "${SMTP_USER}"
  smtp_password: "${SMTP_PASSWORD}"
  from_addr: "${SMTP_FROM}"
  to_addrs: ["${ALERT_EMAIL}"]
  use_ssl: true
```

#### 3.2 新增邮件发送工具

**新增文件**：[email_tool.py](file:///workspace/src/tools/email_tool.py)

`EmailTool` 继承 `BaseTool`：
- 支持 SMTP SSL/TLS 发送
- 支持 HTML 格式邮件（含日志内容）
- 支持多收件人
- 支持附件（日志文件）
- 重试机制（tenacity）

#### 3.3 新增邮件通知模型

**新增文件**：[email_notify.py](file:///workspace/src/web/models/email_notify.py)

`EmailLog` 表用于存储邮件发送记录：
| 字段 | 说明 |
|------|------|
| id | 主键 |
| subject | 邮件主题 |
| body | 邮件内容（HTML） |
| to_addrs | 收件人列表 |
| attachment | 附件路径 |
| status | 发送状态（success/failed） |
| error_msg | 错误信息 |
| created_at | 发送时间 |

#### 3.4 新增邮件告警 API

**修改文件**：[services.py](file:///workspace/src/web/api/services.py) 或新增 `alert.py`

新增端点：
- `POST /api/alert/send-email` - 手动发送告警邮件
- `GET /api/alert/email-logs` - 查询邮件发送历史
- 自动检测：在巡检/诊断/自愈流程中，发现异常服务时自动触发邮件发送

#### 3.5 前端邮件告警页面

**新增文件**：[AlertView.vue](file:///workspace/web/src/views/AlertView.vue)

功能：
- 邮件发送历史列表
- 手动发送告警邮件表单
- 查看发送详情

### 方案 4：前端运维操作增强

#### 4.1 后端配置修改后的自动运维

在 `LocalConfigView.vue` 中，提供"保存并应用"功能：
- 保存配置 → 重载配置 → 根据配置变化自动触发相应操作
- 例如：新增服务器后自动尝试 SSH 连接验证

#### 4.2 异常服务邮件告警联动

**修改文件**：[scheduler.py](file:///workspace/src/scheduler.py)

在巡检和日志分析任务中，检测到异常时：
1. 收集异常服务的日志摘要
2. 通过 EmailTool 发送告警邮件
3. 记录到 EmailLog 表

---

## 三、关键决策与假设

1. 本地配置文件以 YAML 格式在前端编辑，使用 CodeMirror 编辑器（复用现有组件）
2. 保存配置后立即触发热重载，无需重启应用
3. 邮件通知作为企业微信/钉钉之外的补充渠道
4. 敏感信息（密码、密钥）仍通过环境变量 `${VAR}` 形式管理，不直接暴露在前端
5. 权限控制：普通用户可查看配置，仅 admin 可修改
6. 配置修改支持备份（保存前自动备份原文件）

## 四、实施步骤

1. 新增后端 API：`local_configs.py` + Schema `local_config.py`
2. 实现热重载机制：`config_manager.py` + `POST /reload` 端点
3. 新增前端页面：`LocalConfigView.vue`
4. 注册路由和菜单
5. 新增邮件配置和 `EmailTool`
6. 新增邮件告警 API + 前端页面
7. 联动调度器：异常时自动发送邮件
8. 注册通知工具到 ToolRegistry

## 五、文件变更清单

| 操作 | 文件 | 说明 |
|------|------|------|
| 新增 | `src/web/api/local_configs.py` | 本地配置 CRUD + 重载 API |
| 新增 | `src/web/schemas/local_config.py` | 本地配置 Schema |
| 新增 | `src/web/core/config_manager.py` | 应用级配置管理器 |
| 新增 | `src/tools/email_tool.py` | 邮件发送工具 |
| 新增 | `src/web/models/email_notify.py` | 邮件发送记录模型 |
| 新增 | `web/src/views/LocalConfigView.vue` | 本地配置管理前端页面 |
| 新增 | `web/src/views/AlertView.vue` | 告警管理前端页面 |
| 修改 | `src/web/app.py` | 注册新路由 |
| 修改 | `web/src/router/index.ts` | 新增路由 |
| 修改 | `config/config.yaml` | 新增 email 配置段 |
| 修改 | `src/scheduler.py` | 异常邮件告警联动 |
| 修改 | `src/tools/__init__.py` | 注册 EmailTool |