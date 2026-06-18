---
name: alpha-f1-position-change-production
description: 当需要读取期货前20席位持仓突变 Alpha 的生产计算结果时，使用此 skill。该 skill 只读取已生成的 Parquet 结果，不在调用时重新计算因子。
tags: [quant, alpha, production, future]
---

# 期货前20席位持仓突变 Alpha 生产结果

## 适用场景

- 当用户需要查询期货前20席位持仓突变 Alpha 最新结果时
- 当交易 agent 需要使用该因子辅助交易判断时

## 结果文件

- 文件路径：`database.parquet`
- 数据格式：Parquet
- 更新频率：每日收盘后
- 生成方式：生产任务定时计算

## 主键

- `trade_date`
- `factor_id`
- `symbol`

## 字段说明

每日期生成一条记录，包含以下字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| trade_date | string | 交易日期 |
| asset_type | string | 固定为 `future` |
| symbol | string | 期货合约代码 |
| factor_id | string | 因子编号，固定为 `F1` |
| factor_name | string | 因子名称，固定为 `期货前20席位持仓突变` |
| factor_value | float | 因子原始值（多头变化率 - 空头变化率） |
| score | float | 标准化评分，0-100 |
| rank | int | 横截面排名 |
| signal | string | `buy`（多头优势）/ `sell`（空头优势）/ `hold` |
| confidence | float | 置信度，0-1 |
| long_total | float | 当前多头总持仓 |
| short_total | float | 当前空头总持仓 |
| prev_long_total | float | 前一日多头总持仓 |
| prev_short_total | float | 前一日空头总持仓 |
| long_change_rate | float | 多头变化率 |
| short_change_rate | float | 空头变化率 |
| long_broker_count | int | 参与多头计算的期货公司数 |
| short_broker_count | int | 参与空头计算的期货公司数 |
| data_version | string | 数据版本 |
| update_time | string | 结果生成时间 |

## 读取规则

交易 agent 读取 `database.parquet`，优先使用最新有效交易日结果。若最新结果不存在，可回退最近有效交易日，但必须说明数据日期。

## 禁止行为

- 不允许在 agent 调用时重新拉取原始行情。
- 不允许在 agent 调用时重新计算因子。
- 不允许手工修改 Parquet 结果。

## 数据来源

本生产结果来自 `alpha-f1-position-change` 开发产物的计算逻辑，通过生产任务定时计算并存储为 Parquet 文件。
