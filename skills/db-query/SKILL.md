---
name: db-query
description: 查询数据库状态与数据（MySQL/PG/Oracle/达梦/金仓/Redis），仅允许只读 SQL
when_to_use: 需要查看数据库连接数、慢查询、表数据、主从状态、Redis 指标时
metadata:
  scope: remote
  activation:
    mode: always
  security:
    class: read-only
    sql_only: [SELECT, SHOW, DESCRIBE, DESC, EXPLAIN]
AIGC:
  ContentProducer: '001191110102MAD55U9H0F10002'
  ContentPropagator: '001191110102MAD55U9H0F10002'
  Label: '1'
  ProduceID: '8c3a86e6-1d46-45a8-acb5-1aefc0ed671f'
  PropagateID: '8c3a86e6-1d46-45a8-acb5-1aefc0ed671f'
  ReservedCode1: 'e05f3b8d-e26a-48ab-8f0b-d415672b4ec8'
  ReservedCode2: 'e05f3b8d-e26a-48ab-8f0b-d415672b4ec8'
---

[技能: db-query]

对配置的数据库执行只读查询。

## 调用规则

1. 仅允许 `SELECT` / `SHOW` / `DESCRIBE` / `DESC` / `EXPLAIN`（Oracle/达梦/金仓可加 `WITH`/`VALUES`）。
2. 凭证从服务器配置内部读取，**绝不由 LLM 传入**。
3. 查询带 LIMIT（默认 1000 行上限）；禁止 DML/DDL。

## 工具

| 工具 | 说明 |
|---|---|
| db_query | 执行只读 SQL（host/db_type/database/query） |
| db_status | 数据库状态（连接数/慢查询/主从等） |
| redis_info | Redis 内存/命中率指标 |

## 推荐套路

- 连接数：`SHOW STATUS LIKE 'Threads_connected'`（MySQL）
- 慢查询：`SHOW VARIABLES LIKE 'slow_query_log'`
- 主从：`SHOW SLAVE STATUS\G`（只读）

## 不要做

- 不执行 INSERT/UPDATE/DELETE/DDL。
- 不传凭据参数。