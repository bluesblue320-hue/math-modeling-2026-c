# -*- coding: utf-8 -*-
"""
A2 Data Engineering Agent — Problem 1 数据预处理测试。

原则：
  * 测试只读取真实数据、断言 Mapping A 与数据质量。
  * 若原始数据本身存在负值等异常，测试必须**显式报告并 FAIL**，
    **不得**在测试中偷偷修改/裁剪数据。
"""

from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path

import pandas as pd
import pytest

# 允许从仓库根导入 src.preprocess_q1
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.preprocess_q1 import (  # noqa: E402
    DEFAULT_OUT_CSV,
    DEFAULT_SRC_FILE,
    N_PERIODS,
    TIME_STEP_MIN,
    build_dataset,
    format_interval,
    format_label,
    parse_source_time,
    read_raw_attachment,
    run_preprocess,
    validate,
)


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------
@pytest.fixture(scope="session")
def result() -> dict:
    """运行一次完整预处理，得到验证结果（不打印摘要）。"""
    return run_preprocess(print_summary=False)


@pytest.fixture(scope="session")
def dataset(result: dict) -> pd.DataFrame:
    """标准化数据集（从生成的 CSV 读回，确保交付物本身可用）。"""
    return pd.read_csv(DEFAULT_OUT_CSV)


# --------------------------------------------------------------------------
# 时间解析
# --------------------------------------------------------------------------
def test_parse_0010():
    assert parse_source_time(_dt.time(0, 10)) == 10
    assert parse_source_time("00:10") == 10
    assert parse_source_time("0:10") == 10


def test_parse_1010():
    assert parse_source_time("10:10") == 610


def test_parse_2350():
    assert parse_source_time("23:50") == 1430


def test_parse_next_day_0000():
    # '0:00+1' 表示次日 0:00 = 当天 24:00 = 1440 min
    assert parse_source_time("0:00+1") == 1440


def test_parse_rejects_garbage():
    with pytest.raises(ValueError):
        parse_source_time("not-a-time")
    with pytest.raises(ValueError):
        parse_source_time(None)


def test_format_label_roundtrip():
    assert format_label(10) == "00:10"
    assert format_label(610) == "10:10"
    assert format_label(1440) == "0:00+1"


def test_format_interval_edges():
    assert format_interval(0, 10) == "00:00-00:10"
    assert format_interval(1430, 1440) == "23:50-24:00"


# --------------------------------------------------------------------------
# 数据集结构
# --------------------------------------------------------------------------
def test_row_count_144(dataset: pd.DataFrame):
    assert len(dataset) == N_PERIODS == 144


def test_model_t_strictly_1_to_144(dataset: pd.DataFrame):
    assert dataset["model_t"].tolist() == list(range(1, 145))


def test_source_minute_10_to_1440(dataset: pd.DataFrame):
    assert dataset["source_minute"].tolist() == [i * 10 for i in range(1, 145)]


def test_source_minute_constant_step(dataset: pd.DataFrame):
    diffs = dataset["source_minute"].diff().dropna()
    assert set(diffs.tolist()) == {TIME_STEP_MIN}


def test_no_missing_values(dataset: pd.DataFrame):
    assert int(dataset[["price_yuan_per_kwh", "load_kw", "pv_kw"]].isna().sum().sum()) == 0


def test_source_excel_rows_2_to_145(dataset: pd.DataFrame):
    assert dataset["source_excel_row"].tolist() == list(range(2, 146))


def test_full_day_coverage_no_gap_no_overlap(dataset: pd.DataFrame):
    assert dataset["interval_start_min"].iloc[0] == 0
    assert dataset["interval_end_min"].iloc[-1] == 1440
    assert dataset["interval_start_min"].tolist() == [i * 10 for i in range(144)]
    assert dataset["interval_end_min"].tolist() == [i * 10 for i in range(1, 145)]


def test_no_duplicates(dataset: pd.DataFrame):
    assert dataset["model_t"].duplicated().sum() == 0
    assert dataset["physical_interval"].duplicated().sum() == 0
    assert dataset["source_label"].duplicated().sum() == 0


# --------------------------------------------------------------------------
# 关键映射点（Mapping A）
# --------------------------------------------------------------------------
def _row_at(dataset: pd.DataFrame, t: int) -> pd.Series:
    sub = dataset[dataset["model_t"] == t]
    assert len(sub) == 1, f"model_t={t} 行数不为 1"
    return sub.iloc[0]


def test_mapping_first(dataset: pd.DataFrame):
    r = _row_at(dataset, 1)
    assert r["physical_interval"] == "00:00-00:10"
    assert int(r["source_excel_row"]) == 2
    assert r["source_label"] == "00:10"
    assert int(r["source_minute"]) == 10


