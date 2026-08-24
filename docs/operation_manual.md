---
AIGC:
  ContentProducer: '001191110102MAD55U9H0F10002'
  ContentPropagator: '001191110102MAD55U9H0F10002'
  Label: '1'
  ProduceID: '30b1c9ad-2ba9-4048-8cde-a0ce607f6e47'
  PropagateID: '30b1c9ad-2ba9-4048-8cde-a0ce607f6e47'
  ReservedCode1: '318b63c9-c448-44ac-9308-5cd52c2e7bd5'
  ReservedCode2: '318b63c9-c448-44ac-9308-5cd52c2e7bd5'
---

# 运维 Agent 操作手册

[TOC]

## 一、产品概述与总体架构

### 1.1 产品概述

运维 Agent（ongrid-ops）是一款基于大语言模型（LLM）的智能运维 Agent 平台，融合声明式专家 Agent、技能目录、MCP 协议、可观测性工具、拓扑影响面分析、命令安全策略等先进能力，为运维团队提供端到端的自动化运维解决方案。

核心能力包括：

- **智能巡检**：服务器（CPU/内存/磁盘/网络）与数据库（MySQL/PostgreSQL/Oracle/达梦/人大金仓/Redis）自动化巡检
- **故障诊断**：LLM 多维关联分析（指标 + 日志 + 知识库 + 拓扑影响面）
- **日志分析**：远程 SSH 日志、ES/Loki 日志平台查询
- **自愈处理**：预定义规则驱动 + reviewer 审批门槛的安全自愈
- **声明式专家**：通过 agents/*.md 声明专家能力，按需路由
- **技能目录**：skills/ 目录声明可复用运维技能，支持 function 与 subprocess 两种执行模式
- **MCP 接入**：标准 MCP 协议，外部工具自动注册进 ToolRegistry
- **可观测性**：Prometheus（PromQL）、Loki（LogQL）、Grafana Dashboard 跳转
- **拓扑/RCA**：服务拓扑图与影响面展开，辅助根因分析
- **多渠道 IM**：企微、钉钉、飞书 Lark、Telegram、Slack、邮件
- **命令安全**：SSH 只读沙箱、denylist 命令过滤、禁写/禁重定向

### 1.2 总体架构

系统采用分层架构设计：

| 层级 | 模块 | 说明 |
|------|------|------|
| **Agent 层** | MasterAgent → InspectAgent / DiagnoseAgent / LogAgent / HealAgent / SpecialistAgent / ReviewerAgent / ReporterAgent | 任务理解、分解、路由、执行、汇总 |
| **技能层** | skills/ + src/skills/ | 声明式技能目录（SKILL.md）+ 运行时（loader/registry/executor） |
| **工具层** | src/tools/ | SSH 执行、DB 查询、日志工具、系统指标、服务控制、通知、可观测性 |
| **知识层** | knowledge/ + src/knowledge/ | 运维知识库 + 拓扑图（TopologyGraph） |
| **MCP 层** | src/mcp/ | MCP 客户端，注册外部工具 |
| **Web 层** | src/web/（FastAPI）+ web/（Vue3） | 管理平台与可视化 |
| **配置层** | config/ | config.yaml / servers.yaml / rules.yaml / mcp.yaml / skills.yaml / triggers.yaml |
| **部署层** | deploy/ | docker-compose / systemd / Prometheus / Loki / Grafana |

### 1.3 Master Agent 工作流程

1. **任务分析**：MasterAgent 接收用户任务，通过关键词预判 + LLM 分析判断任务类型
2. **路由执行**：根据任务类型路由到对应 Agent（inspect / diagnose / log / heal / specialist / report / composite）
3. **诊断增强**：诊断链路接入拓扑影响面（expand_topology）作为相关性上下文
4. **安全审批**：自愈/写操作经 ReviewerAgent 审批门槛（confirm_required 的专家触发）
5. **结果汇总**：生成最终报告，如有严重问题发送告警通知

## 二、快速上手

### 2.1 登录

1. 部署应用后（详见《部署手册》），浏览器访问 `http://<服务器IP>:8000`
2. 使用默认管理员账号登录：
   - 用户名：`admin`
   - 密码：`admin123`

> **安全提示**：生产环境应立即更换默认密码，并妥善保管 `OPS_AGENT_SECRET_KEY`。

### 2.2 界面布局

- **左侧边栏**：功能导航菜单（总览仪表盘、服务器监控、日志查询、应用服务、技能目录、MCP 管理、拓扑影响面、配置管理、本地配置管理、参数管理、告警管理、知识库管理、自愈规则管理、AI 对话、审计日志）
- **顶部**：当前页面标题、折叠按钮、用户信息
- **主区域**：当前功能页面

### 2.3 端到端示例：巡检 → 诊断 → 自愈

1. 在 AI 对话页面输入：`巡检所有服务器`
2. Agent 执行巡检，返回 CPU、内存、磁盘等指标结果
3. 若发现异常（如某服务器 CPU 超过阈值），系统自动进入诊断环节
4. 诊断时注入知识库上下文与拓扑影响面，给出根因分析
5. 若诊断结果建议重启服务，ReviewerAgent 审批通过后执行自愈操作
6. 生成最终报告，通过 IM 渠道发送告警通知

## 三、协同 Agent 使用

### 3.1 声明式专家

系统通过 `agents/*.md` 声明专家 Agent，每个文件包含 YAML frontmatter（name / role / tools / permission_mode / confirm_required / max_turns）与角色提示词。

内置专家包括：

| 专家名称 | 角色定位 | 典型场景 |
|---------|---------|---------|
| specialist-compute | 计算资源专家 | CPU/内存/负载异常 |
| specialist-disk | 磁盘存储专家 | 磁盘满/inode 耗尽/分区异常 |
| specialist-network | 网络专家 | 延迟/丢包/DNS/防火墙 |
| specialist-sre | SRE 专家 | 稳定性/高可用/容量规划 |
| specialist-ops | 运维服务专家 | 服务启停/systemd/端口 |
| reviewer | 审批专家 | 高危操作静态审查 |
| reporter | 报告专家 | 多源结果汇总 |

### 3.2 Master 路由逻辑

MasterAgent 分析用户任务后，按以下优先级路由：

1. **关键词预判**：匹配专家关键词（如"网络"→specialist-network、"磁盘"→specialist-disk）
2. **LLM 分析**：关键词未命中时，LLM 判断任务类型
3. **默认回退**：无法匹配时默认执行巡检

### 3.3 Reviewer 审批门槛

所有 mutating（写）操作需经 ReviewerAgent 审批：

- **通过**：命中已知 SOP 关键词（restart/重启/clean/清理/自愈/start 等）
- **拒绝**：缺少提案 / 破坏性操作（delete/drop/truncate/rm/格式化/清空/移除）/ 仅停止无恢复方案 / 未命中已知 SOP

> 安全默认策略：不确定时拒绝，需人工确认后执行。

## 四、巡检与日志

### 4.1 服务器巡检

通过 AI 对话输入巡检任务，Agent 自动连接目标服务器（SSH），采集 CPU、内存、磁盘、网络指标。巡检结果包含各指标的当前值、历史趋势与异常告警。

### 4.2 数据库巡检

支持 MySQL、PostgreSQL、Oracle、达梦、人大金仓、Redis 数据库的连接数、慢查询、表空间等指标巡检。

### 4.3 日志查询

- **远程日志**：通过 SSH 读取服务器日志文件，按关键词过滤
- **日志平台**：支持 Elasticsearch 和 Loki 日志平台查询，按时间范围、索引、关键词检索

### 4.4 日志分析 Agent

LogAgent 对日志内容进行 LLM 分析，识别异常模式、提取关键错误信息，并与知识库关联生成诊断建议。

## 五、诊断（RCA）与自愈

### 5.1 故障诊断

DiagnoseAgent 综合以下信息进行根因分析（RCA）：

- 巡检指标异常数据
- 日志分析结果
- 知识库匹配条目
- 拓扑影响面（expand_topology 展开相关节点与传播路径）

### 5.2 拓扑影响面

系统维护服务拓扑图（`knowledge/topology.yaml`），记录节点（服务/服务器/数据库）之间的依赖关系。诊断时自动展开影响面：

- 查看告警节点的上下游依赖
- 识别传播路径（reached_via）与语义标签（semantics）
- 过滤仅显示 propagating（有传播性）的节点

### 5.3 自愈处理

HealAgent 根据自愈规则（`rules.yaml`）执行自动修复：

1. 检查诊断结果是否建议自愈
2. 提案经 ReviewerAgent 审批
3. 审批通过后执行自愈操作（如重启服务、清理缓存）
4. 审批拒绝时记录日志，等待人工确认

### 5.4 自愈规则管理

在 Web 平台「自愈规则管理」页面维护规则：

| 规则名称 | 触发条件 | 执行操作 | 需确认 |
|---------|---------|---------|--------|
| restart_nginx | nginx_status == 'stopped' | service_control → nginx restart | 否 |
| clean_disk | disk_usage_percent > 90 | ssh_execute → 清理缓存 | 是 |

## 六、技能目录

### 6.1 概述

技能目录（skills/）以声明式方式管理可复用运维技能。每个技能包含 `SKILL.md` 声明文件，定义名称、描述、安全分类与激活策略。

### 6.2 内置技能

| 技能名 | 安全分类 | 执行模式 | 说明 |
|--------|---------|---------|------|
| ssh-readonly | read-only | function | 只读 SSH 命令执行 |
| host-files | read-only | function | 远程文件查看 |
| db-query | read-only | function | 数据库只读查询 |
| log-query | read-only | function | 日志检索 |
| restart-service | mutating | function | 服务重启（需审批） |
| notify | read-only | function | 多渠道通知 |
| bash | read-only | subprocess | 本地只读命令执行 |

### 6.3 安全策略

- **read-only 技能**：可自由执行，不触发审批
- **mutating 技能**：必须带 `reviewer_approved=true` 标记才能执行
- **本地命令（bash 技能）**：denylist 命令过滤（rm/dd/mv/chmod/reboot 等）、禁重定向与 shell 元字符、stdout 上限 64KB、超时 30s

### 6.4 Web 管理

在「技能目录」页面可以：

- 查看所有已加载技能及其安全分类
- 查看技能详情（SKILL.md 全文）
- 执行只读技能测试

## 七、MCP 接入

### 7.1 概述

系统支持标准 MCP（Model Context Protocol）协议，可通过 `config/mcp.yaml` 注册外部 MCP Server，其提供的工具自动包装进 ToolRegistry，供 Agent 调用。

### 7.2 配置

```yaml
# config/mcp.yaml
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

### 7.3 Web 管理

在「MCP 管理」页面可以：

- 查看已注册的 MCP Server 及其工具列表
- 调用 MCP 工具测试
- 启用/停用 MCP Server

## 八、拓扑影响面

### 8.1 概述

拓扑图（`knowledge/topology.yaml`）描述节点（服务/服务器/数据库）之间的依赖关系，支持：

- **概览**：查看拓扑图全貌（节点数、边数、节点类型统计）
- **展开影响面**：从指定节点出发，按深度展开上下游依赖
- **搜索节点**：按名称模糊搜索拓扑节点

### 8.2 Web 管理

在「拓扑影响面」页面可以：

- 查看拓扑概览统计
- 输入节点名称展开影响面（指定深度、是否仅显示 propagating 节点）
- 搜索节点定位

### 8.3 诊断联动

诊断链路自动调用 `expand_topology` 工具，以任务关键词为节点提示展开影响面，将相关节点信息注入诊断上下文。

## 九、多渠道 IM 通知

### 9.1 支持渠道

| 渠道 | 配置项 | 说明 |
|------|--------|------|
| 企业微信 | wecom_webhook | 群机器人 Webhook |
| 钉钉 | dingtalk_webhook | 群机器人 Webhook |
| 飞书 Lark | feishu_webhook | 群机器人 Webhook |
| Telegram | telegram_bot_token + telegram_chat_id | Bot API |
| Slack | slack_webhook | Incoming Webhook |
| 邮件 | smtp_host/port/user/password | SMTP |

### 9.2 告警通知触发

- 巡检结果含 critical 级别异常时自动触发
- 自愈操作执行后通知结果
- 支持手动通过 AI 对话触发通知（如"通知运维组 nginx 已恢复"）

## 十、知识库

### 10.1 概述

知识库（`knowledge/*.yaml`）存储故障排查经验条目，诊断时自动检索相关知识注入 Agent 上下文。

### 10.2 知识条目结构

| 字段 | 说明 |
|------|------|
| category | 分类（system / database / network / application） |
| symptom | 症状描述 |
| possible_causes | 可能原因列表 |
| diagnosis_steps | 诊断步骤 |
| solutions | 解决方案 |
| severity | 严重程度（low / medium / high / critical） |

### 10.3 Web 管理

在「知识库管理」页面支持新增/编辑/删除知识条目，按分类与严重程度筛选，按症状关键词搜索。

## 十一、工作流与告警通知

### 11.1 定时调度

通过 `config.yaml` 中的 `schedule` 段配置定时巡检与日志分析任务（cron 表达式）。

### 11.2 告警阈值

在 `config.yaml` 的 `thresholds` 段配置告警阈值（CPU、内存、磁盘使用率等），超过阈值时触发告警通知。

### 11.3 审计日志

系统记录所有关键操作（登录、配置修改、参数变更、服务操作、自愈执行等），在「审计日志」页面查看。

## 十二、审计与安全

### 12.1 命令安全策略

SSH 工具内置只读沙箱：

- **denylist**：rm / dd / mv / chmod / chown / mkfs / reboot / shutdown / useradd / passwd / kill / pkill / sudo / su
- **禁重定向**：拒绝 `>` / `>>` / `<` / `&&` / `||` / `;` / `|`
- **禁 shell 元字符**：拒绝 `$(` / `` ` `` / `${` / `sh -c`
- **stdout 上限**：64KB 截断
- **超时**：默认 30s

### 12.2 权限模式

声明式 Agent 通过 `permission_mode` 控制权限：

| 模式 | 说明 |
|------|------|
| read-only | 仅允许只读操作 |
| read | 允许只读 + 有限读取 |
| write | 允许写操作，confirm_required=True 时需 reviewer 审批 |

### 12.3 密钥管理

- 所有密钥通过 `.env` 环境变量注入，不经过 LLM
- 配置文件中使用 `${ENV_VAR}` 占位符递归解析
- Web 平台「参数管理」页面以掩码显示敏感参数

## 十三、常见排障

| 问题 | 排查方法 |
|------|---------|
| Agent 无响应 | 检查 LLM 配置（api_key / base_url）与网络连通性 |
| SSH 连接失败 | 检查 servers.yaml 中 SSH 配置、网络/防火墙 |
| 数据库驱动缺失 | 按需安装 oracledb / dmPython / ksycopg2 |
| 配置热重载失败 | 检查 YAML 语法，必要时重启服务 |
| 专家未加载 | 检查 agents/*.md frontmatter 格式与日志 |
| 技能执行失败 | 检查 SKILL.md 安全分类与工具注册状态 |
| MCP 工具不可用 | 检查 mcp.yaml 中 MCP Server 配置与连通性 |
| 拓扑展开为空 | 检查 knowledge/topology.yaml 是否存在且格式正确 |
| 自愈被拒绝 | 查看审计日志中 ReviewerAgent 拒绝原因 |

## 十四、附录

### 14.1 配置项速查

| 配置文件 | 关键字段 |
|---------|---------|
| config.yaml | llm / notify / email / schedule / web / thresholds / observability / im_channels |
| servers.yaml | servers[].name/host/port/username/databases |
| rules.yaml | heal_rules[].name/condition/actions/confirm_required |
| mcp.yaml | servers[].name/command/url/transport/enabled |
| skills.yaml | skills[].name/enabled |
| triggers.yaml | triggers[].name/event/actions |

### 14.2 PromQL 模板

```
# CPU 使用率
100 - (avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)

# 内存使用率
(node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes) / node_memory_MemTotal_bytes * 100

# 磁盘使用率
node_filesystem_avail_bytes{fstype!~"tmpfs"} / node_filesystem_size_bytes * 100
```

### 14.3 LogQL 模板

```
# Nginx 错误日志
{job="nginx", level="error"}

# 指定时间范围的关键词搜索
{job="app"} |= "timeout" | json | line_format "{{.message}}"
```

> AI生成