# Ops Agent Bug 修复与功能增强计划

## 概述

修复 5 个问题：本地配置热重载 NoneType 崩溃、邮件配置无法管理、:8000 管理平台无法登录、服务器缺少 Linux/麒麟系统示例、参数化配置缺少管理界面。

---

## 当前状态分析

### 问题 1：本地配置管理 - NoneType 崩溃
- **根因**：`AppConfigManager.init_app()` 从未被调用，`_app_ref` 恒为 `None`
- **崩溃点**：`config_manager.py` 第 71 行 `self._app_ref.config = new_config` → `None.config = ...`
- **影响**：配置文件保存成功但热重载崩溃，新配置未生效
- **文件**：`/workspace/src/main.py`（web 模式未注入 OpsAgentApp）、`/workspace/src/web/core/config_manager.py`、`/workspace/src/web/app.py`

### 问题 2：邮件配置无法管理
- **现状**：`config.yaml` 已有 `email:` 段，但值通过 `${SMTP_HOST}` 等环境变量注入
- **问题**：环境变量未设置时占位符原样保留，`EmailTool.is_configured` 误判为已配置（因为 `"${SMTP_HOST}"` 非空）
- **缺失**：前端无法直接管理邮件参数（环境变量）

### 问题 3：:8000 管理平台无法登录（{"detail":"Not Found"}）
- **根因**：`app.py` 的 `create_app()` 没有挂载前端静态资源（`StaticFiles`）
- **详情**：后端只有 `/api/...` 和 `/ws/...` 路由，直接访问 `:8000/` 或 `:8000/login` 返回 404
- **修复**：在所有路由注册后挂载 `StaticFiles(directory="web/dist", html=True)`，并处理 SPA 路由回退

### 问题 4：服务器缺少 Linux/麒麟系统示例
- **现状**：`servers.yaml` 有 7 个示例，但无 Kylin/麒麟/统信/openEuler 专门示例
- **自愈规则**：Linux 规则用 `apt-get`（Debian/Ubuntu），缺少 `yum/dnf`（Kylin/RHEL 系）
- **ServerConfig**：`os_type` 只有 `"linux"` / `"windows"` 两个值

### 问题 5：参数化配置缺少管理界面
- **现状**：所有 `${VAR}` 占位符依赖操作系统环境变量，无 Web 端管理
- **缺失**：无参数管理模型、API 端点、前端页面
- **需求**：通过前端管理环境变量参数（如 SSH_PASSWORD、MYSQL_PASSWORD、SMTP_HOST 等）

---

## 实施方案

### 1. 修复本地配置热重载 NoneType 崩溃

**文件**：`/workspace/src/main.py`、`/workspace/src/web/app.py`、`/workspace/src/web/core/config_manager.py`

**改动**：

#### 1.1 `main.py` - 注入 OpsAgentApp 引用
在 web 模式启动分支中，调用 `AppConfigManager.init_app(self)` 并将 `self`（OpsAgentApp 实例）传递给 `create_app`：

```python
elif mode == "web":
    from .web.app import create_app
    from .web.core.config_manager import AppConfigManager
    import uvicorn
    AppConfigManager.init_app(self)
    app = create_app(self)
    uvicorn.run(app, host=self.config.web.host, port=self.config.web.port)
```

#### 1.2 `app.py` - 修改 `create_app` 签名
将 `create_app(config)` 改为 `create_app(app_instance)`，从 `app_instance.config` 获取配置：

```python
def create_app(app_instance) -> FastAPI:
    config = app_instance.config
    # ... 其余不变
```

#### 1.3 `config_manager.py` - 增加健壮性
- `reload_config()` 中增加 `_app_ref` 为 None 的检查
- 修复 ConfigLoader.reset() 先执行导致的状态不一致问题（调整为先加载新配置成功后再重置）

#### 1.4 `local_configs.py` - 修复硬编码路径
将 `CONFIG_DIR = Path("/workspace/config")` 改为从 `ConfigLoader` 单例动态获取：

```python
from ...utils.config_loader import ConfigLoader
CONFIG_DIR = Path(ConfigLoader.get_instance().config_dir)
```

---

### 2. 修复邮件配置管理

**文件**：`/workspace/src/tools/email_tool.py`

**改动**：

#### 2.1 修复 `is_configured` 判断逻辑
检测未解析的占位符字符串：

```python
@property
def is_configured(self) -> bool:
    values = [self._smtp_host, self._smtp_user, self._smtp_password, self._from_addr]
    if not all(values):
        return False
    # 检测未解析的 ${...} 占位符
    for v in values:
        if v and v.startswith("${") and v.endswith("}"):
            return False
    if not self._to_addrs:
        return False
    return True
```

