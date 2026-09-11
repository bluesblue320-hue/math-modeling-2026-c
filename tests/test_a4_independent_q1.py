# -*- coding: utf-8 -*-
"""
A4 Independent Validation / Red Team Agent — independent tests for Problem 1.

=========================== INDEPENDENCE CONTRACT ===========================
This test module MUST NOT import ``src.model_q1`` or ``src.solve_q1`` and MUST
NOT call ``build_model()`` / ``solve_q1.run()``. Every assertion is recomputed
from ``data/processed/q1_data.csv`` (frozen A2 input) and from A3's claimed
artifacts (``outputs/q1_solution.csv`` / ``q1_summary.json``), which are treated
as claims to falsify.

The LP-rebuild test re-formulates the optimisation from ``docs/model_spec.md``
independently (flat 721-vector, scipy/HiGHS) rather than reusing A3's PuLP model.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy.optimize import linprog

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_CSV = REPO_ROOT / "data" / "processed" / "q1_data.csv"
SOLUTION_CSV = REPO_ROOT / "outputs" / "q1_solution.csv"
SUMMARY_JSON = REPO_ROOT / "outputs" / "q1_summary.json"

N = 144
DT = 1.0 / 6.0
E0 = 6000.0
E_MIN, E_MAX = 1200.0, 10800.0
P_CH_MAX = P_DIS_MAX = 5000.0
ETA_CH = ETA_DIS = 0.90

TOL_KWH = 1e-8
TOL_KW = 1e-6
TOL_E = 1e-6
TOL_OBJ = 1e-4

ANCHORS = {1: "00:00-00:10", 61: "10:00-10:10", 73: "12:00-12:10", 85: "14:00-14:10",
           97: "16:00-16:10", 109: "18:00-18:10", 121: "20:00-20:10", 144: "23:50-24:00"}


# --------------------------------------------------------------------------
# loaders (missing artefacts -> FAIL, never skip)
# --------------------------------------------------------------------------
def _data() -> pd.DataFrame:
    assert DATA_CSV.exists(), f"缺少 A2 数据: {DATA_CSV}"
    return pd.read_csv(DATA_CSV, encoding="utf-8-sig")


def _sol() -> pd.DataFrame:
    assert SOLUTION_CSV.exists(), f"缺少 A3 结果: {SOLUTION_CSV}"
    return pd.read_csv(SOLUTION_CSV, encoding="utf-8-sig")


def _summ() -> dict:
    assert SUMMARY_JSON.exists(), f"缺少 A3 汇总: {SUMMARY_JSON}"
    return json.loads(SUMMARY_JSON.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# independence guard
# --------------------------------------------------------------------------
def test_a4_files_do_not_import_a3():
    """AST-level independence guard: no real import of / call into A3 code."""
    import ast

    forbidden_modules = {"src.model_q1", "src.solve_q1"}
    for f in [Path(__file__), REPO_ROOT / "src" / "audit_q1_independent.py"]:
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name not in forbidden_modules, f"{f.name} imports {alias.name}"
            elif isinstance(node, ast.ImportFrom):
                assert (node.module or "") not in forbidden_modules, f"{f.name} imports from {node.module}"
            elif isinstance(node, ast.Call):
                fn = node.func
                if isinstance(fn, ast.Name):
                    assert fn.id != "build_model", f"{f.name} calls build_model()"
                elif isinstance(fn, ast.Attribute):
                    assert not (fn.attr == "run" and isinstance(fn.value, ast.Name)
                                and fn.value.id == "solve_q1"), f"{f.name} calls solve_q1.run()"


# --------------------------------------------------------------------------
# 1. structure / mapping
# --------------------------------------------------------------------------
def test_data_and_solution_have_144_rows():
    assert len(_data()) == N
    assert len(_sol()) == N


def test_model_t_and_physical_interval_identical():
    d, s = _data(), _sol()
    assert d["model_t"].tolist() == list(range(1, N + 1))
    assert s["model_t"].tolist() == list(range(1, N + 1))
    assert s["physical_interval"].astype(str).tolist() == d["physical_interval"].astype(str).tolist()


def test_anchor_intervals():
    s = _sol().set_index("model_t")
    for t, lbl in ANCHORS.items():
        assert str(s.at[t, "physical_interval"]) == lbl


# --------------------------------------------------------------------------
# 2. inputs unchanged
# --------------------------------------------------------------------------
def test_input_columns_unchanged():
    d, s = _data(), _sol()
    for c in ("price_yuan_per_kwh", "load_kw", "pv_kw"):
        assert np.max(np.abs(d[c].to_numpy(float) - s[c].to_numpy(float))) <= 1e-12


# --------------------------------------------------------------------------
# 3. derived units / cost
# --------------------------------------------------------------------------
def test_kw_to_kwh():
    s = _sol()
    assert np.max(np.abs(s["grid_kw"].to_numpy(float) * DT - s["grid_kwh"])) <= TOL_KWH
    assert np.max(np.abs(s["charge_kw"].to_numpy(float) * DT - s["charge_kwh"])) <= TOL_KWH
    assert np.max(np.abs(s["discharge_kw"].to_numpy(float) * DT - s["discharge_kwh"])) <= TOL_KWH
    curt = (s["pv_kw"].to_numpy(float) - s["pv_used_kw"].to_numpy(float)) * DT
    assert np.max(np.abs(curt - s["curtailment_kwh"])) <= TOL_KWH


def test_interval_and_total_cost():
    s, sm = _sol(), _summ()
    expected = s["price_yuan_per_kwh"].to_numpy(float) * s["grid_kwh"].to_numpy(float)
    assert np.max(np.abs(expected - s["interval_cost_yuan"])) <= TOL_KWH
    total = float(np.sum(expected))
    assert abs(total - sm["objective_cost_yuan"]) <= TOL_OBJ


# --------------------------------------------------------------------------
# 4. constraints
# --------------------------------------------------------------------------
def test_power_balance():
    s = _sol()
    r = (s["grid_kw"] + s["pv_used_kw"] + s["discharge_kw"]
         - s["load_kw"] - s["charge_kw"]).to_numpy(float)
    assert np.max(np.abs(r)) <= TOL_KW


def test_pv_constraints_and_curtailment_identity():
    s = _sol()
    used, pv = s["pv_used_kw"].to_numpy(float), s["pv_kw"].to_numpy(float)
    assert used.min() >= -TOL_KW
    assert np.max(used - pv) <= TOL_KW
    assert s["curtailment_kw"].to_numpy(float).min() >= -TOL_KW
    assert np.max(np.abs((pv - used) - s["curtailment_kw"].to_numpy(float))) <= TOL_KW


def test_pv_energy_identity():
    s = _sol()
    avail = float(np.sum(s["pv_kw"]) * DT)
    used = float(np.sum(s["pv_used_kw"]) * DT)
    curt = float(np.sum(s["curtailment_kwh"]))
    assert abs(avail - used - curt) <= 1e-6


def test_storage_continuity():
    s = _sol()
    es, ee = s["energy_start_kwh"].to_numpy(float), s["energy_end_kwh"].to_numpy(float)
    assert np.max(np.abs(ee[:-1] - es[1:])) <= TOL_E


def test_storage_recursion():
    s = _sol()
    es, ee = s["energy_start_kwh"].to_numpy(float), s["energy_end_kwh"].to_numpy(float)
    ch, dis = s["charge_kw"].to_numpy(float), s["discharge_kw"].to_numpy(float)
    expected = es + ETA_CH * ch * DT - (dis / ETA_DIS) * DT
    assert np.max(np.abs(ee - expected)) <= TOL_E


def test_storage_bounds():
    s = _sol()
    es, ee = s["energy_start_kwh"].to_numpy(float), s["energy_end_kwh"].to_numpy(float)
    all_e = np.concatenate([es, [ee[-1]]])
    assert all_e.min() >= E_MIN - TOL_E
    assert all_e.max() <= E_MAX + TOL_E


def test_power_bounds_and_grid_nonnegative():
    s = _sol()
    assert s["charge_kw"].to_numpy(float).min() >= -TOL_KW
    assert s["charge_kw"].to_numpy(float).max() <= P_CH_MAX + TOL_KW
    assert s["discharge_kw"].to_numpy(float).min() >= -TOL_KW
    assert s["discharge_kw"].to_numpy(float).max() <= P_DIS_MAX + TOL_KW
    assert s["grid_kw"].to_numpy(float).min() >= -TOL_KW
    # grid has NO 5000 kW cap -> must not be asserted


def test_terminal_energy():
    s = _sol()
    es, ee = s["energy_start_kwh"].to_numpy(float), s["energy_end_kwh"].to_numpy(float)
    assert abs(es[0] - E0) <= TOL_E
    assert abs(ee[-1] - E0) <= TOL_E
    assert abs(ee[-1] - es[0]) <= TOL_E


def test_simultaneous_charge_discharge():
    s = _sol()
    ch, dis = s["charge_kw"].to_numpy(float), s["discharge_kw"].to_numpy(float)
    both = (ch > TOL_KW) & (dis > TOL_KW)
    assert int(both.sum()) == 0


# --------------------------------------------------------------------------
# 5. energy conservation
# --------------------------------------------------------------------------
def test_full_day_energy_balance():
    s = _sol()
    load = float(np.sum(s["load_kw"]) * DT)
    grid = float(np.sum(s["grid_kw"]) * DT)
    pv_used = float(np.sum(s["pv_used_kw"]) * DT)
    ch = float(np.sum(s["charge_kw"]) * DT)
    dis = float(np.sum(s["discharge_kw"]) * DT)
    assert abs((grid + pv_used + dis) - (load + ch)) <= 1e-4


def test_battery_net_energy_identity():
    s = _sol()
    ch = float(np.sum(s["charge_kw"]) * DT)
    dis = float(np.sum(s["discharge_kw"]) * DT)
    net = ETA_CH * ch - dis / ETA_DIS
    e_delta = float(s["energy_end_kwh"].iloc[-1] - s["energy_start_kwh"].iloc[0])
    assert abs(net - e_delta) <= 1e-4


# --------------------------------------------------------------------------
# 6. summary / blocks / key intervals / baseline
# --------------------------------------------------------------------------
def test_summary_reconciliation():
    s, sm = _sol(), _summ()
    pairs = {
        "objective_cost_yuan": float(np.sum(s["price_yuan_per_kwh"] * s["grid_kwh"])),
        "total_grid_energy_kwh": float(np.sum(s["grid_kw"]) * DT),
        "total_charge_energy_kwh": float(np.sum(s["charge_kw"]) * DT),
        "total_discharge_energy_kwh": float(np.sum(s["discharge_kw"]) * DT),
        "total_pv_available_kwh": float(np.sum(s["pv_kw"]) * DT),
        "total_pv_used_kwh": float(np.sum(s["pv_used_kw"]) * DT),
        "total_curtailment_kwh": float(np.sum(s["curtailment_kwh"])),
        "initial_energy_kwh": float(s["energy_start_kwh"].iloc[0]),
        "final_energy_kwh": float(s["energy_end_kwh"].iloc[-1]),
        "min_energy_kwh": float(min(s["energy_start_kwh"].min(), s["energy_end_kwh"].min())),
        "max_energy_kwh": float(max(s["energy_start_kwh"].max(), s["energy_end_kwh"].max())),
        "simultaneous_charge_discharge_count": 0,
    }
    for k, v in pairs.items():
        assert abs(v - float(sm[k])) <= 1e-6, k


def test_blocks_4h():
    s, sm = _sol(), _summ()
    for lbl, t0, t1 in [("00:00-04:00", 1, 24), ("04:00-08:00", 25, 48), ("08:00-12:00", 49, 72),
                        ("12:00-16:00", 73, 96), ("16:00-20:00", 97, 120), ("20:00-24:00", 121, 144)]:
        m = (s["model_t"] >= t0) & (s["model_t"] <= t1)
        a3b = next(b for b in sm["blocks_4h"] if b["block"] == lbl)
        assert abs(float(s.loc[m, "charge_kwh"].sum()) - a3b["charge_kwh_sum"]) <= 1e-6
        assert abs(float(s.loc[m, "discharge_kwh"].sum()) - a3b["discharge_kwh_sum"]) <= 1e-6
        assert abs(float(s.loc[m, "grid_kwh"].sum()) - a3b["grid_kwh_sum"]) <= 1e-6


def test_key_intervals():
    s, sm = _sol(), _summ()
    for t, lbl in [(61, "10:00-10:10"), (73, "12:00-12:10"), (85, "14:00-14:10"),
                   (97, "16:00-16:10"), (109, "18:00-18:10"), (121, "20:00-20:10")]:
        row = s.loc[s["model_t"] == t].iloc[0]
        assert str(row["physical_interval"]) == lbl
        a3k = next(k for k in sm["key_intervals"] if k["model_t"] == t)
        assert abs(float(row["grid_kwh"]) - a3k["grid_kwh"]) <= 1e-6


def test_baseline():
    d, s, sm = _data(), _sol(), _summ()
    load, pv = d["load_kw"].to_numpy(float), d["pv_kw"].to_numpy(float)
    price = d["price_yuan_per_kwh"].to_numpy(float)
    bl = np.maximum(load - pv, 0.0)
    cost = float(np.sum(price * bl * DT))
    assert abs(cost - sm["baseline_no_storage"]["baseline_cost_yuan"]) <= 1e-6
    saving = cost - float(np.sum(price * s["grid_kwh"].to_numpy(float)))
    assert abs(saving - sm["baseline_no_storage"]["saving_yuan"]) <= 1e-6


# --------------------------------------------------------------------------
# 7. independent LP optimality
# --------------------------------------------------------------------------
def test_independent_lp_optimal_objective():
    d = _data()
    price = d["price_yuan_per_kwh"].to_numpy(float)
    load = d["load_kw"].to_numpy(float)
    pv = d["pv_kw"].to_numpy(float)

    n = 4 * N + (N + 1)
    gi = lambda t: t - 1                                        # noqa: E731
    pi = lambda t: N + t - 1                                    # noqa: E731
    ci = lambda t: 2 * N + t - 1                                # noqa: E731
    di = lambda t: 3 * N + t - 1                                # noqa: E731
    ei = lambda k: 4 * N + k                                    # noqa: E731

    c = np.zeros(n)
    for t in range(1, N + 1):
        c[gi(t)] = price[t - 1] * DT

    A = np.zeros((2 * N + 2, n))
    b = np.zeros(2 * N + 2)
    r = 0
    for t in range(1, N + 1):
        A[r, gi(t)] = 1; A[r, pi(t)] = 1; A[r, di(t)] = 1; A[r, ci(t)] = -1
        b[r] = load[t - 1]; r += 1
    for t in range(1, N + 1):
        A[r, ei(t)] = 1; A[r, ei(t - 1)] = -1
        A[r, ci(t)] = -ETA_CH * DT; A[r, di(t)] = DT / ETA_DIS
        r += 1
    A[r, ei(0)] = 1; b[r] = E0; r += 1
    A[r, ei(N)] = 1; A[r, ei(0)] = -1; b[r] = 0.0; r += 1

    bounds = ([(0.0, None)] * N + [(0.0, float(pv[t])) for t in range(N)]
              + [(0.0, P_CH_MAX)] * N + [(0.0, P_DIS_MAX)] * N + [(E_MIN, E_MAX)] * (N + 1))

    res = linprog(c, A_eq=A, b_eq=b, bounds=bounds, method="highs")
    assert res.status == 0, res.message
    a3_obj = float(_summ()["objective_cost_yuan"])
    assert abs(res.fun - a3_obj) <= TOL_OBJ or abs(res.fun - a3_obj) / abs(res.fun) <= 1e-9


def test_a4_validation_json_exists_and_passes():
    p = REPO_ROOT / "outputs" / "a4_validation.json"
    assert p.exists(), "缺少 outputs/a4_validation.json"
    v = json.loads(p.read_text(encoding="utf-8"))
    assert v["status"] == "PASS"
    assert v["artifact_validation_pass"] is True
    assert v["independent_optimal_match"] is True
    assert v["findings"]["critical"] == []
    assert v["findings"]["major"] == []
