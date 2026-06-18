from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd
import panda_data


FACTOR_ID = "F1"
FACTOR_NAME = "期货前20席位持仓突变"
CHANGE_THRESHOLD = 0.02  # 2% 变化阈值
REQUIRED_COLUMNS = {"underlying_symbol", "date", "broker_name", "net_position", "position_type"}


def _get_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"请先设置环境变量 {name}")
    return value


def load_position_data(
    symbols: list[str] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pd.DataFrame:
    """从 panda_data 获取期货持仓数据

    默认获取当日往前三个月的数据。
    也可通过 start_date 和 end_date 指定日期范围（格式：YYYY-MM-DD）。
    支持环境变量 PANDA_DATA_START_DATE 和 PANDA_DATA_END_DATE。
    """
    username = _get_env("PANDA_DATA_USERNAME")
    password = _get_env("PANDA_DATA_PASSWORD")
    panda_data.init_token(username=username, password=password)

    # 计算日期范围
    end_date = end_date or os.getenv("PANDA_DATA_END_DATE", datetime.now().strftime("%Y-%m-%d"))
    if start_date is None:
        start_date = os.getenv("PANDA_DATA_START_DATE")
        if not start_date:
            # 往前三个月
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            start_dt = end_dt - timedelta(days=90)
            start_date = start_dt.strftime("%Y-%m-%d")

    # 转换为 YYYYMMDD 格式给 panda_data
    start_date_8 = start_date.replace("-", "")
    end_date_8 = end_date.replace("-", "")

    print(f"获取数据范围: {start_date} ~ {end_date}")

    # 获取多头数据
    print("获取多头数据...", end=" ", flush=True)
    symbols = symbols or ["AP", "CF", "CJ", "FJ", "OI", "SA", "SH", "SR", "UR"]
    long_df = panda_data.get_future_netposi_rank(
        start_date=start_date_8,
        end_date=end_date_8,
        underlying_symbol=symbols,
        max_rank=20,
        type="long"
    )

    # 获取空头数据
    print("空头数据...", end=" ", flush=True)
    short_df = panda_data.get_future_netposi_rank(
        start_date=start_date_8,
        end_date=end_date_8,
        underlying_symbol=symbols,
        max_rank=20,
        type="short"
    )

    # 合并数据
    if long_df is not None and not long_df.empty:
        long_df = long_df.copy()
        long_df['position_type'] = 'long'
    if short_df is not None and not short_df.empty:
        short_df = short_df.copy()
        short_df['position_type'] = 'short'

    if long_df is not None and not long_df.empty and short_df is not None and not short_df.empty:
        combined_df = pd.concat([long_df, short_df], ignore_index=True)
    elif long_df is not None and not long_df.empty:
        combined_df = long_df
    elif short_df is not None and not short_df.empty:
        combined_df = short_df
    else:
        combined_df = pd.DataFrame()

    if combined_df.empty:
        raise ValueError(f"未获取到期货持仓数据 (日期范围: {start_date} ~ {end_date})")

    print(f"[OK] 共 {len(combined_df)} 行")
    return combined_df.sort_values(["underlying_symbol", "date", "broker_name", "position_type"])


def validate_input(input_data: Any) -> pd.DataFrame:
    """验证输入数据"""
    df = pd.DataFrame(input_data)
    if df.empty:
        raise ValueError("持仓数据不能为空")

    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"持仓数据缺少必要字段: {sorted(missing)}")

    df = df.copy()
    df["underlying_symbol"] = df["underlying_symbol"].astype(str)
    df["date"] = df["date"].astype(str)
    df["broker_name"] = df["broker_name"].astype(str)
    df["net_position"] = pd.to_numeric(df["net_position"], errors="coerce")
    df["position_type"] = df["position_type"].astype(str)

    return df


