# Ops Agent 操作手册

## 一、概述

Ops Agent 是基于 LLM 的智能运维 Agent，提供服务器/数据库巡检、故障自动诊断、日志分析、简单问题自愈处理等能力，并配套 Web 管理平台进行图形化运维。

本文档面向 Web 管理平台的**使用者**（运维工程师、测试工程师、DevOps 团队），覆盖平台各功能页的操作方式与系统配置说明。

## 二、快速入门

### 2.1 登录

1. 部署应用后（详见《部署手册》`docs/deployment.md`），浏览器访问 `http://<服务器IP>:8000`
2. 使用默认管理员账号登录：
   - 用户名：`admin`
   - 密码：`admin123`

> **安全提示**：登录后请立即在右上角用户菜单中选择「退出登录」前先修改密码（密码修改通过系统账号管理完成）。生产环境应立即更换默认密码，并妥善保管 `OPS_AGENT_SECRET_KEY`。

### 2.2 界面布局

- **左侧边栏**：功能导航菜单（总览仪表盘、服务器监控、日志查询、应用服务、配置管理、本地配置管理、参数管理、告警管理、知识库管理、自愈规则管理、AI 对话、审计日志）
- **顶部**：当前页面标题、折叠按钮、用户信息（角色）
- **主区域**：当前功能页面

## 三、Web 平台功能使用说明

### 3.1 总览仪表盘

展示系统运行总览：服务器/服务状态、告警统计、近期巡检结果、关键指标等，便于快速掌握整体健康度。

### 3.2 服务器监控 / 服务器详情

- **列表**：查看已配置服务器的基本状态与关键指标
- **详情**：点击进入后查看该服务器 CPU、内存、磁盘、网络等实时指标

> 服务器数据来源于 `servers.yaml` 中配置的服务器及其 SSH/采集信息。

### 3.3 日志查询

支持按服务器、关键词查询日志内容，展示时间、级别、来源等信息，用于故障排查与分析。

### 3.4 应用服务

包含两个标签页：

- **动态服务**：选择服务器后实时获取系统服务列表（`systemctl`），可对单个服务执行「启动 / 停止 / 重启」，或勾选多个服务进行「批量重启」
- **服务定义**：管理受监控的应用服务定义（服务名称、显示名称、所属服务器、分类、端口、是否启用监控），可新增、编辑、删除服务定义

### 3.5 配置管理

用于管理**远程服务器**上的配置文件（如 `nginx.conf`），通过 SSH 读取与写入。适用于修改被管服务器的运行配置。

> 注意：此处与「本地配置管理」不同，本地配置管理操作的是**本机后端自身的 YAML 配置**。

### 3.6 本地配置管理

用于在线编辑本机后端的三份 YAML 配置，采用「标签页」切换：

| 标签页 | 对应文件 | 内容 |
|--------|---------|------|
| 主配置 | `config.yaml` | LLM、通知、调度、日志平台、Web、邮件、告警阈值 |
| 服务器配置 | `servers.yaml` | 服务器列表、SSH、数据库连接 |
| 自愈规则 | `rules.yaml` | 自愈触发条件、执行操作、确认级别 |

**操作步骤：**

1. 点击顶部标签页选择要编辑的配置文件
2. 在编辑器（YAML 语法高亮）中修改内容
3. 点击「保存」→ 确认后写入，系统**自动备份原文件**并**自动触发配置热重载**
4. 也可点击「重载配置」手动触发热重载；「刷新」用于重新加载当前文件内容

**提示：**
- 修改后未保存时切换标签页，会提示是否放弃未保存的修改
- 若热重载失败，需检查 YAML 语法，必要时重启服务（见 3.11「常见运维操作」）

### 3.7 参数管理

管理系统运行所需的参数（如 SSH 密码、数据库密码、密钥等敏感信息）：

- 新增 / 编辑 / 删除参数
- 参数可分「分类」（SSH、数据库、LLM、邮件等）
- 敏感参数以掩码（`******`）显示
- 「应用到配置」：将参数值注入环境变量并触发热重载

> 敏感信息仅显示掩码，编辑时需重新输入，避免泄露。

### 3.8 告警管理

查看告警通知记录，支持邮件告警等渠道的发送历史与管理（告警类型与阈值在 `config.yaml` 中配置）。

### 3.9 知识库管理

