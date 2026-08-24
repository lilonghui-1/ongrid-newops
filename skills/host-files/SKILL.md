---
name: host-files
description: 在远程主机上查看文件系统状态（大文件定位、du 汇总、stat 元信息），只读
when_to_use: 磁盘空间不足时定位大文件、查看目录占用、获取文件元信息
metadata:
  os: [linux]
  scope: remote
  activation:
    mode: keyword
    keywords: [大文件, 磁盘, du, 空间, find, inode]
  security:
    class: read-only
AIGC:
  ContentProducer: '001191110102MAD55U9H0F10002'
  ContentPropagator: '001191110102MAD55U9H0F10002'
  Label: '1'
  ProduceID: '768ed6ef-e1a6-4908-a119-7b92d42fc6f5'
  PropagateID: '768ed6ef-e1a6-4908-a119-7b92d42fc6f5'
  ReservedCode1: '78be29f3-c4fe-4d4c-b749-857b77a4ed42'
  ReservedCode2: '78be29f3-c4fe-4d4c-b749-857b77a4ed42'
---

[技能: host-files]

在远程主机上做文件系统只读检查，定位大文件与目录占用。

## 子命令

| 命令 | 说明 |
|---|---|
| host_find_large_files | 在指定目录下找大于 size 的文件（如 `find /var/log -type f -size +100M`） |
| host_du_summary | 目录占用汇总（`du -sh` 一批路径，3~8 个一次） |
| host_stat_file | 获取文件/目录元信息（stat） |

## 调用规则

1. 批量协议：`host_du_summary` 一次 3~8 个路径，不要单个路径反复调用。
2. 路径必须匹配 allowlist：`/var` `/opt` `/home` `/tmp` `/srv` `/data`；拒绝 `/proc` `/sys` `/dev`。
3. 结果截断 64KiB。

## 推荐套路

- 大文件：`find /var -type f -size +100M -exec ls -lh {} \;`（一次）
- 占用汇总：`du -sh /var/log /var/lib /opt/app 2>/dev/null`

## 不要做

- 不删除/移动任何文件（写操作交自愈 Agent）。
- 不使用 `find -delete`、`rm` 等写参数。