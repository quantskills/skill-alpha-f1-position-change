from __future__ import annotations

import pandas as pd

from factor import calculate_factor, load_position_data


def build_forward_returns(positions: pd.DataFrame) -> pd.DataFrame:
    """构建未来收益

    对于期货持仓因子，使用多空持仓总变化作为收益 proxy。
    注意：正式回测应使用期货价格数据计算真实收益。
    """
    # 按品种、日期和持仓类型分组求和
    daily_total = positions.groupby(["underlying_symbol", "date", "position_type"])["net_position"].sum().reset_index()
    pivot_df = daily_total.pivot(index=["underlying_symbol", "date"], columns="position_type", values="net_position").reset_index()
    pivot_df = pivot_df.rename(columns={"long": "long_total", "short": "short_total"})
    pivot_df["long_total"] = pivot_df["long_total"].fillna(0)
    pivot_df["short_total"] = pivot_df["short_total"].fillna(0)

    # 计算下一日持仓（按品种分组）
    pivot_df = pivot_df.sort_values(["underlying_symbol", "date"])
    pivot_df["next_long_total"] = pivot_df.groupby("underlying_symbol")["long_total"].shift(-1)
    pivot_df["next_short_total"] = pivot_df.groupby("underlying_symbol")["short_total"].shift(-1)

    # 计算净持仓变化作为 proxy
    pivot_df["forward_return"] = (
        (pivot_df["next_long_total"] - pivot_df["long_total"]) -
        (pivot_df["next_short_total"] - pivot_df["short_total"])
    ) / (pivot_df["long_total"].abs() + pivot_df["short_total"].abs() + 1e-6)

    pivot_df["trade_date"] = pd.to_datetime(pivot_df["date"], format="%Y%m%d", errors="coerce").dt.strftime("%Y-%m-%d")
    pivot_df["symbol"] = pivot_df["underlying_symbol"]

    return pivot_df[["trade_date", "symbol", "forward_return"]].dropna()


def pearson_ic(x: pd.DataFrame) -> float:
    """计算 Pearson IC"""
    return float(x["factor_value"].corr(x["forward_return"]))


def rank_ic(x: pd.DataFrame) -> float:
    """计算 Rank IC"""
    factor_rank = x["factor_value"].rank(method="average")
    return_rank = x["forward_return"].rank(method="average")
    return float(factor_rank.corr(return_rank))


def information_ratio(returns: pd.Series) -> float:
    """计算信息比率"""
    std = returns.std()
    if returns.empty or not std:
        return 0.0
    return float(returns.mean() / std * (252**0.5))


def annualized_return(returns: pd.Series) -> float:
    """计算年化收益率"""
    if returns.empty:
        return 0.0
    cumulative_return = float((1 + returns).prod() - 1)
    years = len(returns) / 252
    if years <= 0:
        return cumulative_return
    return float((1 + cumulative_return) ** (1 / years) - 1)


def run_backtest() -> dict:
    """运行回测

    计算期货持仓因子的 IC、ICIR、分层收益等指标。
    注意：本示例使用持仓变化作为收益 proxy，正式回测应使用期货价格数据。
    """
    # 加载原始持仓数据
    raw_positions = load_position_data()

    # 计算因子
    factor = calculate_factor(input_data=raw_positions)

    # 构建未来收益（使用持仓变化作为 proxy）
    forward = build_forward_returns(raw_positions)

    # 合并数据（按日期和品种）
    panel = factor.merge(forward, on=["trade_date", "symbol"], how="inner")

    if panel.empty:
        raise ValueError("回测样本为空")

    # 按日期计算 IC 指标
    daily_ic = panel.groupby("trade_date").apply(pearson_ic).dropna()
    daily_rank_ic = panel.groupby("trade_date").apply(rank_ic).dropna()
    ic = float(daily_ic.mean()) if not daily_ic.empty else 0.0
    icir = float(daily_ic.mean() / daily_ic.std()) if len(daily_ic) > 1 and daily_ic.std() else 0.0
    rank_ic_value = float(daily_rank_ic.mean()) if not daily_rank_ic.empty else 0.0
    rank_icir = (
        float(daily_rank_ic.mean() / daily_rank_ic.std())
        if len(daily_rank_ic) > 1 and daily_rank_ic.std()
        else 0.0
    )

    # 分层收益（按日期）
    panel["group"] = panel.groupby("trade_date")["factor_value"].transform(
        lambda s: pd.qcut(s.rank(method="first"), 2, labels=["low", "high"], duplicates="drop")
    )
    group_return = panel.groupby("group", observed=False)["forward_return"].mean().round(6).to_dict()

    # 买入信号收益
    buy_return = panel[panel["signal"] == "buy"].groupby("trade_date")["forward_return"].mean().fillna(0)
    if buy_return.empty:
        buy_return = panel.groupby("trade_date")["forward_return"].mean().fillna(0)

    # 累计收益和回撤
    curve = (1 + buy_return).cumprod()
    cumulative_return = float(curve.iloc[-1] - 1) if not curve.empty else 0.0
    drawdown = curve / curve.cummax() - 1
    max_drawdown = float(drawdown.min()) if not drawdown.empty else 0.0
    calmar = cumulative_return / abs(max_drawdown) if max_drawdown else 0.0

    # 换手率（基于信号变化）
    signal_changes = (panel["signal"] != panel.groupby("symbol")["signal"].shift(1)).sum()
    turnover = float(signal_changes / len(panel)) if len(panel) > 0 else 0.0

    # 信号统计
    total_records = len(panel)
    buy_signals = len(panel[panel["signal"] == "buy"])
    sell_signals = len(panel[panel["signal"] == "sell"])
    hold_signals = len(panel[panel["signal"] == "hold"])

    # 按品种统计信号
    symbol_signals = panel.groupby("symbol")["signal"].value_counts().unstack(fill_value=0).to_dict()

    return {
        "IC": round(ic, 6),
        "ICIR": round(icir, 6),
        "Rank IC": round(rank_ic_value, 6),
        "Rank ICIR": round(rank_icir, 6),
        "IR(SHR*)": round(information_ratio(buy_return), 6),
        "CR": round(calmar, 6),
        "ARR(%)": round(annualized_return(buy_return) * 100, 6),
        "MDD(%)": round(max_drawdown * 100, 6),
        "分层收益": group_return,
        "换手率": round(turnover, 6),
        "样本数": int(len(panel)),
        "买入信号": buy_signals,
        "卖出信号": sell_signals,
        "持仓信号": hold_signals,
        "品种信号分布": symbol_signals,
        "评估口径": "因子在 t 日形成，基于 t 日及以前的持仓数据计算；收益使用持仓变化作为 proxy，正式回测应使用期货价格数据计算真实收益；正式策略应考虑数据发布延迟和实际可交易性。",
    }


if __name__ == "__main__":
    metrics = run_backtest()
    for key, value in metrics.items():
        if key == "品种信号分布":
            print(f"{key}:")
            for symbol, signals in value.items():
                print(f"  {symbol}: {signals}")
        else:
            print(f"{key}: {value}")
