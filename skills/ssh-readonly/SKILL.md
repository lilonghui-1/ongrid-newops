---
name: ssh-readonly
description: 在远程主机上执行只读 Shell 命令（ps/df/free/top 采样等），受命令安全策略约束
when_to_use: 需要在被管主机上执行只读命令采集状态时；禁止用于写操作
metadata:
  os: [linux, windows]
  scope: remote
  activation:
    mode: always
  security:
    class: read-only
    deny: [rm, dd, mv, chmod, chown, mkfs, reboot, shutdown, useradd, passwd, kill, pkill]
AIGC:
  ContentProducer: '001191110102MAD55U9H0F10002'
  ContentPropagator: '001191110102MAD55U9H0F10002'
  Label: '1'
  ProduceID: 'd07b6d5c-4d84-4dfd-b009-5f2d1171e109'
  PropagateID: 'd07b6d5c-4d84-4dfd-b009-5f2d1171e109'
  ReservedCode1: 'fc0a4a35-903a-46dc-96cf-660ab3a1a6b7'
  ReservedCode2: 'fc0a4a35-903a-46dc-96cf-660ab3a1a6b7'
---

[技能: ssh-readonly]

通过 SSH 在远程主机执行只读命令。

## 调用规则

1. 只允许只读命令：`ps` `df` `free` `top -bn1` `uptime` `ss -tlnp` `systemctl status`（只读参数）`cat`（有限路径）等。
2. 禁止写/危险命令：`rm` `dd` `mv` `chmod` `chown` `mkdir` `reboot` `shutdown` `useradd` `passwd` `kill` `pkill`、重定向（`>` `>>`）、管道到 `sh`、`sudo`（默认）。
3. 命令通过 `ssh_execute` 工具执行（其内部含 CommandPolicy 校验）。

## 参数

| 参数 | 说明 |
|---|---|
| host | 目标主机（配置中的服务器 host） |
| command | 只读命令，建议单命令，可含管道（如 `ps aux \| grep nginx \| head -20`） |
| timeout | 超时秒数（默认 30，建议 ≤60） |

## 推荐套路

- 采样系统状态：`uptime`、`free -m`、`df -h`、`ss -tlnp`
- 查进程：`ps aux --sort=-%mem | head -15`

## 不要做

- 不执行写/破坏性命令（会被 CommandPolicy 拒绝并返回 error）。
- 不把命令拼接到 shell 解释器（管道数量 ≤ 2）。