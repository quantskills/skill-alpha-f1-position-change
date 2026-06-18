---
name: alpha-f1-position-change
description: 当需要开发、计算、验证期货前20席位持仓突变因子时，使用此 skill。支持多空持仓优势分析、主力调仓方向判断。
tags: [quant, alpha, development, future]
---

# 期货前20席位持仓突变 Alpha

## 适用场景

- 当用户需要分析期货前20席位持仓突变时
- 当用户需要计算基于主力调仓行为的 Alpha 因子时
- 当用户需要验证期货持仓类因子的完整交付流程时

## 因子逻辑

- 核心假设：将前20名持仓按品种加总，每个品种独立计算。当某品种多头增加2%以上或空头减少2%以上时，判定为该品种多头优势；当多头减少2%以上或空头增加2%以上时，判定为该品种空头优势。
- 计算公式：
  - 每个品种前20名多头总和 = Σ(多头持仓)
  - 每个品种前20名空头总和 = Σ(空头持仓)
  - 多头变化率 = (今日多头总和 - 昨日多头总和) / abs(昨日多头总和)
  - 空头变化率 = (今日空头总和 - 昨日空头总和) / abs(昨日空头总和)
  - factor_value = 多头变化率 - 空头变化率
  - signal = "buy"  当 多头变化率 >= 2% 或 空头变化率 <= -2%
  - signal = "sell" 当 多头变化率 <= -2% 或 空头变化率 >= 2%
  - signal = "hold" 其他情况
- 排序方向：因子值越大表示多头优势越强
- 适用市场：支持 panda_data `get_future_netposi_rank` 的所有期货品种
- 输出格式：每个品种每天生成一条记录，支持多品种 Rank IC 计算

## 输入数据

本示例使用 Panda data SDK 拉取期货持仓数据。正式开发时，因子计算必须使用 PandaAI data 数据拉取库或项目指定数据源获取数据。

| 字段 | 说明 | 来源 |
|---|---|---|
| date | 交易日期 | get_future_netposi_rank |
| broker_name | 期货公司名称 | get_future_netposi_rank |
| net_position | 净持仓量 | get_future_netposi_rank |
| position_type | 持仓类型(long/short) | 合并时添加 |

## 输出结果

每日期生成一条记录，包含以下字段：

| 字段 | 说明 |
|---|---|
| trade_date | 交易日期（YYYY-MM-DD 格式） |
| asset_type | 资产类型（future） |
| symbol | 标的代码 |
| factor_value | 因子原始值（多头变化率 - 空头变化率） |
| score | 0-100 标准化评分 |
| rank | 横截面排名 |
| signal | 交易信号：`buy`（多头优势）/ `sell`（空头优势）/ `hold` |
| confidence | 置信度 |
| long_total | 当前多头总持仓 |
| short_total | 当前空头总持仓 |
| prev_long_total | 前一日多头总持仓 |
| prev_short_total | 前一日空头总持仓 |
| long_change_rate | 多头变化率 |
| short_change_rate | 空头变化率 |
| long_broker_count | 参与多头计算的期货公司数 |
| short_broker_count | 参与空头计算的期货公司数 |

## 因子评价标准

Alpha 任务需要同时报告因子预测能力和策略层表现，不能只给单一收益结果。

| 分类 | 指标 | 方向 | 说明 |
|---|---|---|---|
| Signal Statistics | 信号频率 | 合理范围 | buy/sell 信号占比，过高可能过拟合 |
| Signal Statistics | 多头优势天数 | 参考指标 | 多头变化率 >= 2% 的天数 |
| Signal Statistics | 空头优势天数 | 参考指标 | 空头变化率 >= 2% 的天数 |
| Broker Coverage | 活跃期货公司数 | 越多越好 | 参与计算的期货公司数量 |

硬性要求：

- 不允许未来函数：因子在 `t` 日形成时，只能使用 `t` 日及以前可获得的数据。
- 不允许偷价：策略评估不得假设用 `t` 日收盘后才知道的信号，在同一个 `t` 日收盘价成交。
- 期货持仓数据通常在收盘后发布，本示例的策略层收益仅作为 MVP 演示口径；正式策略应考虑数据延迟和实际可交易性。

## 使用方式

Agent 使用本 skill 时，应在 `开发产物` 目录下执行命令，优先按下面顺序运行：

```bash
python scripts/factor.py
python scripts/validate.py
python scripts/backtest.py
```

运行前需要设置 `PANDA_DATA_USERNAME` 和 `PANDA_DATA_PASSWORD` 环境变量。
可选设置 `PANDA_DATA_START_DATE` 和 `PANDA_DATA_END_DATE` 控制样本区间。

## Agent 执行规则

1. 先运行 `scripts/factor.py`，确认 Panda data 能返回持仓数据，且因子结果非空。
2. 再运行 `scripts/validate.py`，确认字段完整、时间顺序正确、无未来函数问题。
3. 最后运行 `scripts/backtest.py`，输出信号统计、IC/ICIR、分层收益等回测指标。
4. 如果任一步失败，必须报告失败命令、错误信息和数据日期，不得直接进入生产。

## 成功标准

- `factor.py` 能输出包含 `factor_value`、`score`、`rank`、`signal` 的结果。
- `validate.py` 输出验证通过信息。
- `backtest.py` 至少输出 IC、ICIR、信号频率、样本数。
- 回测输出必须说明收益评估口径，避免未来函数和偷价。
- 结果中的 `data_version` 应为真实数据版本，例如 `real-v1`。

## 与生产产物的关系

开发产物用于计算、验证和回测；生产产物用于读取已生成结果。Agent 在开发验证时可以运行本 skill 的脚本，但在生产查询时应使用 `alpha-f1-position-change-production`，不要临时重算因子。

## 验收要求

- 不允许未来函数。
- 必须有样本外验证。
- 必须有回测指标。
- 正式任务必须使用 PandaAI data 或项目指定数据源实现。
- 不通过验证不得进入生产。

## 依赖

- Python 3.10+
- panda-data
- pandas
- numpy