维护故障排查知识条目。每个条目包含：症状描述、分类、严重程度、可能原因、诊断步骤、解决方案。支持：

- 新增 / 编辑 / 删除知识条目
- 按分类、严重程度筛选，按症状关键词搜索

> 知识库用于在故障诊断时向 Agent 注入上下文，提升诊断准确率。

### 3.10 自愈规则管理

维护自愈规则。每条规则包含：规则名称、触发条件、执行操作（一个或多个，含工具、参数、是否需人工确认）、启用状态。

支持新增 / 编辑 / 删除规则、启用/停用规则。

**规则示例：**

| 名称 | 触发条件 | 操作 | 需确认 |
|------|---------|------|--------|
| restart_nginx | `nginx_status == 'stopped'` | service_control → nginx restart | 否（低风险） |
| clean_disk | `disk_usage_percent > 90` | ssh_execute → 清理缓存 | 是（高风险） |

> 高风险操作（如清理、终止进程）建议开启「需人工确认」，防止误操作。

### 3.11 AI 运维对话

通过自然语言与运维 Agent 交互，例如：

- `巡检所有服务器`
- `诊断 192.168.1.10 的 CPU 异常`
- `分析 nginx 错误日志`
- `检查 Redis 内存使用情况`

Agent 会调用相应工具（巡检、诊断、日志、自愈等）并返回结构化结果。

### 3.12 审计日志

记录系统中的关键操作（登录、配置修改、参数变更、服务操作等），便于安全审计与追责。

## 四、系统配置详解

> 以下配置均可通过「本地配置管理」在线编辑，或直接编辑 `config/` 目录下的文件。

### 4.1 config.yaml — 主配置

| 配置段 | 说明 | 关键字段 |
|--------|------|---------|
| `llm` | LLM 服务配置 | provider、api_key、base_url、model、temperature、max_tokens |
| `llm_models` | Web 端 AI 对话可选模型列表 | 支持 gpt-4 / qwen-plus / deepseek-chat 等 |
| `notify` | 通知渠道 | wecom_webhook、dingtalk_webhook |
| `email` | 邮件通知 | smtp_host、smtp_port、smtp_user/password、from_addr、to_addrs |
| `log_level` | 日志级别 | DEBUG / INFO / WARNING / ERROR |
| `db_drivers` | 国产数据库驱动版本要求 | oracledb、dmPython、ksycopg2 |
| `log_platforms` | 日志平台（ES / Loki） | type、url、index、username/password |
| `schedule` | 定时巡检 / 日志分析 | cron 表达式、enabled |
| `web` | Web 平台 | host、port、secret_key、默认账号 |
| `thresholds` | 告警阈值 | cpu、memory、disk |

### 4.2 servers.yaml — 服务器配置

定义被管服务器及关联数据库：

```yaml
servers:
  - name: "web-server-01"
    host: "192.168.1.10"
    port: 22
    username: "ops"
    private_key_path: "${SSH_PRIVATE_KEY_PATH}"
    os_type: "linux"          # linux / windows
    tags: ["web", "production"]
    databases:
      - type: "mysql"         # mysql / postgresql / oracle / dm / kingbase / redis
        host: "127.0.0.1"
        port: 3306
        username: "monitor"
        password: "${MYSQL_PASSWORD}"
        name: "app_db"
```

### 4.3 rules.yaml — 自愈规则

定义自愈触发条件与执行操作：

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

**字段说明：**
- `condition`：触发条件（支持运算符与布尔逻辑）
- `actions[].tool`：执行工具（service_control / ssh_execute / db_execute / send_notification 等）
- `actions[].params`：工具参数
- `actions[].confirm_required`：是否需人工确认（`true` 高风险、`false` 低风险自动执行）

## 五、常见运维操作

| 操作 | 命令 / 方式 |
|------|------------|
| 热重载配置 | Web「本地配置管理」保存后自动触发，或点击「重载配置」按钮 |
| 手动重启服务 | `sudo systemctl restart ops-agent`（systemd 方式） |
| 查看日志 | `sudo journalctl -u ops-agent -f` |
| 重置数据库 | 删除 `data/ops_agent_web.db` 后重启服务，自动重建 |
| 清理无效配置 | 修改 `config.yaml` 中对应段落后热重载 |

> systemd 服务部署方式详见《部署手册》第三章。