def calculate_total_position(df: pd.DataFrame) -> pd.DataFrame:
    """计算每日每个品种的前20名持仓总和

    按日期、品种和持仓类型分组，计算前20名持仓的总和。
    """
    # 按日期、品种和持仓类型分组，求和净持仓
    daily_total = df.groupby(["underlying_symbol", "date", "position_type"])["net_position"].sum().reset_index()

    # 透视为宽表：每行一个日期+品种，包含多头和空头总和
    pivot_df = daily_total.pivot(index=["underlying_symbol", "date"], columns="position_type", values="net_position").reset_index()
    pivot_df = pivot_df.rename(columns={"long": "long_total", "short": "short_total"})

    # 填充缺失值
    pivot_df["long_total"] = pivot_df["long_total"].fillna(0)
    pivot_df["short_total"] = pivot_df["short_total"].fillna(0)

    # 统计参与计算的期货公司数量
    broker_count = df.groupby(["underlying_symbol", "date", "position_type"])["broker_name"].nunique().reset_index()
    broker_count = broker_count.pivot(index=["underlying_symbol", "date"], columns="position_type", values="broker_name").reset_index()
    broker_count = broker_count.rename(columns={"long": "long_broker_count", "short": "short_broker_count"})

    result = pivot_df.merge(broker_count, on=["underlying_symbol", "date"], how="left")
    result["long_broker_count"] = result["long_broker_count"].fillna(0).astype(int)
    result["short_broker_count"] = result["short_broker_count"].fillna(0).astype(int)

    return result.sort_values(["underlying_symbol", "date"])


def calculate_position_change(df: pd.DataFrame) -> pd.DataFrame:
    """计算多空持仓变化率

    计算多头和空头持仓的日变化率（按品种分组）。
    """
    df = df.sort_values(["underlying_symbol", "date"])

    # 按品种分组，计算前一日持仓
    df["prev_long_total"] = df.groupby("underlying_symbol")["long_total"].shift(1)
    df["prev_short_total"] = df.groupby("underlying_symbol")["short_total"].shift(1)

    # 计算多头变化率
    df["long_change_amount"] = df["long_total"] - df["prev_long_total"]
    df["long_change_rate"] = np.where(
        df["prev_long_total"].abs() > 0,
        df["long_change_amount"] / df["prev_long_total"].abs(),
        0
    )

    # 计算空头变化率
    df["short_change_amount"] = df["short_total"] - df["prev_short_total"]
    df["short_change_rate"] = np.where(
        df["prev_short_total"].abs() > 0,
        df["short_change_amount"] / df["prev_short_total"].abs(),
        0
    )

    # 因子值：多头变化率 - 空头变化率（正值表示多头优势增强）
    df["factor_value"] = df["long_change_rate"] - df["short_change_rate"]

    return df


