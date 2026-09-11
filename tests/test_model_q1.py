# -*- coding: utf-8 -*-
"""
A3 Optimization Agent — Problem 1 优化结果测试（A3 任务书 §35）。

原则：
  * 测试只读取真实产物（q1_data.csv / q1_solution.csv / q1_summary.json）与模型模块，
    断言模型实现与求解结果正确。
  * 若结果文件不存在，测试**必须 FAIL**，**不得 skip**。
  * 不得在测试中修改数据或结果，以图让测试通过。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.model_q1 import (  # noqa: E402
    DELTA_T,
    E_INIT,
    E_MAX,
    E_MIN,
    ETA_CH,
    ETA_DIS,
    N_PERIODS,
    P_CH_MAX,
    P_DIS_MAX,
    build_model,
)

DATA_CSV = REPO_ROOT / "data" / "processed" / "q1_data.csv"
SOLUTION_CSV = REPO_ROOT / "outputs" / "q1_solution.csv"
SUMMARY_JSON = REPO_ROOT / "outputs" / "q1_summary.json"
TOL = 1e-6

# 结果列（A3 §18）
REQUIRED_SOLUTION_COLUMNS = [
    "model_t", "physical_interval", "price_yuan_per_kwh", "load_kw", "pv_kw",
    "grid_kw", "grid_kwh", "pv_used_kw", "curtailment_kw", "curtailment_kwh",
    "charge_kw", "charge_kwh", "discharge_kw", "discharge_kwh",
    "energy_start_kwh", "energy_end_kwh", "interval_cost_yuan",
]


# --------------------------------------------------------------------------
# 载入辅助（文件不存在 → 断言失败）
# --------------------------------------------------------------------------
def _load_data() -> pd.DataFrame:
    assert DATA_CSV.exists(), f"缺少 A2 数据文件: {DATA_CSV}"
    return pd.read_csv(DATA_CSV, encoding="utf-8-sig")


def _load_solution() -> pd.DataFrame:
    assert SOLUTION_CSV.exists(), f"缺少 A3 结果文件: {SOLUTION_CSV}（测试必须 FAIL）"
    return pd.read_csv(SOLUTION_CSV, encoding="utf-8-sig")


def _load_summary() -> dict:
    assert SUMMARY_JSON.exists(), f"缺少 A3 汇总文件: {SUMMARY_JSON}（测试必须 FAIL）"
    with open(SUMMARY_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


# --------------------------------------------------------------------------
# 1–3 结构 / 步长
# --------------------------------------------------------------------------
def test_q1_data_rows_144():
    df = _load_data()
    assert len(df) == 144 == N_PERIODS


def test_model_t_1_to_144():
    df = _load_data()
    assert df["model_t"].tolist() == list(range(1, 145))
    sol = _load_solution()
    assert sol["model_t"].tolist() == list(range(1, 145))


def test_delta_t_is_one_sixth():
    assert DELTA_T == pytest.approx(1.0 / 6.0)
    assert DELTA_T * 144 == pytest.approx(24.0)


# --------------------------------------------------------------------------
# 4–5 首尾电量
# --------------------------------------------------------------------------
def test_initial_energy_6000():
    sol = _load_solution()
    assert float(sol["energy_start_kwh"].iloc[0]) == pytest.approx(E_INIT, abs=TOL)
    assert _load_summary()["initial_energy_kwh"] == pytest.approx(E_INIT, abs=TOL)


def test_terminal_energy_6000():
    sol = _load_solution()
    assert float(sol["energy_end_kwh"].iloc[-1]) == pytest.approx(E_INIT, abs=TOL)
    s = _load_summary()
    assert s["final_energy_kwh"] == pytest.approx(E_INIT, abs=TOL)
    assert s["terminal_energy_error_kwh"] <= TOL


# --------------------------------------------------------------------------
# 6–8 电量/充放电边界
# --------------------------------------------------------------------------
def test_energy_bounds():
    sol = _load_solution()
    e_start = sol["energy_start_kwh"].astype(float)
    e_end = sol["energy_end_kwh"].astype(float)
    assert e_start.min() >= E_MIN - TOL
    assert e_end.max() <= E_MAX + TOL
    assert e_start.max() <= E_MAX + TOL
    assert e_end.min() >= E_MIN - TOL


def test_charge_bounds():
    sol = _load_solution()
    ch = sol["charge_kw"].astype(float)
    assert ch.min() >= -TOL
    assert ch.max() <= P_CH_MAX + TOL


def test_discharge_bounds():
    sol = _load_solution()
    dis = sol["discharge_kw"].astype(float)
    assert dis.min() >= -TOL
    assert dis.max() <= P_DIS_MAX + TOL


# --------------------------------------------------------------------------
# 9 PV / 购电非负
# --------------------------------------------------------------------------
def test_grid_nonnegative():
    sol = _load_solution()
    assert sol["grid_kw"].astype(float).min() >= -TOL


def test_pv_used_bounds():
    sol = _load_solution()
    used = sol["pv_used_kw"].astype(float)
    pv = sol["pv_kw"].astype(float)
    assert used.min() >= -TOL
    assert (used - pv).max() <= TOL
    assert sol["curtailment_kw"].astype(float).min() >= -TOL


# --------------------------------------------------------------------------
# 11–13 平衡 / 递推 / 费用复算
# --------------------------------------------------------------------------
def test_power_balance():
    sol = _load_solution()
    residual = (
        sol["grid_kw"].astype(float)
        + sol["pv_used_kw"].astype(float)
        + sol["discharge_kw"].astype(float)
        - sol["load_kw"].astype(float)
        - sol["charge_kw"].astype(float)
    )
    assert residual.abs().max() <= TOL


def test_energy_recursion():
    sol = _load_solution()
    e_start = sol["energy_start_kwh"].astype(float).tolist()
    e_end = sol["energy_end_kwh"].astype(float).tolist()
    ch = sol["charge_kw"].astype(float).tolist()
    dis = sol["discharge_kw"].astype(float).tolist()
    worst = 0.0
    for t in range(144):
        expected = e_start[t] + ETA_CH * ch[t] * DELTA_T - (dis[t] / ETA_DIS) * DELTA_T
        worst = max(worst, abs(e_end[t] - expected))
    assert worst <= TOL


def test_objective_recomputation():
    sol = _load_solution()
    s = _load_summary()
    recomputed = float((sol["price_yuan_per_kwh"].astype(float) * sol["grid_kwh"].astype(float)).sum())
    assert recomputed == pytest.approx(s["objective_cost_yuan"], abs=1e-6)
    assert s["objective_abs_diff_yuan"] <= TOL


# --------------------------------------------------------------------------
# 14–16 结果文件结构
# --------------------------------------------------------------------------
def test_solution_csv_144_rows():
    sol = _load_solution()
    assert len(sol) == 144
    assert list(sol.columns) == REQUIRED_SOLUTION_COLUMNS


def test_no_nan():
    sol = _load_solution()
    assert int(sol.isna().sum().sum()) == 0


def test_physical_interval_matches_a2():
    data = _load_data()
    sol = _load_solution()
    assert sol["physical_interval"].astype(str).tolist() == data["physical_interval"].astype(str).tolist()
    # model_t=61 必须对应 10:00-10:10（不得修改）
    row = sol[sol["model_t"] == 61].iloc[0]
    assert str(row["physical_interval"]) == "10:00-10:10"


# --------------------------------------------------------------------------
# 附加：模型结构 / 目标含 Δt / 同时充放电 / summary 核心字段
# --------------------------------------------------------------------------
def test_model_variable_count():
    prices = [0.5] * 144
    loads = [4000.0] * 144
    pv = [0.0] * 144
    bundle = build_model(prices, loads, pv)
    # 4 类功率变量 × 144 + 145 个状态边界 = 721 个连续变量
    assert len(bundle.prob.variables()) == 4 * 144 + 145


def test_objective_includes_delta_t():
    c0 = 0.5
    prices = [c0] * 144
    loads = [4000.0] * 144
    pv = [0.0] * 144
    bundle = build_model(prices, loads, pv)
    coef = bundle.cost_expr.get(bundle.p_grid[1])
    assert coef == pytest.approx(c0 * DELTA_T)   # 不得漏掉 Δt


def test_no_simultaneous_charge_discharge():
    sol = _load_solution()
    ch = sol["charge_kw"].astype(float)
    dis = sol["discharge_kw"].astype(float)
    both = (ch > 1e-6) & (dis > 1e-6)
    assert int(both.sum()) == 0
    assert _load_summary()["simultaneous_charge_discharge_count"] == 0


def test_summary_core_fields_and_status():
    s = _load_summary()
    assert s["status"] == "OPTIMAL"
    assert s["solver_status"] == "Optimal"
    assert s["secondary_optimization_used"] is False
    for key in [
        "objective_cost_yuan", "total_grid_energy_kwh", "total_charge_energy_kwh",
        "total_discharge_energy_kwh", "total_pv_available_kwh", "total_pv_used_kwh",
        "total_curtailment_kwh", "initial_energy_kwh", "final_energy_kwh",
        "min_energy_kwh", "max_energy_kwh", "max_charge_kw", "max_discharge_kw",
        "max_grid_kw", "max_power_balance_residual_kw",
        "max_energy_recursion_residual_kwh", "terminal_energy_error_kwh",
        "simultaneous_charge_discharge_count", "max_simultaneous_kw",
    ]:
        assert key in s, f"summary 缺少核心字段: {key}"


def test_summary_validation_all_pass():
    s = _load_summary()
    assert s["validation_all_pass"] is True
    assert all(s["validation_checks"].values())


def test_key_intervals_present():
    s = _load_summary()
    assert [k["model_t"] for k in s["key_intervals"]] == [61, 73, 85, 97, 109, 121]
