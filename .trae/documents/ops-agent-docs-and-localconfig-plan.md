# Ops Agent 文档更新 + 本地配置管理界面优化计划

## 一、概述

本计划包含三项任务：
1. **更新部署手册**（`docs/deployment.md`）
2. **新增/更新操作手册**（`docs/operation.md`，覆盖 Web 平台 + 系统配置）
3. **优化本地配置管理界面**（`web/src/views/LocalConfigView.vue`，采用「配置分组 + 标签页」交互）

交付形式：文档为 **Markdown**；前端改造沿用现有 Element Plus + CodeMirror 技术栈。

---

## 二、现状分析

### 2.1 文档现状
- [docs/deployment.md](file:///workspace/docs/deployment.md)：
  - 已包含环境要求、首次部署、更新、systemd、常见问题
  - 内容偏基础，未反映 Web 管理平台新增功能（本地配置热重载、参数管理、Web 配置管理、多数据库支持等）
- 操作手册缺失：项目内仅有 [测试说明手册](file:///workspace/docs/test-manual/dist/html-report/index.html)，无面向 Web 平台用户的操作手册

### 2.2 本地配置管理现状
- [LocalConfigView.vue](file:///workspace/web/src/views/LocalConfigView.vue)：当前为「左侧 `el-menu` 文件列表 + 右侧 CodeMirror 编辑器」左右布局
  - 左侧卡片列出 3 个配置文件（主配置 `config.yaml` / 服务器配置 `servers.yaml` / 自愈规则 `rules.yaml`）
  - 右侧为 YAML 编辑器 + 顶部工具栏（保存/刷新/重载）
- 后端 [local_configs.py](file:///workspace/src/web/api/local_configs.py) 提供的端点：
  - `GET /local-configs/files`：返回文件列表（含 `name`/`label`/`description`/`exists`/`size`/`modified_at`）
  - `GET /local-configs/files/{name}`：读取内容
  - `PUT /local-configs/files/{name}`：保存（自动备份）
  - `POST /local-configs/reload`：触发热重载
- 前端数据结构 `LocalConfigFile`：`name`、`path`、`label`、`description`、`format`、`exists`、`size`、`modified_at`

### 2.3 相关路由/菜单
- 路由 [router/index.ts](file:///workspace/web/src/router/index.ts#L73-L77)：`/local-configs` → `LocalConfigView`，标题「本地配置管理」
- 侧边栏 [LayoutView.vue](file:///workspace/web/src/views/LayoutView.vue#L24)：菜单项「本地配置管理」

---

## 三、变更方案

### 3.1 更新部署手册 `docs/deployment.md`

定位：作为系统级部署与运维指导，补充 Web 管理平台能力。

**具体修改（在现有结构上增强）：**
1. **环境要求**：补充可选国产数据库驱动（Oracle/达梦/人大金仓，从现有代码 `db_tools.py` 驱动映射确认 `oracledb`/`dmPython`/`ksycopg2`）及访问 LLM API 的网络要求
2. **后端部署**：细化配置文件准备（`config.yaml` / `servers.yaml` / `rules.yaml` 三文件职责）
3. **顶部新增「功能与模块」小节**：简述 Agent（巡检/诊断/日志/自愈）与 Web 管理平台各功能页
4. **Web 平台说明**：默认端口 `8000`、默认账号 `admin / admin123`（登录后需改密）、本地配置热重载功能说明
5. **更新流程**：补充「数据库未见效需重装驱动」「前端构建 vue-tsc 报错」等新增关联提醒
6. **常见问题**：补充配置热重载失败、数据库驱动缺失、端口占用、数据库重置（`data/ops_agent_web.db`）等

> 仅更新内容，不改变文档骨架与风格。

### 3.2 新增操作手册 `docs/operation.md`

定位：面向 Web 管理平台使用者的操作指南，覆盖 **Web 平台功能** + **系统配置**。

**文档结构：**
1. 概述（产品定位、适用对象）
2. 快速入门（登录、默认账号、修改密码）
3. Web 平台功能使用说明：
   - 总览仪表盘
   - 服务器监控 / 服务器详情
   - 日志查询
   - 应用服务（动态服务 / 服务定义）
   - 配置管理（远程服务器配置）
   - **本地配置管理**（本次优化后的标签页交互）
   - 参数管理
   - 告警管理
   - 知识库管理
   - 自愈规则管理
   - AI 运维对话
   - 审计日志
4. 系统配置详解：
   - `config.yaml`（LLM / 通知 / 调度 / Web / 日志平台）
   - `servers.yaml`（服务器 / SSH / 数据库连接）
   - `rules.yaml`（自愈规则）
5. 常见运维操作（热重载、重启、日志查看）

> 各功能页描述基于 [router/index.ts](file:///workspace/web/src/router/index.ts) 中已注册视图与其功能代码。

### 3.3 优化本地配置管理界面 `web/src/views/LocalConfigView.vue`

**目标交互：** 「配置分组 + 标签页」——用顶部标签页取代左侧 `el-menu` 文件列表，按配置文件分组。

**具体改动：**
1. **移除左侧 `el-col`/`el-menu` 侧栏**，改为单卡片全宽布局
2. **新增顶部工具栏**（保留现有动作）：
   - 当前配置文件名/标签 + 元信息标签（`size`、`modified_at`）
   - 「保存」「刷新」「重载配置」按钮（复用现有逻辑）
   - 「未保存」警示标签
3. **新增 `el-tabs` 作为配置切换器**：
   - 每个 tab 对应一个配置文件，`label` 取自 `LocalConfigFile.label`（主配置 / 服务器配置 / 自愈规则）
   - `el-tab-pane` 内展示 CodeMirror 编辑器（YAML 高亮）
   - 监听 tab 切换 → 调用 `selectFile(name)`（沿用未保存变更的确认逻辑）
   - 仅对 `exists === true` 的文件显示 tab；若全部不存在则显示空态
4. **保持逻辑层不变**：`loadConfigList` / `selectFile` / `confirmSave` / `refreshFile` / `triggerReload` 等函数复用
5. **样式调整**：`scoped` SCSS 中删除侧栏相关样式，新增标签页/工具栏布局；编辑器高度改为整卡占满

**类型注意：** 复用现有 `LocalConfigFile` / `ConfigContent` 接口；`el-tabs` 的 `v-model` 绑定的文件名类型为 `string`。

---

## 四、假设与决策

1. 采用用户选择的方向：**配置分组 + 标签页**（废弃左菜单方案）
2. 两份手册均输出 **Markdown**（不生成 HTML/Word）
3. 操作手册**覆盖 Web 平台 + 系统配置**
4. 本地配置仅有 3 个文件且语义明确（主配置/服务器/规则），`el-tabs` 按文件标签分页即为「分组」；若后续文件增多可扩展为嵌套分组（本次不做）
5. 不改动后端 `local_configs.py` 接口与 `LayoutView.vue` / `router`（菜单入口保持不变）

---

## 五、验证步骤

1. **前端构建**：`cd /workspace/web && npm run build`，确认 `vue-tsc` 无类型错误
2. **交互验证**（如环境允许启动）：
   - 登录后进入「本地配置管理」，确认顶部标签页可切换三个配置文件
   - 修改内容后无保存切换，提示确认；保存后自动触发重载
   - 元信息标签（大小/修改时间）正确显示
3. **文档核对**：通读 `docs/deployment.md` 与 `docs/operation.md`，确认功能页描述与代码一致、无占位缺漏

---

## 六、涉及文件清单

| 操作 | 文件 | 说明 |
|------|------|------|
| 修改 | `docs/deployment.md` | 补充 Web 管理平台、数据库驱动、热重载等部署内容 |
| 新增 | `docs/operation.md` | 全新操作手册（Web 平台 + 系统配置） |
| 修改 | `web/src/views/LocalConfigView.vue` | 由左右布局改造为标签页 + 工具栏布局 |