def test_mapping_1000(dataset: pd.DataFrame):
    r = _row_at(dataset, 61)
    assert r["physical_interval"] == "10:00-10:10"
    assert int(r["source_excel_row"]) == 62
    assert r["source_label"] == "10:10"


def test_mapping_1200(dataset: pd.DataFrame):
    r = _row_at(dataset, 73)
    assert r["physical_interval"] == "12:00-12:10"
    assert int(r["source_excel_row"]) == 74
    assert r["source_label"] == "12:10"


def test_mapping_1400(dataset: pd.DataFrame):
    r = _row_at(dataset, 85)
    assert r["physical_interval"] == "14:00-14:10"
    assert int(r["source_excel_row"]) == 86
    assert r["source_label"] == "14:10"


def test_mapping_1600(dataset: pd.DataFrame):
    r = _row_at(dataset, 97)
    assert r["physical_interval"] == "16:00-16:10"
    assert int(r["source_excel_row"]) == 98
    assert r["source_label"] == "16:10"


def test_mapping_1800(dataset: pd.DataFrame):
    r = _row_at(dataset, 109)
    assert r["physical_interval"] == "18:00-18:10"
    assert int(r["source_excel_row"]) == 110
    assert r["source_label"] == "18:10"


def test_mapping_2000(dataset: pd.DataFrame):
    r = _row_at(dataset, 121)
    assert r["physical_interval"] == "20:00-20:10"
    assert int(r["source_excel_row"]) == 122
    assert r["source_label"] == "20:10"


def test_mapping_last(dataset: pd.DataFrame):
    r = _row_at(dataset, 144)
    assert r["physical_interval"] == "23:50-24:00"
    assert int(r["source_excel_row"]) == 145
    assert r["source_label"] == "0:00+1"
    assert int(r["source_minute"]) == 1440


# --------------------------------------------------------------------------
# 数值类型与合理性
# --------------------------------------------------------------------------
@pytest.mark.parametrize("col", ["price_yuan_per_kwh", "load_kw", "pv_kw"])
def test_numeric_columns_are_numeric(dataset: pd.DataFrame, col: str):
    converted = pd.to_numeric(dataset[col], errors="raise")
    assert converted.dtype.kind == "f"


def test_load_all_non_negative(dataset: pd.DataFrame):
    bad = dataset[dataset["load_kw"] < 0]
    assert bad.empty, (
        "原始数据存在负负载（不在测试中修改，需人工确认）：\n"
        + bad.to_string()
    )


def test_pv_all_non_negative(dataset: pd.DataFrame):
    bad = dataset[dataset["pv_kw"] < 0]
    assert bad.empty, (
        "原始数据存在负光伏（不在测试中修改，需人工确认）：\n"
        + bad.to_string()
    )


def test_price_all_non_negative(dataset: pd.DataFrame):
    bad = dataset[dataset["price_yuan_per_kwh"] < 0]
    assert bad.empty, (
        "原始数据存在负电价（不在测试中修改，需人工确认）：\n"
        + bad.to_string()
    )


# --------------------------------------------------------------------------
# 端到端验证结果
# --------------------------------------------------------------------------
def test_validation_status_pass(result: dict):
    assert result["status"] == "PASS", f"验证失败: errors={result['errors']}"
    assert result["errors"] == []


def test_validation_no_missing_no_duplicates(result: dict):
    assert result["missing_values"] == 0
    assert result["duplicate_model_t"] == 0
    assert result["duplicate_intervals"] == 0


def test_validation_full_day_covered(result: dict):
    assert result["full_day_covered"] is True
    assert result["first_interval"] == "00:00-00:10"
    assert result["last_interval"] == "23:50-24:00"
    assert result["mapping"] == "RIGHT_ENDPOINT"


def test_raw_read_matches_expected_shape():
    """真实读取：原始附件应为 144 条数据行，时间列为混合类型。"""
    records = read_raw_attachment(DEFAULT_SRC_FILE)
    assert len(records) == 144
    types = {type(r["raw_time"]).__name__ for r in records}
    # 混合类型：datetime.time（Excel 时间）+ str（文本）
    assert "time" in types
    assert "str" in types


def test_build_dataset_is_pure_from_raw():
    """build_dataset 必须由原始读取构建，不得 hardcode 数值。"""
    records = read_raw_attachment(DEFAULT_SRC_FILE)
    df = build_dataset(records)
    assert len(df) == 144
    # 数值必须与源记录逐行一致
    for i, rec in enumerate(records):
        assert df.iloc[i]["price_yuan_per_kwh"] == rec["raw_price"]
        assert df.iloc[i]["load_kw"] == rec["raw_load"]
        assert df.iloc[i]["pv_kw"] == rec["raw_pv"]