---

### 3. 修复 :8000 管理平台无法登录

**文件**：`/workspace/src/web/app.py`

**改动**：

#### 3.1 挂载前端静态资源
在 `return app` 之前，所有 `include_router` 之后添加：

```python
from fastapi.staticfiles import StaticFiles
from pathlib import Path

dist = Path(__file__).resolve().parents[2] / "web" / "dist"
if dist.exists():
    app.mount("/", StaticFiles(directory=str(dist), html=True), name="frontend")
```

#### 3.2 SPA 路由回退处理
由于 `html=True` 会自动回退到 `index.html`，前端 Vue Router 的 history 模式路由将正常工作。

---

### 4. 增加 Linux/麒麟系统服务器示例

**文件**：`/workspace/config/servers.yaml`、`/workspace/config/rules.yaml`、`/workspace/src/utils/config_loader.py`

**改动**：

#### 4.1 `servers.yaml` - 新增麒麟系统示例
在现有示例后添加：

```yaml
  # 示例：麒麟操作系统服务器（Kylin）
  - name: "kylin-server-01"
    host: "192.168.1.40"
    port: 22
    username: "ops"
    password: "${KYLIN_SSH_PASSWORD}"
    os_type: "linux"
    tags: ["kylin", "production", "domestic"]
    databases:
      - type: "dm"
        host: "127.0.0.1"
        port: 5236
        username: "SYSDBA"
        password: "${DM_PASSWORD}"
        name: "DAMENG"

  # 示例：统信 UOS 服务器
  - name: "uos-server-01"
    host: "192.168.1.41"
    port: 22
    username: "ops"
    password: "${UOS_SSH_PASSWORD}"
    os_type: "linux"
    tags: ["uos", "production", "domestic"]
    databases:
      - type: "kingbase"
        host: "127.0.0.1"
        port: 54321
        username: "system"
        password: "${KINGBASE_PASSWORD}"
        name: "test"

  # 示例：openEuler 服务器
  - name: "openeuler-server-01"
    host: "192.168.1.42"
    port: 22
    username: "ops"
    private_key_path: "${SSH_PRIVATE_KEY_PATH}"
    os_type: "linux"
    tags: ["openeuler", "production", "domestic"]
    databases:
      - type: "postgresql"
        host: "127.0.0.1"
        port: 5432
        username: "monitor"
        password: "${PG_PASSWORD}"
        name: "app_db"

  # 示例：Linux 服务器（密码登录）
  - name: "linux-app-server-01"
    host: "192.168.1.50"
    port: 22
    username: "ops"
    password: "${LINUX_SSH_PASSWORD}"
    os_type: "linux"
    tags: ["linux", "application", "production"]
    databases: []
```

#### 4.2 `rules.yaml` - 新增麒麟/RHEL 系自愈规则
添加使用 `yum`/`dnf` 的规则：

```yaml
  # ============================================
  # 麒麟/RHEL 系 Linux 自愈规则
  # ============================================
  - name: "clean_yum_cache"
    condition: "disk_usage_percent > 90"
    actions:
      - tool: "ssh_execute"
        params:
          command: "sudo yum clean all && sudo yum autoremove -y"
        confirm_required: true
    description: "磁盘使用率超过90%时清理 yum 缓存（麒麟/RHEL 系）"

  - name: "clean_journal_logs_rhel"
    condition: "disk_usage_percent > 85"
    actions:
      - tool: "ssh_execute"
        params:
          command: "sudo journalctl --vacuum-time=3d"
        confirm_required: false
    description: "磁盘使用率超过85%时清理 systemd 日志（通用 Linux）"
```

#### 4.3 `config_loader.py` - 扩展 os_type 说明
在 `ServerConfig` 的 `os_type` 字段注释中补充支持的值：

```python
os_type: str = "linux"  # linux / windows（麒麟、统信、openEuler 均为 linux）
```

---

### 5. 新增参数管理系统

**新增文件**：模型、API、前端页面
**修改文件**：路由注册、菜单、配置加载器

#### 5.1 新增模型 `/workspace/src/web/models/system_parameter.py`

```python
class SystemParameter(Base):
    __tablename__ = "system_parameters"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False)
    category: Mapped[str] = mapped_column(String(64), default="general")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
```

#### 5.2 新增 API `/workspace/src/web/api/parameters.py`
端点：
- `GET /parameters` - 获取参数列表（支持按分类筛选）
- `PUT /parameters/{key}` - 更新参数值
- `POST /parameters` - 新增参数
- `DELETE /parameters/{key}` - 删除参数
- `GET /parameters/export` - 导出为 .env 格式
- `POST /parameters/apply` - 将参数应用到环境变量并触发配置重载

