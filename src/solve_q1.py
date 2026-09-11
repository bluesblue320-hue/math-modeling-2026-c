# -*- coding: utf-8 -*-
"""
A3 Optimization Agent — Problem 1 确定性 LP 求解、验证与标准化输出。

职责边界（AGENTS.md 第 4 节 Scope；A3 任务书 §16）：
  * 读取 data/processed/q1_data.csv（A2 冻结的唯一数据输入）。
  * 执行 A2 前置 Gate 与时间映射 Gate。
  * 调用 src/model_q1.py 构建 LP，用 Solver 求解，检查 Solver Status。
  * 提取变量、计算派生量、执行基础内部验证（A3 §21–§31）。
  * 输出 outputs/q1_solution.csv / q1_solution.xlsx / q1_summary.json。
  * 不生成官方 result1.xlsx，不写论文，不处理问题 2/3/4。

严格禁止：重新读取原始 Excel、重新解析 source_label、做任何 interpolation /
resample / shift / sort / 时间重建 / 时间平移；修改时间映射；修改数学模型。

运行：  python src/solve_q1.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import pulp

# 允许以脚本方式直接运行
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.model_q1 import (  # noqa: E402
    DELTA_T,
    E_INIT,
    E_MAX,
    E_MIN,
    N_PERIODS,
    P_CH_MAX,
    P_DIS_MAX,
    TOL,
    apply_secondary_min_throughput,
    build_model,
)

# --------------------------------------------------------------------------
# 路径（均相对仓库根，产物不含本机绝对路径）
# --------------------------------------------------------------------------
REPO_ROOT = _REPO_ROOT
DATA_CSV = REPO_ROOT / "data" / "processed" / "q1_data.csv"
A2_JSON = REPO_ROOT / "outputs" / "a2_validation.json"
TIME_MAPPING_MD = REPO_ROOT / "docs" / "time_mapping_decision.md"
OUT_CSV = REPO_ROOT / "outputs" / "q1_solution.csv"
OUT_XLSX = REPO_ROOT / "outputs" / "q1_solution.xlsx"
OUT_JSON = REPO_ROOT / "outputs" / "q1_summary.json"

# 数值处理容差
CLAMP_TOL: float = 1e-9           # 展示层：把 |v|≤1e-9 的 Solver 浮点噪声归零
SIMULTANEOUS_TOL: float = 1e-6    # 同时充放电判定容差（A3 §29）
RESIDUAL_TOL: float = 1e-6        # 平衡/递推/边界校验容差（A3 §21–§25）
OBJ_TOL: float = 1e-6             # 费用复算容差（A3 §28）
EPS_COST: float = 1e-6            # 第二阶段费用允许偏差（元）

# 题目表 1 六个关键时段（A3 §33；只引用 model_t，不重新解释）
KEY_INTERVALS: list[tuple[int, str]] = [
    (61, "10:00-10:10"),
    (73, "12:00-12:10"),
    (85, "14:00-14:10"),
    (97, "16:00-16:10"),
    (109, "18:00-18:10"),
    (121, "20:00-20:10"),
]

# 题目表 2 六个 4 h 汇总块（model_spec.md §8）
BLOCKS_4H: list[tuple[str, int, int]] = [
    ("00:00-04:00", 1, 24),
    ("04:00-08:00", 25, 48),
    ("08:00-12:00", 49, 72),
    ("12:00-16:00", 73, 96),
    ("16:00-20:00", 97, 120),
    ("20:00-24:00", 121, 144),
]

SOLUTION_COLUMNS = [
    "model_t",
    "physical_interval",
    "price_yuan_per_kwh",
    "load_kw",
    "pv_kw",
    "grid_kw",
    "grid_kwh",
    "pv_used_kw",
    "curtailment_kw",
    "curtailment_kwh",
    "charge_kw",
    "charge_kwh",
    "discharge_kw",
    "discharge_kwh",
    "energy_start_kwh",
    "energy_end_kwh",
    "interval_cost_yuan",
]


# ==========================================================================
# 0. 前置 Gate
# ==========================================================================
class GateError(RuntimeError):
    """前置 Gate 未通过。"""


def check_time_mapping_gate() -> dict[str, Any]:
    """校验 docs/time_mapping_decision.md 为 DECIDED / BLOCK_A2 FALSE / Mapping A。"""
    if not TIME_MAPPING_MD.exists():
        raise GateError(f"找不到时间映射决策文件: {TIME_MAPPING_MD}")
    text = TIME_MAPPING_MD.read_text(encoding="utf-8")
    checks = {
        "status_decided": "STATUS: DECIDED" in text,
        "block_a2_false": "BLOCK_A2: FALSE" in text,
        "mapping_a": "Mapping A" in text,
    }
    if not all(checks.values()):
        raise GateError(f"时间映射 Gate 未通过: {checks}")
    return checks


def check_a2_gate() -> dict[str, Any]:
    """读取 outputs/a2_validation.json 并校验 A3 §2 要求的全部字段。"""
    if not A2_JSON.exists():
        raise GateError(f"找不到 A2 验证文件: {A2_JSON}")
    with open(A2_JSON, "r", encoding="utf-8") as f:
        a2 = json.load(f)

    required: dict[str, Any] = {
        "status": "PASS",
        "rows": N_PERIODS,
        "missing_values": 0,
        "duplicate_model_t": 0,
        "duplicate_intervals": 0,
        "time_step_minutes": 10,
        "mapping": "RIGHT_ENDPOINT",
        "full_day_covered": True,
        "first_model_t": 1,
        "last_model_t": N_PERIODS,
        "first_interval": "00:00-00:10",
        "last_interval": "23:50-24:00",
    }
    bad: dict[str, tuple[Any, Any]] = {}
    for key, expected in required.items():
        actual = a2.get(key)
        if actual != expected:
            bad[key] = (expected, actual)
    if bad:
        raise GateError(f"A2 验证 Gate 未通过，字段不符: {bad}")
    return a2


def check_data_gate(df: pd.DataFrame) -> None:
    """校验 q1_data.csv 结构，并确认 model_t=61 ↔ 10:00-10:10。"""
    if len(df) != N_PERIODS:
        raise GateError(f"q1_data.csv 行数应为 {N_PERIODS}，实际 {len(df)}")
    if df["model_t"].tolist() != list(range(1, N_PERIODS + 1)):
        raise GateError("q1_data.csv 的 model_t 非严格 1..144")
    r61 = df[df["model_t"] == 61]
    if len(r61) != 1 or str(r61.iloc[0]["physical_interval"]) != "10:00-10:10":
        raise GateError("model_t=61 未对应 10:00-10:10")
    if int(df[["price_yuan_per_kwh", "load_kw", "pv_kw"]].isna().sum().sum()) != 0:
        raise GateError("q1_data.csv 存在缺失值")


def load_data() -> pd.DataFrame:
    df = pd.read_csv(DATA_CSV, encoding="utf-8-sig")
    check_data_gate(df)
    return df


# ==========================================================================
# 1. 求解
# ==========================================================================
def _cbc_version() -> str:
    """尽力获取 CBC 版本；失败则返回 'unknown'。"""
    try:
        cmd = pulp.PULP_CBC_CMD(msg=False)
        exe = getattr(cmd, "path", None)
        if exe and Path(exe).exists():
            out = subprocess.run(
                [exe, "-version"], capture_output=True, text=True, timeout=20
            )
            text = (out.stdout or "") + (out.stderr or "")
            for line in text.splitlines():
                if "Version" in line or "version" in line:
                    return line.strip()
    except Exception:  # pragma: no cover - 版本探测失败不影响求解
        pass
    return "unknown"


def _highs_version() -> str:
    """尽力获取 HiGHS 版本；失败则返回 'unknown'。"""
    try:
        import highspy  # noqa: PLC0415

        h = highspy.Highs()
        v = h.version()
        if isinstance(v, (tuple, list)):
            return ".".join(str(x) for x in v)
        return str(v)
    except Exception:  # pragma: no cover
        return "unknown"


PRIMARY_SOLVER = "highs"      # 主求解器：PuLP + HiGHS（full double precision）
CROSSCHECK_SOLVER = "cbc"     # 交叉校验求解器：PuLP + CBC


def _make_solver(name: str):
    if name == "highs":
        return pulp.HiGHS(msg=False)
    if name == "cbc":
        return pulp.PULP_CBC_CMD(msg=False)
    raise ValueError(f"未知求解器: {name}")


def solve_stage(bundle, *, stage_label: str) -> tuple[str, str]:
    """用主求解器（HiGHS）求解给定模型，返回 (pulp_status_text, solver_name)。

    仅当 Solver Status == Optimal 才继续；否则按 A3 §17 立即停止。
    """
    solver = _make_solver(PRIMARY_SOLVER)
    bundle.prob.solve(solver)
    status_text = pulp.LpStatus.get(bundle.prob.status, str(bundle.prob.status))
    if status_text != "Optimal":
        raise RuntimeError(
            f"[{stage_label}] Solver Status = {status_text}（非 Optimal），"
            f"按 A3 §17 立即停止，不生成结果。"
        )
    return status_text, "PULP_HiGHS (HiGHS)"


def crosscheck_with_cbc(prices, loads, pv) -> dict[str, Any]:
    """用独立求解器 CBC 复核最优值（A3 §15 / model_spec §9.4 多重最优解检查）。"""
    out: dict[str, Any] = {"solver": "PULP_CBC_CMD (COIN-OR CBC)"}
    try:
        b = build_model(prices, loads, pv)
        b.prob.solve(_make_solver("cbc"))
        out["status"] = pulp.LpStatus.get(b.prob.status, str(b.prob.status))
        out["objective_cost_yuan"] = float(pulp.value(b.cost_expr))
    except Exception as exc:  # pragma: no cover - 交叉校验失败不影响主结果
        out["status"] = "unavailable"
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


# ==========================================================================
# 2. 变量提取与派生量
# ==========================================================================
def _val(v: pulp.LpVariable) -> float:
    return float(v.value()) if v.value() is not None else 0.0


def _clamp(v: float) -> float:
    """把 |v| ≤ CLAMP_TOL 的 Solver 浮点噪声归零（展示层）。"""
    return 0.0 if abs(v) <= CLAMP_TOL else v


def extract_solution(df: pd.DataFrame, bundle) -> dict[str, list[float]]:
    prices = df["price_yuan_per_kwh"].astype(float).tolist()
    loads = df["load_kw"].astype(float).tolist()
    pv = df["pv_kw"].astype(float).tolist()

    grid_raw = [_val(bundle.p_grid[t]) for t in range(1, N_PERIODS + 1)]
    pv_use = [_clamp(_val(bundle.p_pv_use[t])) for t in range(1, N_PERIODS + 1)]
    ch = [_clamp(_val(bundle.p_ch[t])) for t in range(1, N_PERIODS + 1)]
    dis = [_clamp(_val(bundle.p_dis[t])) for t in range(1, N_PERIODS + 1)]
    energy = [_clamp(_val(bundle.energy[s])) for s in range(0, N_PERIODS + 1)]

    grid = [_clamp(g) for g in grid_raw]

    grid_kwh = [g * DELTA_T for g in grid]
    ch_kwh = [c * DELTA_T for c in ch]
    dis_kwh = [d * DELTA_T for d in dis]
    curt_kw = [pv[i] - pv_use[i] for i in range(N_PERIODS)]
    curt_kwh = [c * DELTA_T for c in curt_kw]
    cost = [prices[i] * grid_kwh[i] for i in range(N_PERIODS)]

    return {
        "prices": prices,
        "loads": loads,
        "pv": pv,
        "grid_raw": grid_raw,
        "grid": grid,
        "pv_use": pv_use,
        "ch": ch,
        "dis": dis,
        "energy": energy,
        "grid_kwh": grid_kwh,
        "ch_kwh": ch_kwh,
        "dis_kwh": dis_kwh,
        "curt_kw": curt_kw,
        "curt_kwh": curt_kwh,
        "cost": cost,
    }


# ==========================================================================
# 3. 内部验证（A3 §21–§31、§26–§28）
# ==========================================================================
def run_validation(df: pd.DataFrame, sol: dict[str, list[float]], solver_objective: float) -> dict[str, Any]:
    intervals = df["physical_interval"].astype(str).tolist()
    loads, pv = sol["loads"], sol["pv"]
    grid, pv_use, ch, dis, energy = sol["grid"], sol["pv_use"], sol["ch"], sol["dis"], sol["energy"]

    # §21 功率平衡独立复算
    balance_res = [
        grid[t] + pv_use[t] + dis[t] - loads[t] - ch[t] for t in range(N_PERIODS)
    ]
    max_abs_balance = max(abs(r) for r in balance_res)

    # §22 储能递推独立复算
    rec_res = []
    for t in range(N_PERIODS):
        expected = energy[t] + 0.9 * ch[t] * DELTA_T - (dis[t] / 0.9) * DELTA_T
        rec_res.append(energy[t + 1] - expected)
    max_abs_rec = max(abs(r) for r in rec_res)

    # §23 储能边界
    min_energy = min(energy)
    max_energy = max(energy)
    energy_bounds_ok = (min_energy >= E_MIN - RESIDUAL_TOL) and (max_energy <= E_MAX + RESIDUAL_TOL)

    # §24 首尾状态
    terminal_error = abs(energy[N_PERIODS] - E_INIT)
    e0_ok = abs(energy[0] - E_INIT) <= RESIDUAL_TOL

    # §25 充放电功率
    max_charge = max(ch)
    max_discharge = max(dis)
    charge_bounds_ok = all(-RESIDUAL_TOL <= c <= P_CH_MAX + RESIDUAL_TOL for c in ch)
    discharge_bounds_ok = all(-RESIDUAL_TOL <= d <= P_DIS_MAX + RESIDUAL_TOL for d in dis)

    # §26 光伏
    pv_bounds_ok = all(-RESIDUAL_TOL <= pv_use[i] <= pv[i] + RESIDUAL_TOL for i in range(N_PERIODS))
    curt_nonneg_ok = all(c >= -RESIDUAL_TOL for c in sol["curt_kw"])

    # §27 外网购电
    min_grid_raw = min(sol["grid_raw"])
    negative_grid_raw_count = sum(1 for g in sol["grid_raw"] if g < 0.0)
    grid_nonneg_ok = min_grid_raw >= -RESIDUAL_TOL

    # §28 费用独立复算
    cost_recomputed = sum(sol["cost"])
    obj_abs_diff = abs(solver_objective - cost_recomputed)

    # §29 同时充放电
    simultaneous_idx = [
        t for t in range(N_PERIODS)
        if ch[t] > SIMULTANEOUS_TOL and dis[t] > SIMULTANEOUS_TOL
    ]
    max_sim = max((min(ch[t], dis[t]) for t in simultaneous_idx), default=0.0)

    checks = {
        "power_balance": max_abs_balance <= RESIDUAL_TOL,
        "energy_recursion": max_abs_rec <= RESIDUAL_TOL,
        "energy_bounds": energy_bounds_ok,
        "initial_energy": e0_ok,
        "terminal_energy": terminal_error <= RESIDUAL_TOL,
        "charge_bounds": charge_bounds_ok,
        "discharge_bounds": discharge_bounds_ok,
        "pv_bounds": pv_bounds_ok,
        "curtailment_nonneg": curt_nonneg_ok,
        "grid_nonneg": grid_nonneg_ok,
        "objective_recompute": obj_abs_diff <= OBJ_TOL,
    }

    return {
        "max_power_balance_residual_kw": max_abs_balance,
        "max_energy_recursion_residual_kwh": max_abs_rec,
        "terminal_energy_error_kwh": terminal_error,
        "energy_start_kwh": energy[0],
        "energy_end_kwh": energy[N_PERIODS],
        "min_energy_kwh": min_energy,
        "max_energy_kwh": max_energy,
        "max_charge_kw": max_charge,
        "max_discharge_kw": max_discharge,
        "max_grid_kw": max(grid),
        "min_grid_kw_raw": min_grid_raw,
        "negative_grid_raw_count": negative_grid_raw_count,
        "objective_recomputed_yuan": cost_recomputed,
        "objective_abs_diff_yuan": obj_abs_diff,
        "simultaneous_charge_discharge_count": len(simultaneous_idx),
        "simultaneous_model_t": [t + 1 for t in simultaneous_idx],
        "max_simultaneous_kw": max_sim,
        "checks": checks,
        "all_checks_pass": all(checks.values()),
        "tolerances": {
            "residual_tol": RESIDUAL_TOL,
            "simultaneous_tol": SIMULTANEOUS_TOL,
            "objective_tol": OBJ_TOL,
            "clamp_tol": CLAMP_TOL,
        },
    }


# ==========================================================================
# 4. 汇总 / Baseline
# ==========================================================================
def build_blocks(sol: dict[str, list[float]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for label, t0, t1 in BLOCKS_4H:
        i0, i1 = t0 - 1, t1  # 0-based 切片 [i0, i1)
        out.append({
            "block": label,
            "model_t_start": t0,
            "model_t_end": t1,
            "charge_kwh_sum": sum(sol["ch_kwh"][i0:i1]),
            "discharge_kwh_sum": sum(sol["dis_kwh"][i0:i1]),
            "grid_kwh_sum": sum(sol["grid_kwh"][i0:i1]),
        })
    return out


def build_key_intervals(df: pd.DataFrame, sol: dict[str, list[float]]) -> list[dict[str, Any]]:
    interval_map = {int(df.iloc[i]["model_t"]): str(df.iloc[i]["physical_interval"]) for i in range(len(df))}
    out: list[dict[str, Any]] = []
    for t, label in KEY_INTERVALS:
        i = t - 1
        out.append({
            "model_t": t,
            "physical_interval": interval_map[t],
            "expected_interval": label,
            "grid_kw": sol["grid"][i],
            "grid_kwh": sol["grid_kwh"][i],
        })
    return out


def compute_baseline(df: pd.DataFrame) -> dict[str, Any]:
    """No-Storage Baseline（A3 §32）：P_ch = P_dis = 0，允许弃光。仅用于解释，不进入优化目标。"""
    prices = df["price_yuan_per_kwh"].astype(float).tolist()
    loads = df["load_kw"].astype(float).tolist()
    pv = df["pv_kw"].astype(float).tolist()
    grid_kw = [max(loads[i] - pv[i], 0.0) for i in range(N_PERIODS)]
    grid_kwh = [g * DELTA_T for g in grid_kw]
    cost = sum(prices[i] * grid_kwh[i] for i in range(N_PERIODS))
    return {
        "description": "No-storage baseline: P_ch=0, P_dis=0, curtailment allowed",
        "baseline_grid_kwh": grid_kwh,
        "baseline_cost_yuan": cost,
        "total_baseline_grid_energy_kwh": sum(grid_kwh),
    }


# ==========================================================================
# 5. 输出
# ==========================================================================
def build_solution_dataframe(df: pd.DataFrame, sol: dict[str, list[float]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for i in range(N_PERIODS):
        rows.append({
            "model_t": int(df.iloc[i]["model_t"]),
            "physical_interval": str(df.iloc[i]["physical_interval"]),
            "price_yuan_per_kwh": sol["prices"][i],
            "load_kw": sol["loads"][i],
            "pv_kw": sol["pv"][i],
            "grid_kw": sol["grid"][i],
            "grid_kwh": sol["grid_kwh"][i],
            "pv_used_kw": sol["pv_use"][i],
            "curtailment_kw": sol["curt_kw"][i],
            "curtailment_kwh": sol["curt_kwh"][i],
            "charge_kw": sol["ch"][i],
            "charge_kwh": sol["ch_kwh"][i],
            "discharge_kw": sol["dis"][i],
            "discharge_kwh": sol["dis_kwh"][i],
            "energy_start_kwh": sol["energy"][i],
            "energy_end_kwh": sol["energy"][i + 1],
            "interval_cost_yuan": sol["cost"][i],
        })
    return pd.DataFrame(rows, columns=SOLUTION_COLUMNS)


def write_outputs(
    solution_df: pd.DataFrame,
    summary: dict[str, Any],
    baseline: dict[str, Any],
) -> None:
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    solution_df.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")

    # Excel：solution + summary 两个 sheet（内部检查用，非官方 result1.xlsx）
    summary_rows = [
        ("status", summary["status"]),
        ("solver", summary["solver"]),
        ("solver_status", summary["solver_status"]),
        ("objective_cost_yuan", summary["objective_cost_yuan"]),
        ("total_grid_energy_kwh", summary["total_grid_energy_kwh"]),
        ("total_charge_energy_kwh", summary["total_charge_energy_kwh"]),
        ("total_discharge_energy_kwh", summary["total_discharge_energy_kwh"]),
        ("total_pv_available_kwh", summary["total_pv_available_kwh"]),
        ("total_pv_used_kwh", summary["total_pv_used_kwh"]),
        ("total_curtailment_kwh", summary["total_curtailment_kwh"]),
        ("initial_energy_kwh", summary["initial_energy_kwh"]),
        ("final_energy_kwh", summary["final_energy_kwh"]),
        ("min_energy_kwh", summary["min_energy_kwh"]),
        ("max_energy_kwh", summary["max_energy_kwh"]),
        ("max_grid_kw", summary["max_grid_kw"]),
        ("max_charge_kw", summary["max_charge_kw"]),
        ("max_discharge_kw", summary["max_discharge_kw"]),
        ("max_power_balance_residual_kw", summary["max_power_balance_residual_kw"]),
        ("max_energy_recursion_residual_kwh", summary["max_energy_recursion_residual_kwh"]),
        ("terminal_energy_error_kwh", summary["terminal_energy_error_kwh"]),
        ("simultaneous_charge_discharge_count", summary["simultaneous_charge_discharge_count"]),
        ("max_simultaneous_kw", summary["max_simultaneous_kw"]),
        ("secondary_optimization_used", summary["secondary_optimization_used"]),
        ("baseline_cost_yuan", baseline["baseline_cost_yuan"]),
        ("saving_yuan", summary["baseline_no_storage"]["saving_yuan"]),
        ("saving_rate", summary["baseline_no_storage"]["saving_rate"]),
    ]
    summary_df = pd.DataFrame(summary_rows, columns=["metric", "value"])
    blocks_df = pd.DataFrame(summary["blocks_4h"])
    key_df = pd.DataFrame(summary["key_intervals"])

    with pd.ExcelWriter(OUT_XLSX, engine="openpyxl") as writer:
        solution_df.to_excel(writer, sheet_name="solution", index=False)
        summary_df.to_excel(writer, sheet_name="summary", index=False)
        blocks_df.to_excel(writer, sheet_name="blocks_4h", index=False)
        key_df.to_excel(writer, sheet_name="key_intervals", index=False)

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)


# ==========================================================================
# 6. 主流程
# ==========================================================================
def run(print_summary: bool = True) -> dict[str, Any]:
    # --- Gate ---
    check_time_mapping_gate()
    check_a2_gate()
    df = load_data()

    prices = df["price_yuan_per_kwh"].astype(float).tolist()
    loads = df["load_kw"].astype(float).tolist()
    pv = df["pv_kw"].astype(float).tolist()

    # --- Stage 1: 原 LP ---
    bundle = build_model(prices, loads, pv)
    solver_status, solver_name = solve_stage(bundle, stage_label="stage1")
    c_star = float(pulp.value(bundle.cost_expr))
    throughput_stage1 = float(pulp.value(bundle.throughput_expr))

    sol = extract_solution(df, bundle)
    validation = run_validation(df, sol, c_star)

    # --- 独立求解器交叉校验（CBC）---
    crosscheck = crosscheck_with_cbc(prices, loads, pv)
    if crosscheck.get("status") == "Optimal":
        crosscheck["objective_abs_diff_yuan"] = abs(
            crosscheck["objective_cost_yuan"] - c_star
        )
        crosscheck["objective_rel_diff"] = (
            crosscheck["objective_abs_diff_yuan"] / abs(c_star) if c_star else 0.0
        )

    # --- Stage 2（仅当出现显著同时充放电，A3 §31 方案 B） ---
    secondary_used = False
    secondary_info: dict[str, Any] = {"triggered": False}
    if validation["simultaneous_charge_discharge_count"] > 0:
        secondary_info = {
            "triggered": True,
            "method": "two_stage_min_throughput (model_spec §7 方案 B)",
            "c_star": c_star,
            "eps_cost": EPS_COST,
            "throughput_before_kwh": throughput_stage1,
        }
        apply_secondary_min_throughput(bundle, c_star, EPS_COST)
        solver_status, solver_name = solve_stage(bundle, stage_label="stage2")
        c_second = float(pulp.value(bundle.cost_expr))
        throughput_stage2 = float(pulp.value(bundle.throughput_expr))
        if abs(c_second - c_star) > max(EPS_COST, 1e-3):
            raise RuntimeError(
                f"第二阶段购电费用 {c_second} 偏离第一阶段 {c_star}，超出容差，按 A3 §31 停止。"
            )
        secondary_info.update({
            "c_second": c_second,
            "cost_diff": abs(c_second - c_star),
            "throughput_after_kwh": throughput_stage2,
            "throughput_reduction_kwh": throughput_stage1 - throughput_stage2,
        })
        # 重新提取与验证
        sol = extract_solution(df, bundle)
        validation = run_validation(df, sol, c_star)
        secondary_used = True
        if validation["simultaneous_charge_discharge_count"] > 0:
            raise RuntimeError("第二阶段后仍存在同时充放电，需按 A3 §31 进一步处理（升级 MILP）。")

    # --- 汇总指标 ---
    total_grid = sum(sol["grid_kwh"])
    total_charge = sum(sol["ch_kwh"])
    total_discharge = sum(sol["dis_kwh"])
    total_pv_avail = sum(sol["pv"]) * DELTA_T
    total_pv_used = sum(sol["pv_use"]) * DELTA_T
    total_curt = sum(sol["curt_kwh"])

    baseline = compute_baseline(df)
    baseline_cost = baseline["baseline_cost_yuan"]
    saving = baseline_cost - c_star
    saving_rate = saving / baseline_cost if baseline_cost != 0 else 0.0

    blocks = build_blocks(sol)
    key_intervals = build_key_intervals(df, sol)

    summary: dict[str, Any] = {
        "status": "OPTIMAL",
        "solver": solver_name,
        "solver_version": f"HiGHS {_highs_version()}",
        "solver_status": solver_status,
        "solver_versions": {
            "primary": f"PULP_HiGHS / HiGHS {_highs_version()}",
            "cbc_crosscheck": f"COIN-OR CBC {_cbc_version()}",
            "pulp": pulp.__version__,
        },
        "crosscheck_cbc": crosscheck,
        "pulp_version": pulp.__version__,
        "objective_cost_yuan": c_star,
        "total_grid_energy_kwh": total_grid,
        "total_charge_energy_kwh": total_charge,
        "total_discharge_energy_kwh": total_discharge,
        "total_pv_available_kwh": total_pv_avail,
        "total_pv_used_kwh": total_pv_used,
        "total_curtailment_kwh": total_curt,
        "initial_energy_kwh": E_INIT,
        "final_energy_kwh": sol["energy"][N_PERIODS],
        "min_energy_kwh": validation["min_energy_kwh"],
        "max_energy_kwh": validation["max_energy_kwh"],
        "max_charge_kw": validation["max_charge_kw"],
        "max_discharge_kw": validation["max_discharge_kw"],
        "max_grid_kw": validation["max_grid_kw"],
        "max_power_balance_residual_kw": validation["max_power_balance_residual_kw"],
        "max_energy_recursion_residual_kwh": validation["max_energy_recursion_residual_kwh"],
        "terminal_energy_error_kwh": validation["terminal_energy_error_kwh"],
        "simultaneous_charge_discharge_count": validation["simultaneous_charge_discharge_count"],
        "max_simultaneous_kw": validation["max_simultaneous_kw"],
        "secondary_optimization_used": secondary_used,
        "secondary_optimization": secondary_info,
        "objective_recomputed_yuan": validation["objective_recomputed_yuan"],
        "objective_abs_diff_yuan": validation["objective_abs_diff_yuan"],
        "min_grid_kw_raw": validation["min_grid_kw_raw"],
        "negative_grid_raw_count": validation["negative_grid_raw_count"],
        "simultaneous_model_t": validation["simultaneous_model_t"],
        "tolerances": validation["tolerances"],
        "delta_t_hours": DELTA_T,
        "n_periods": N_PERIODS,
        "mapping": "Mapping A (source label = interval end); RIGHT_ENDPOINT",
        "validation_checks": validation["checks"],
        "validation_all_pass": validation["all_checks_pass"],
        "baseline_no_storage": {
            "baseline_cost_yuan": baseline_cost,
            "total_baseline_grid_energy_kwh": baseline["total_baseline_grid_energy_kwh"],
            "optimized_cost_yuan": c_star,
            "saving_yuan": saving,
            "saving_rate": saving_rate,
        },
        "blocks_4h": blocks,
        "key_intervals": key_intervals,
    }

    solution_df = build_solution_dataframe(df, sol)
    write_outputs(solution_df, summary, baseline)

    if print_summary:
        _print_summary(summary, solution_df)

    if not validation["all_checks_pass"]:
        raise RuntimeError(f"A3 内部验证未全部通过: {validation['checks']}")

    return summary


def _print_summary(summary: dict[str, Any], solution_df: pd.DataFrame) -> None:
    b = summary["baseline_no_storage"]
    print("=" * 72)
    print(f"A3 OPTIMIZATION STATUS: {'PASS' if summary['validation_all_pass'] else 'FAIL'}")
    print("=" * 72)
    print(f"Solver            : {summary['solver']} ({summary['solver_version']})")
    print(f"Solver Status     : {summary['solver_status']}")
    print(f"Objective Cost    : {summary['objective_cost_yuan']:.6f} yuan")
    print(f"Total Grid Energy : {summary['total_grid_energy_kwh']:.6f} kWh")
    print(f"Total Charge      : {summary['total_charge_energy_kwh']:.6f} kWh")
    print(f"Total Discharge   : {summary['total_discharge_energy_kwh']:.6f} kWh")
    print(f"PV avail/used/curt: {summary['total_pv_available_kwh']:.3f} / "
          f"{summary['total_pv_used_kwh']:.3f} / {summary['total_curtailment_kwh']:.3f} kWh")
    print(f"E0/E144           : {summary['initial_energy_kwh']:.3f} / {summary['final_energy_kwh']:.3f} kWh")
    print(f"E min/max         : {summary['min_energy_kwh']:.3f} / {summary['max_energy_kwh']:.3f} kWh")
    print(f"max grid/ch/dis   : {summary['max_grid_kw']:.3f} / "
          f"{summary['max_charge_kw']:.3f} / {summary['max_discharge_kw']:.3f} kW")
    print(f"max balance resid : {summary['max_power_balance_residual_kw']:.3e} kW")
    print(f"max recursion res : {summary['max_energy_recursion_residual_kwh']:.3e} kWh")
    print(f"terminal E error  : {summary['terminal_energy_error_kwh']:.3e} kWh")
    print(f"simultaneous count: {summary['simultaneous_charge_discharge_count']} "
          f"(max {summary['max_simultaneous_kw']:.3e} kW)")
    print(f"secondary opt used: {summary['secondary_optimization_used']}")
    print(f"Baseline cost     : {b['baseline_cost_yuan']:.6f} yuan")
    print(f"Saving            : {b['saving_yuan']:.6f} yuan ({b['saving_rate']*100:.4f} %)")
    print("-" * 72)
    print("Key intervals (grid_kwh):")
    for k in summary["key_intervals"]:
        print(f"  t={k['model_t']:>3} {k['physical_interval']}: {k['grid_kwh']:.6f} kWh")
    print("-" * 72)
    print(f"solution rows     : {len(solution_df)}")
    print(f"checks            : {summary['validation_checks']}")
    print("=" * 72)


if __name__ == "__main__":
    try:
        run()
    except (GateError, RuntimeError) as exc:
        print(f"\nA3 STATUS: FAIL / BLOCKED\nReason: {exc}")
        sys.exit(1)
