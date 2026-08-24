---
name: notify
description: 多渠道通知（企业微信/钉钉/飞书/Telegram/Slack/邮件），发送告警与通知
when_to_use: 需要发送告警、通知、报告给相关人员或群组时
metadata:
  scope: cloud
  activation:
    mode: always
  security:
    class: outbound
AIGC:
  ContentProducer: '001191110102MAD55U9H0F10002'
  ContentPropagator: '001191110102MAD55U9H0F10002'
  Label: '1'
  ProduceID: '8c320ecb-68c5-474e-85e6-1ba4feadce85'
  PropagateID: '8c320ecb-68c5-474e-85e6-1ba4feadce85'
  ReservedCode1: 'f5f7d154-a788-45ed-8d18-00a9f8775e99'
  ReservedCode2: 'f5f7d154-a788-45ed-8d18-00a9f8775e99'
---

[技能: notify]

通过统一通知路由向多渠道发送告警/通知。

## 调用规则

1. 工具 `send_notification`：channel ∈ wecom/dingtalk/lark/telegram/slack/all。
2. 邮件：`send_email`（SMTP 配置）。
3. 级别：info/warning/error/critical。

## 推荐套路

- 严重问题用 critical + 全渠道：`send_notification(level="critical", channel="all")`
- 例行通知用 info 单渠道。

## 不要做

- 不发送未经确认的告警（内容空/级别滥用）。
- 不把密钥写进消息内容。