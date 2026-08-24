---
AIGC:
  ContentProducer: '001191110102MAD55U9H0F10002'
  ContentPropagator: '001191110102MAD55U9H0F10002'
  Label: '1'
  ProduceID: 'd4f8e781-034d-487b-acb5-5ce47c7ec049'
  PropagateID: 'd4f8e781-034d-487b-acb5-5ce47c7ec049'
  ReservedCode1: '85f039ad-5341-4ba0-af5b-89d5122904b9'
  ReservedCode2: '85f039ad-5341-4ba0-af5b-89d5122904b9'
---

# AGENTS.md — 编码与安全红线（Python 侧）

本文件约束在 ongrid-ops 仓库内编写 / 修改 Python 代码的约定。请严格遵守。

## 一、安全红线（最高优先级）

1. **只读优先（read-only by default）**：新增/修改工具默认只读；任何 mutating 操作
   （重启、删除、写文件、改配置、执行写命令）必须：
   - 声明 `mutating: true`；
   - 在 Agent 侧经过 reviewer 门槛（`confirm_required=True`）后方可执行；
   - 不经 LLM 直接传入密钥/凭据（凭证一律从 `config/` 或环境变量内部读取）。
2. **命令执行**：一律使用 `subprocess.run([...], shell=False)`（或 SSH 通道内执行），
   禁止 `shell=True`；禁止拼接用户输入进 shell。远程命令必须过 `CommandPolicy` 只读沙箱。
3. **密钥管理**：密钥（API Key / 密码 / webhook）一律放 `.env`（git 忽略）或
   `config.yaml` 的 `${ENV_VAR}` 占位；**禁止**硬编码密钥、**禁止**把密钥写进日志、
   `ToolParameter`（LLM 可见）或提交到仓库。
4. **外部请求**：所有出站 HTTP 使用 `httpx` 并设置超时与重试；对不可信 URL 做校验。
5. **路径安全**：文件读写必须做路径校验（拒绝 `..`、绝对路径越权、符号链接逃逸）。

## 二、架构与接口约定

1. **工具**：继承 `src/tools/base.py::BaseTool`，定义 `name/description/parameters` 与
   `execute(**kwargs) -> ToolResult`；在 `src/tools/__init__.py::register_all_tools` 注册；
   新模块若有配置段，同步在 `config.yaml` + `src/utils/config_loader.py::AppConfig` 中声明。
2. **Agent**：声明式 Agent 定义在 `agents/*.md`（frontmatter: name/description/tools/
   permission_mode/max_turns），由 `src/agents_loader.py` 解析注册，不直接手写 Agent 类；
   专业 Agent 返回统一 dict：`{"agent","task","result","tool_calls"}`。
3. **技能**：技能定义在 `skills/*/SKILL.md`（frontmatter + 正文），运行时在
   `src/skills/`（schema/loader/registry/executor），不允许绕过运行时直接调用技能实现。
4. **配置**：新增配置段 = `config.yaml` 段 + `AppConfig` 字段 + `${ENV_VAR}` 占位 + `.env.example`。
5. **测试**：新增模块必须配套 `tests/` 测试；外部依赖（LLM / HTTP / DB / SSH）一律 mock，
   不得在测试中发起真实外部调用。
6. **可观测性**：查询结果保留原始 JSON 形状直回 LLM（截断 8MiB），不深度反序列化。
7. **前端**：Vue3 `<script setup lang="ts">`，请求走 `@/api/request`，页面放 `web/src/views/`，
   路由在 `web/src/router/index.ts` 注册。

## 三、流程红线

- 提交前运行 `python -m compileall src` 与 `pytest -q`，必须全绿。
- 不把 `.env`、密钥、`__pycache__`、`node_modules`、`dist` 等纳入版本库。
- 修改共享配置（config.yaml 等）时保持向后兼容；`servers.yaml` / `rules.yaml` 结构不变。
- 文档改动默认出 `.docx`（docx-js），仓库同步更新 `docs/`。

> AI生成