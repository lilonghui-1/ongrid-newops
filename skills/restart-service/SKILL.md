---
name: restart-service
description: 重启/启动/停止/查询服务（systemd/PowerShell），写操作，必须经 reviewer 审批
when_to_use: 自愈规则命中需要重启服务、或用户明确要求启停服务时
metadata:
  os: [linux, windows]
  scope: remote
  activation:
    mode: keyword
    keywords: [重启, restart, 启动, start, 停止, stop]
  security:
    class: mutating
    confirm_required: true
AIGC:
  ContentProducer: '001191110102MAD55U9H0F10002'
  ContentPropagator: '001191110102MAD55U9H0F10002'
  Label: '1'
  ProduceID: '9de83bc3-4170-4dd3-9742-d7d3ec58edb5'
  PropagateID: '9de83bc3-4170-4dd3-9742-d7d3ec58edb5'
  ReservedCode1: '3ba6377d-7d68-4f7b-9c29-c0c3cc5bdb35'
  ReservedCode2: '3ba6377d-7d68-4f7b-9c29-c0c3cc5bdb35'
---

[技能: restart-service]

对目标服务执行启停操作（**mutating**）。

## 前置条件

1. 必须命中自愈规则或用户明确指令。
2. 必须经 reviewer 审批（Decision: approve）后方可执行；reject 不重试。
3. 执行前记录服务状态基线。

## 工具

- `service_control`（action=restart/start/stop/status，Linux systemctl / Windows PowerShell）

## 操作流程

1. `status` 确认当前状态。
2. `restart` 执行重启（或按规则 start/stop）。
3. 再次 `status` 验证恢复，必要时配合 `system_metrics` 核验指标。

## 不要做

- 不审批就不执行；不批量重启未确认服务。
- 服务正常时不执行 restart。