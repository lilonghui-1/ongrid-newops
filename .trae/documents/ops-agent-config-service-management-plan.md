# Ops Agent 配置管理与应用服务管理优化方案

## 一、当前状态分析

### 项目概述
- **项目名称**: Ops Agent（运维 Agent）
- **后端**: Python FastAPI + SQLAlchemy + SQLite
- **前端**: Vue 3 + TypeScript + Element Plus + Vue Router
- **配置**: YAML 文件（`config/config.yaml`, `config/servers.yaml`, `config/rules.yaml`）

### 问题 1：配置管理 - 新增配置文件时提示"请先选择服务器"

**根因**：前端 `ConfigEditView.vue` 在加载服务器列表时，API 请求路径为 `/servers/`（带尾斜杠），但后端 `servers.py` 中路由定义为 `@router.get("")`（空字符串，匹配 `/api/servers` 不带尾斜杠）。这导致 FastAPI 无法匹配路由，服务器列表返回空，因此下拉框无选项，新增配置时提示"请先选择服务器"。

**相关文件**：
- [ConfigEditView.vue](file:///workspace/web/src/views/ConfigEditView.vue#L134) - `loadServers()` 调用 `request.get('/servers/')` ⚠️ 带尾斜杠
- [servers.py](file:///workspace/src/web/api/servers.py#L205) - `@router.get("")` 路由定义 ⚠️ 无尾斜杠
- [ServiceListView.vue](file:///workspace/web/src/views/ServiceListView.vue#L46) - 对比：`/servers` 不带尾斜杠 ✅
- [ServerListView.vue](file:///workspace/web/src/views/ServerListView.vue#L43) - 对比：`/servers` 不带尾斜杠 ✅

### 问题 2：应用服务管理需要后端维护和可视化界面

**当前现状**：
- **后端** [services.py](file:///workspace/src/web/api/services.py) - 通过 SSH 动态执行 `systemctl list-units` 获取服务列表，使用 `ServiceInfo` schema（name, status, pid, cpu, memory）
- **前端** [ServiceListView.vue](file:///workspace/web/src/views/ServiceListView.vue) - 已有基础 UI：服务列表表格、启动/停止/重启/批量重启操作
- 服务数据完全动态获取，**没有数据库模型持久化存储服务定义**，无法在后台维护服务元数据（如服务分类、描述、所属应用等）

**需要改进的方向**：
- 后端新增服务管理的数据模型和 CRUD API，支持服务定义的后台维护
- 前端增强可视化界面，支持服务的增删改查管理

---

## 二、修改方案

### 方案 1：修复配置管理服务器列表加载问题

**修改文件**：[ConfigEditView.vue](file:///workspace/web/src/views/ConfigEditView.vue#L134)

**修改内容**：将 API 请求路径从 `/servers/` 改为 `/servers`（去掉尾斜杠）

```diff
- const res = await request.get<...>('/servers/')
+ const res = await request.get<...>('/servers')
```

### 方案 2：增强应用服务管理 - 后端 DB 模型 + API + 前端可视化

#### 2.1 新增数据库模型 `AppService`

**新增文件**：[service.py](file:///workspace/src/web/models/service.py)

定义 `AppService` ORM 模型，用于存储服务定义：

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int (PK) | 主键 |
| server_host | str | 所属服务器地址 |
| name | str | 服务名称 |
| display_name | str | 服务显示名称 |
| description | str | 服务描述 |
| category | str | 服务分类（如 web/middleware/database/custom） |
| port | int | 服务端口（可选） |
| enabled | bool | 是否启用监控 |
| created_by | str | 创建人 |
| created_at | datetime | 创建时间 |
| updated_at | datetime | 更新时间 |

**修改文件**：[__init__.py](file:///workspace/src/web/models/__init__.py)

导入并导出 `AppService` 模型。

**修改文件**：[database.py](file:///workspace/src/web/database.py)

在 `init_database()` 中导入 `AppService` 模型，确保表自动创建。

#### 2.2 新增服务定义 Schema

**新增文件**：[service.py](file:///workspace/src/web/schemas/service.py)（追加内容）

新增 `AppServiceCreate`、`AppServiceUpdate`、`AppServiceResponse` Pydantic 模型。

#### 2.3 新增服务管理 API

**修改文件**：[services.py](file:///workspace/src/web/api/services.py)

新增 CRUD 端点（前缀 `/api/services/manage`）：

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `/manage` | 获取所有服务定义列表 | 登录用户 |
| GET | `/manage/{service_id}` | 获取单个服务定义详情 | 登录用户 |
| POST | `/manage` | 新增服务定义 | operator |
| PUT | `/manage/{service_id}` | 更新服务定义 | operator |
| DELETE | `/manage/{service_id}` | 删除服务定义 | admin |
| GET | `/manage/by-server/{host}` | 获取指定服务器的服务定义列表 | 登录用户 |

**修改文件**：[app.py](file:///workspace/src/web/app.py)

无需修改（已在 `services_router` 中注册）。

#### 2.4 前端服务管理可视化界面

**修改文件**：[ServiceListView.vue](file:///workspace/web/src/views/ServiceListView.vue)

增强功能：
1. **服务列表表格** - 增加"服务分类"、"端口"、"描述"等列，显示信息和状态
2. **新增服务定义对话框** - 表单包含：服务名称、显示名称、描述、分类、端口、所属服务器
3. **编辑服务定义对话框** - 支持修改已有服务定义
4. **删除服务定义** - 确认弹窗后删除
5. **搜索/过滤** - 按服务名称、分类、服务器搜索
6. 原有的启动/停止/重启操作保留

---

## 三、关键决策与假设

- 服务定义与动态服务列表是**互补关系**：动态列表展示实时运行状态，服务定义管理用于持久化存储服务元数据
- 服务定义不依赖 SSH 连接，可在后台独立维护
- 沿用现有技术栈（Vue 3 + Element Plus + FastAPI + SQLAlchemy + SQLite）
- 无需新增 npm 依赖

## 四、验证步骤

1. **修复验证**：打开配置管理页面，确认服务器下拉框能正常加载服务器列表
2. **服务定义 CRUD 验证**：
   - 新增服务定义 → 确认数据库中存储成功
   - 编辑服务定义 → 确认字段更新
   - 删除服务定义 → 确认记录删除
3. **前端可视化验证**：
   - 服务列表页显示所有已定义的服务
   - 按服务器筛选正确
   - 启动/停止/重启操作正常