"""
生成生产版 Parquet 文件

此脚本从开发产物的 calculate_factor 函数获取因子结果，
进行质量检查后保存为 Parquet 文件供生产使用。
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import pandas as pd

# 从开发产物导入计算函数
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "alpha-f1-position-change" / "scripts"))
from factor import calculate_factor, load_position_data


def check_data_quality(df: pd.DataFrame) -> pd.DataFrame:
    """检查数据质量"""
    # 检查主键唯一性（对于期货持仓因子，主键为 trade_date + factor_id + symbol）
    key_cols = ["trade_date", "factor_id", "symbol"]
    duplicates = df.duplicated(subset=key_cols)
    if duplicates.any():
        print(f"警告：发现 {duplicates.sum()} 条重复记录，将自动去重")
        df = df.drop_duplicates(subset=key_cols, keep='first')

    # 检查必须字段完整性
    required_fields = [
        "trade_date", "asset_type", "symbol",
        "factor_id", "factor_name", "factor_value", "score", "signal",
        "data_version", "update_time",
        "long_total", "short_total", "long_change_rate", "short_change_rate"
    ]
    missing = df[required_fields].isna().any()
    if missing.any():
        missing_fields = missing[missing].index.tolist()
        raise ValueError(f"字段存在缺失值: {missing_fields}")

    # 检查分数范围
    if not df["score"].between(0, 100).all():
        raise ValueError("score 超出 0-100 范围")

    # 检查信号合法性
    valid_signals = {"buy", "sell", "hold"}
    invalid_signals = set(df["signal"].unique()) - valid_signals
    if invalid_signals:
        raise ValueError(f"非法信号值: {invalid_signals}")

    # 检查 asset_type
    if (df["asset_type"] != "future").any():
        raise ValueError("asset_type 必须为 'future'")

    # 检查 factor_id
    if (df["factor_id"] != "F1").any():
        raise ValueError("factor_id 必须为 'F1'")

    print("数据质量检查通过")
    return df


def generate_parquet(
    output_path: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> str:
    """生成生产版 Parquet 文件

    Args:
        output_path: 输出文件路径，默认为 skill 目录下的 database.parquet
        start_date: 开始日期，格式 YYYY-MM-DD
        end_date: 结束日期，格式 YYYY-MM-DD

    Returns:
        生成的 Parquet 文件路径
    """
    # 加载原始数据
    print("加载原始持仓数据...")
    raw_data = load_position_data(start_date=start_date, end_date=end_date)

    # 计算因子
    print("计算因子...")
    update_time = datetime.now().isoformat(timespec="seconds")
    factor_result = calculate_factor(input_data=raw_data, update_time=update_time)

    # 数据质量检查
    print("检查数据质量...")
    factor_result = check_data_quality(factor_result)

    # 确定输出路径
    if output_path is None:
        script_dir = Path(__file__).parent
        output_path = str(script_dir / "database.parquet")

    # 保存为 Parquet
    print(f"保存到 {output_path}...")
    factor_result.to_parquet(output_path, index=False)

    print(f"成功生成 {len(factor_result)} 条记录")
    print(f"日期范围: {factor_result['trade_date'].min()} ~ {factor_result['trade_date'].max()}")

    return output_path


if __name__ == "__main__":
    # 支持环境变量控制日期范围
    start_date = os.getenv("PANDA_DATA_START_DATE")
    end_date = os.getenv("PANDA_DATA_END_DATE")

    output_path = generate_parquet(start_date=start_date, end_date=end_date)
    print(f"\n生产文件已生成: {output_path}")
