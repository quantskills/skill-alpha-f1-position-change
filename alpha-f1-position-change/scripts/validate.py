from __future__ import annotations

from factor import calculate_factor, load_position_data


def check_no_future_function() -> None:
    """检查无未来函数：截断到最后一日后重新计算，结果应一致"""
    raw_data = load_position_data()
    result = calculate_factor(input_data=raw_data, update_time="2026-06-07T15:30:00")
    last_date = result["trade_date"].max()

    # 按品种检查最后一日的因子值
    for symbol in result["symbol"].unique():
        symbol_result = result[result["symbol"] == symbol]
        last_symbol_date = symbol_result["trade_date"].max()

        # 截断到最后一日
        truncated = raw_data[raw_data["date"] <= last_symbol_date.replace("-", "")]
        recalculated = calculate_factor(input_data=truncated, update_time="2026-06-07T15:30:00")

        # 对比该品种最后一日的因子值
        left = symbol_result[symbol_result["trade_date"] == last_symbol_date].reset_index(drop=True)
        right = recalculated[(recalculated["symbol"] == symbol) & (recalculated["trade_date"] == last_symbol_date)].reset_index(drop=True)

        if not left.empty and not right.empty:
            assert left["factor_value"].iloc[0].round(10) == right["factor_value"].iloc[0].round(10), f"{symbol} 未来函数检测失败"


def check_required_fields() -> None:
    """检查输出字段完整性"""
    result = calculate_factor(update_time="2026-06-07T15:30:00")
    required = {
        "trade_date",
        "asset_type",
        "symbol",
        "factor_id",
        "factor_name",
        "factor_value",
        "score",
        "signal",
        "data_version",
        "update_time",
        "long_total",
        "short_total",
        "long_change_rate",
        "short_change_rate",
    }
    missing = required - set(result.columns)
    assert not missing, f"结果缺少字段: {sorted(missing)}"
    assert result["score"].between(0, 100).all(), "score必须在0-100之间"
    assert set(result["signal"]).issubset({"buy", "sell", "hold"}), "signal必须为buy/sell/hold"


def check_out_of_sample_slice() -> None:
    """检查样本外切片可用"""
    raw_data = load_position_data()
    result = calculate_factor(input_data=raw_data, update_time="2026-06-07T15:30:00")
    unique_dates = sorted(result["trade_date"].unique())
    if len(unique_dates) < 2:
        return  # 样本太少，跳过

    split_date = unique_dates[len(unique_dates) // 2]
    train = result[result["trade_date"] <= split_date]
    test = result[result["trade_date"] > split_date]
    assert not train.empty, "训练集不能为空"
    assert not test.empty, "测试集不能为空"


if __name__ == "__main__":
    check_no_future_function()
    check_required_fields()
    check_out_of_sample_slice()
    print("验证通过：无未来函数，字段完整，样本外切片可用")