def calculate_factor(
    input_data: Any | None = None,
    window: int | None = None,
    update_time: str | None = None,
) -> pd.DataFrame:
    """完整流程：加载数据 -> 计算总持仓 -> 计算变化率 -> 生成信号

    算法逻辑：
    1. 将某日的前20名持仓按品种加总，多头加在一起，空头加在一起
    2. 计算多空持仓变化率（每个品种独立计算）
    3. 如果多头增加2%以上或空头减少2%以上，判定为多头优势（buy）
    4. 如果多头减少2%以上或空头增加2%以上，判定为空头优势（sell）
    5. 其他情况为 hold

    Args:
        input_data: 可选，直接传入持仓数据 DataFrame。若为 None 则自动从 panda_data 加载。
        window: 本因子不使用窗口参数，保留以兼容标准接口。
        update_time: 结果生成时间，默认当前时间。

    Returns:
        包含以下标准字段的 DataFrame，每个品种每天一条记录：
        - trade_date: 交易日期
        - asset_type: 资产类型
        - symbol: 标的代码
        - factor_id: 因子编号
        - factor_name: 因子名称
        - factor_value: 因子原始值（多头变化率 - 空头变化率）
        - score: 标准化评分
        - rank: 横截面排名
        - signal: 交易信号
        - confidence: 置信度
        - data_version: 数据版本
        - update_time: 结果生成时间
        - long_total: 当前多头总持仓
        - short_total: 当前空头总持仓
        - prev_long_total: 前一日多头总持仓
        - prev_short_total: 前一日空头总持仓
        - long_change_rate: 多头变化率
        - short_change_rate: 空头变化率
        - long_broker_count: 参与多头计算的期货公司数
        - short_broker_count: 参与空头计算的期货公司数
    """
    update_time = update_time or datetime.now().isoformat(timespec="seconds")

    # 加载数据
    if input_data is None:
        raw_data = load_position_data()
    else:
        raw_data = input_data

    validated = validate_input(raw_data)
    total_position = calculate_total_position(validated)
    with_change = calculate_position_change(total_position)

    # 过滤掉第一天（无前一日数据）
    df = with_change.dropna(subset=["prev_long_total", "prev_short_total"]).copy()

    if df.empty:
        raise ValueError("历史数据长度不足，无法计算持仓变化率")

    # 生成信号
    # 多头增加2%以上或空头减少2%以上 → 多头优势
    # 多头减少2%以上或空头增加2%以上 → 空头优势
    conditions = [
        (df["long_change_rate"] >= CHANGE_THRESHOLD) | (df["short_change_rate"] <= -CHANGE_THRESHOLD),
        (df["long_change_rate"] <= -CHANGE_THRESHOLD) | (df["short_change_rate"] >= CHANGE_THRESHOLD),
    ]
    choices = ["buy", "sell"]
    df["signal"] = np.select(conditions, choices, default="hold")

    # 按日期计算横截面排名和评分
    df["rank"] = df.groupby("date")["factor_value"].rank(ascending=False, method="first").astype(int)
    df["score"] = df.groupby("date")["factor_value"].rank(pct=True).mul(100).round(2)
    df["confidence"] = (df["score"] / 100).round(4)

    # 添加元数据
    df["trade_date"] = pd.to_datetime(df["date"], format="%Y%m%d", errors="coerce").dt.strftime("%Y-%m-%d")
    df["asset_type"] = "future"
    df["symbol"] = df["underlying_symbol"]  # 使用原始品种代码
    df["factor_id"] = FACTOR_ID
    df["factor_name"] = FACTOR_NAME
    df["data_version"] = "real-v1"
    df["update_time"] = update_time

    columns = [
        "trade_date",
        "asset_type",
        "symbol",
        "factor_id",
        "factor_name",
        "factor_value",
        "score",
        "rank",
        "signal",
        "confidence",
        "long_total",
        "short_total",
        "prev_long_total",
        "prev_short_total",
        "long_change_rate",
        "short_change_rate",
        "long_broker_count",
        "short_broker_count",
        "data_version",
        "update_time",
    ]

    return df[columns].sort_values(["trade_date", "rank"]).reset_index(drop=True)


def get_significant_signals(df: pd.DataFrame, threshold: float = 0.02) -> pd.DataFrame:
    """获取显著信号"""
    buy_signals = df[df["signal"] == "buy"]
    sell_signals = df[df["signal"] == "sell"]
    return pd.concat([buy_signals, sell_signals]).sort_values("trade_date", ascending=False)


if __name__ == "__main__":
    result = calculate_factor(update_time=datetime.now().isoformat(timespec="seconds"))

    print(f"计算完成，共 {len(result)} 条记录")
    print(f"有效信号数量: {len(result[result['signal'] != 'hold'])}")
    print(f"涉及品种: {result['symbol'].unique().tolist()}")

    # 显示最新信号（按品种分组）
    print("\n各品种最新信号:")
    latest_by_symbol = result.groupby("symbol").last().reset_index()
    print(latest_by_symbol[["symbol", "trade_date", "signal", "factor_value", "long_change_rate", "short_change_rate"]].to_string(index=False))