#### 5.3 新增 Schema `/workspace/src/web/schemas/parameter.py`
Pydantic 模型：`SystemParameterResponse`、`SystemParameterCreate`、`SystemParameterUpdate`

#### 5.4 修改 `config_loader.py` - 加载时注入数据库参数
在 `load()` 方法中，加载 YAML 后、`_resolve_env_vars` 之前，从数据库读取参数并注入到 `os.environ`：

```python
def _load_db_parameters(self):
    """从数据库加载系统参数到环境变量"""
    try:
        from ..web.database import SessionLocal
        from ..web.models.system_parameter import SystemParameter
        db = SessionLocal()
        params = db.query(SystemParameter).all()
        for p in params:
            if p.value:
                os.environ[p.key] = p.value
        db.close()
    except Exception:
        pass  # 数据库未初始化时跳过
```

#### 5.5 修改 `app.py` - 注册参数管理路由
```python
from .api.parameters import router as parameters_router
app.include_router(parameters_router, prefix="/api/parameters", tags=["参数管理"])
```

#### 5.6 修改 `models/__init__.py` 和 `database.py`
注册 `SystemParameter` 模型

#### 5.7 新增前端页面 `/workspace/web/src/views/ParameterView.vue`
- 参数列表表格（key、value、描述、分类、是否密钥）
- 新增/编辑参数对话框（密钥值显示为 ***）
- 按分类筛选（SSH、数据库、LLM、邮件、通知、Web）
- "应用到配置"按钮 → 调用 `/parameters/apply` 触发环境变量注入 + 配置重载

#### 5.8 修改 `router/index.ts` - 添加路由
```typescript
{
  path: 'parameters',
  name: 'Parameters',
  component: () => import('@/views/ParameterView.vue'),
  meta: { title: '参数管理' },
}
```

#### 5.9 修改 `LayoutView.vue` - 添加菜单项
```typescript
{ index: '/parameters', title: '参数管理', icon: 'Key' },
```

---

### 6. 构建前端并推送代码

#### 6.1 构建前端
```bash
cd /workspace/web && npm run build
```

#### 6.2 推送到 Git
```bash
cd /workspace && git add -A && git commit -m "fix: 修复配置热重载崩溃、邮件配置、前端静态资源、增加麒麟系统示例和参数管理" && git push
```

---

## 文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/main.py` | 修改 | web 模式注入 OpsAgentApp 引用 |
| `src/web/app.py` | 修改 | create_app 签名改为接收 app_instance，挂载 StaticFiles，注册参数路由 |
| `src/web/core/config_manager.py` | 修改 | 增加健壮性检查，修复重置顺序 |
| `src/web/api/local_configs.py` | 修改 | 修复硬编码路径 |
| `src/tools/email_tool.py` | 修改 | 修复 is_configured 占位符检测 |
| `config/servers.yaml` | 修改 | 新增麒麟/UOS/openEuler/Linux 密码登录示例 |
| `config/rules.yaml` | 修改 | 新增 yum/dnf 系自愈规则 |
| `src/utils/config_loader.py` | 修改 | 加载时注入数据库参数，补充 os_type 注释 |
| `src/web/models/system_parameter.py` | 新增 | SystemParameter 模型 |
| `src/web/models/__init__.py` | 修改 | 注册 SystemParameter |
| `src/web/database.py` | 修改 | 导入 SystemParameter |
| `src/web/api/parameters.py` | 新增 | 参数管理 CRUD + 应用 API |
| `src/web/schemas/parameter.py` | 新增 | 参数管理 Schema |
| `web/src/views/ParameterView.vue` | 新增 | 参数管理前端页面 |
| `web/src/router/index.ts` | 修改 | 添加 /parameters 路由 |
| `web/src/views/LayoutView.vue` | 修改 | 添加参数管理菜单项 |

---

## 验证步骤

1. **启动后端**：`cd /workspace && python -m src.main --mode web`
2. **验证 :8000 可访问**：浏览器打开 `http://localhost:8000/` 应显示登录页
3. **验证登录**：用 admin/admin123 登录
4. **验证本地配置管理**：进入"本地配置管理"页面，编辑并保存配置，点击"重载配置"应成功
5. **验证参数管理**：进入"参数管理"页面，添加参数（如 SMTP_HOST），点击"应用到配置"
6. **验证邮件配置**：在参数管理中设置 SMTP 相关参数，在"告警管理"页面发送测试邮件
7. **验证服务器示例**：查看 `servers.yaml` 包含麒麟/UOS/openEuler 示例
8. **推送代码到 Git**
