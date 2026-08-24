---
name: bash
description: 本地 Bash 命令执行（仅只读，由 CommandPolicy 约束），用于 Agent 侧本地环境状态查询
when_to_use: 需要在 Agent 运行所在主机执行只读命令（本地环境、进程、网络连通性自检）时
metadata:
  os: [linux, windows]
  scope: local
  activation:
    mode: keyword
    keywords: [本地, local, 环境检查, 自检]
  security:
    class: read-only
    deny: [rm, dd, mv, chmod, chown, reboot, shutdown, kill]
AIGC:
  ContentProducer: '001191110102MAD55U9H0F10002'
  ContentPropagator: '001191110102MAD55U9H0F10002'
  Label: '1'
  ProduceID: 'badc77e3-93d2-495f-9744-f1c22b1f263f'
  PropagateID: 'badc77e3-93d2-495f-9744-f1c22b1f263f'
  ReservedCode1: 'a98ae9e3-cdaf-44b8-97e2-8279a986d9f6'
  ReservedCode2: 'a98ae9e3-cdaf-44b8-97e2-8279a986d9f6'
---

[技能: bash]

在 Agent 本地主机执行只读命令（subprocess 模式，`shell=False`）。

## 调用规则

1. 命令通过 `CommandPolicy` 校验：denylist 命令（rm/dd/reboot 等）一律拒绝；禁写/禁重定向。
2. 仅限只读命令：`ps` `df` `free` `uptime` `ss` `curl -sI` 等。
3. stdout 上限 64KiB，超时默认 30s。

## 推荐套路

- 本地自检：`ps aux | grep -E "nginx|redis" | head -20`
- 连通性：`curl -sI --max-time 5 http://localhost:8000/healthz`

## 不要做

- 不执行写操作/重定向/管道到 shell 解释器。
- 不在生产主机上执行未授权命令。