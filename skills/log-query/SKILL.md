---
name: log-query
description: 查询与分析日志（SSH 读取 / ELK / Loki），识别错误模式与频率
when_to_use: 需要查看应用日志、错误排查、统计异常频率时
metadata:
  scope: remote
  activation:
    mode: always
  security:
    class: read-only
AIGC:
  ContentProducer: '001191110102MAD55U9H0F10002'
  ContentPropagator: '001191110102MAD55U9H0F10002'
  Label: '1'
  ProduceID: '93861a7d-ec07-4dea-aa2a-79f7acbc0f35'
  PropagateID: '93861a7d-ec07-4dea-aa2a-79f7acbc0f35'
  ReservedCode1: '4c3d26a7-2bde-4ee8-97f7-4b6777202861'
  ReservedCode2: '4c3d26a7-2bde-4ee8-97f7-4b6777202861'
---

[技能: log-query]

采集与分析服务器日志，支持 SSH 文件读取与日志平台（ES/Loki）查询。

## 调用规则

1. SSH 读取：`log_fetch`（mode=tail/head/grep），注意日志路径与时间窗。
2. 平台查询：`log_platform_query`（ES DSL / Loki LogQL）与 `query_logql`。
3. 分析：`log_analyze`（错误率/严重度/时间分布），本地正则实现。

## 推荐套路

- 最近 1h 错误：LogQL `{app="nginx"} |= "error"` 或 ES `bool must term level:error`
- 采样：`log_fetch mode=tail lines=200 /var/log/app/error.log`

## 不要做

- 不把整个大文件全文回灌 LLM（只给统计与命中片段）。
- 不执行写操作。