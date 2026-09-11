# -*- coding: utf-8 -*-
"""
A3 Optimization Agent — Problem 1 确定性 LP 模型定义。

职责边界（AGENTS.md 第 4 节 Scope；A3 任务书 §16）：
  * 只负责：定义模型参数、创建 LP、创建变量、添加目标函数、添加全部约束、
    返回 model 与 variables。
  * 不负责：读取数据、求解、写结果文件、解释题目、修改时间映射。

严格实现唯一事实源 ``docs/model_spec.md``（不得改动数学模型）：

  目标      min C_buy = Σ_t c_t · P_grid_t · Δt                （含 Δt = 1/6）
  功率平衡  P_grid_t + P_pv_use_t + P_dis_t = P_load_t + P_ch_t  （逐时段等式 C1）
  光伏利用  0 ≤ P_pv_use_t ≤ P_PV_t                              （允许弃光 C2）
  储能递推  E_t = E_{t-1} + η_ch·P_ch_t·Δt − (P_dis_t/η_dis)·Δt （含 Δt，C3）
  初值      E_0 = 6000                                            （C4）
  首尾相等  E_144 = E_0                                           （C5）
  电量范围  1200 ≤ E_t ≤ 10800，t = 0..144                        （C6）
  充电上限  0 ≤ P_ch_t  ≤ 5000                                    （C7）
  放电上限  0 ≤ P_dis_t ≤ 5000                                    （C8）
  禁止售电  P_grid_t ≥ 0                                          （C9）

问题 1 主模型为 **LP**：不得引入 0-1 变量、电池退化成本、售电收益、
紧急购电、5 倍电价、违约费用或任何问题 2/3/4 机制。

可选 C10（购电功率数值平凡上界）默认**不启用**（A3 任务书 §14）。
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Sequence

import pulp

# --------------------------------------------------------------------------
# 模型常量（源自 Source of Truth，允许 hardcode；不得修改数值）
# --------------------------------------------------------------------------
N_PERIODS: int = 144              # 一天 144 个 10 min 时段（model_spec.md §1）
DELTA_T: float = 1.0 / 6.0        # Δt = 10 min = 1/6 h（invariant）
E_CAPACITY: float = 12000.0       # 设备容量 kWh（附录 1；不替代运行上限）
E_MIN: float = 1200.0             # 运行电量下限 kWh（C6）
E_MAX: float = 10800.0            # 运行电量上限 kWh（C6）
E_INIT: float = 6000.0            # 初始电量 kWh（C4）
P_CH_MAX: float = 5000.0          # 最大充电功率 kW（C7）
P_DIS_MAX: float = 5000.0         # 最大放电功率 kW（C8）
ETA_CH: float = 0.90              # 充电效率（H3 解释假设）
ETA_DIS: float = 0.90             # 放电效率（H3 解释假设）
TOL: float = 1e-6                 # 统一数值容差（H12，判定/校验用）


@dataclass
class ModelBundle:
    """LP 模型与其变量、关键表达式的集合。"""

    prob: pulp.LpProblem
    p_grid: dict[int, pulp.LpVariable]
    p_pv_use: dict[int, pulp.LpVariable]
    p_ch: dict[int, pulp.LpVariable]
    p_dis: dict[int, pulp.LpVariable]
    energy: dict[int, pulp.LpVariable]        # 索引 0..144（145 个状态边界）
    cost_expr: pulp.LpAffineExpression        # C_buy = Σ c_t·P_grid_t·Δt
    throughput_expr: pulp.LpAffineExpression  # Σ (P_ch_t + P_dis_t)·Δt
    eta_ch: float = ETA_CH
    eta_dis: float = ETA_DIS


def _check_input(prices: Sequence[float], loads: Sequence[float], pv: Sequence[float]) -> None:
    for name, seq in (("prices", prices), ("loads", loads), ("pv", pv)):
        if len(seq) != N_PERIODS:
            raise ValueError(f"{name} 长度应为 {N_PERIODS}，实际 {len(seq)}")


def build_model(
    prices: Sequence[float],
    loads: Sequence[float],
    pv: Sequence[float],
    *,
    enforce_grid_upper_bound: bool = False,
    name: str = "q1_deterministic_dispatch",
    eta_ch: float = ETA_CH,
    eta_dis: float = ETA_DIS,
) -> ModelBundle:
    """按 model_spec.md 构建问题 1 确定性 LP。

    参数
    ----
    prices : 144 个时段的电价 c_t（元/kWh）
    loads  : 144 个时段的负载功率 P_load_t（kW）
    pv     : 144 个时段的光伏预测功率 P_PV_t（kW）
    enforce_grid_upper_bound : 是否启用可选约束 C10（默认 False，见 A3 §14）
    eta_ch, eta_dis : 敏感性场景效率；默认仍为 H3 主假设，不修改全局常量。

    返回
    ----
    ModelBundle（prob 已含目标函数与全部约束，可直接求解）
    """
    _check_input(prices, loads, pv)
    for label, efficiency in (("eta_ch", eta_ch), ("eta_dis", eta_dis)):
        if not isfinite(efficiency) or not 0 < efficiency <= 1:
            raise ValueError(f"{label} must be finite and in (0, 1], got {efficiency}")

    prob = pulp.LpProblem(name, pulp.LpMinimize)

    # ---------------- 决策变量 ----------------
    p_grid = {t: pulp.LpVariable(f"P_grid_{t}", lowBound=0.0) for t in range(1, N_PERIODS + 1)}
    p_pv_use = {t: pulp.LpVariable(f"P_pv_use_{t}", lowBound=0.0) for t in range(1, N_PERIODS + 1)}
    p_ch = {
        t: pulp.LpVariable(f"P_ch_{t}", lowBound=0.0, upBound=P_CH_MAX)
        for t in range(1, N_PERIODS + 1)
    }
    p_dis = {
        t: pulp.LpVariable(f"P_dis_{t}", lowBound=0.0, upBound=P_DIS_MAX)
        for t in range(1, N_PERIODS + 1)
    }
    energy = {
        s: pulp.LpVariable(f"E_{s}", lowBound=E_MIN, upBound=E_MAX)
        for s in range(0, N_PERIODS + 1)
    }

    # ---------------- 约束 ----------------
    # C4 初始电量
    prob += energy[0] == E_INIT, "C4_E0_init"

    for t in range(1, N_PERIODS + 1):
        # C1 功率平衡（逐 10 min 等式）
        prob += (
            p_grid[t] + p_pv_use[t] + p_dis[t] == loads[t - 1] + p_ch[t],
            f"C1_balance_{t}",
        )
        # C2 光伏利用上限（下界 0 已由变量 lowBound 给出；允许弃光）
        prob += p_pv_use[t] <= pv[t - 1], f"C2_pv_upper_{t}"
        # C3 储能电量递推（含 Δt 与效率）
        prob += (
            energy[t]
            == energy[t - 1] + eta_ch * p_ch[t] * DELTA_T - (p_dis[t] / eta_dis) * DELTA_T,
            f"C3_recursion_{t}",
        )
        # 可选 C10 购电功率平凡上界（默认不启用）
        if enforce_grid_upper_bound:
            prob += p_grid[t] <= max(loads) + P_CH_MAX, f"C10_grid_upper_{t}"

    # C5 首尾电量相等
    prob += energy[N_PERIODS] == energy[0], "C5_terminal_energy"

    # C6 电量范围 1200 ≤ E_t ≤ 10800 已由变量 lowBound/upBound 施加

    # ---------------- 目标函数 ----------------
    cost_expr = pulp.lpSum(prices[t - 1] * p_grid[t] * DELTA_T for t in range(1, N_PERIODS + 1))
    throughput_expr = pulp.lpSum(
        (p_ch[t] + p_dis[t]) * DELTA_T for t in range(1, N_PERIODS + 1)
    )
    prob += cost_expr, "objective_min_purchase_cost"

    return ModelBundle(
        prob=prob,
        p_grid=p_grid,
        p_pv_use=p_pv_use,
        p_ch=p_ch,
        p_dis=p_dis,
        energy=energy,
        cost_expr=cost_expr,
        throughput_expr=throughput_expr,
        eta_ch=eta_ch,
        eta_dis=eta_dis,
    )


def apply_secondary_min_throughput(bundle: ModelBundle, c_star: float, eps_cost: float) -> None:
    """方案 B（两阶段优化）：在保持第一阶段最优购电费用不变的前提下最小化储能吞吐量。

    仅用于在**数值等价**的最优解中消除退化/无意义的同时充放电循环，
    **不得**改变第一阶段的购电费用水平。见 model_spec.md §7 方案 B、A3 任务书 §31。

    参数
    ----
    c_star   : 第一阶段最小购电费用（元）
    eps_cost : 费用允许偏差（元），约束 |C_buy − c_star| ≤ eps_cost
    """
    bundle.prob += bundle.cost_expr <= c_star + eps_cost, "secondary_cost_upper"
    bundle.prob += bundle.cost_expr >= c_star - eps_cost, "secondary_cost_lower"
    bundle.prob.setObjective(bundle.throughput_expr)


__all__ = [
    "N_PERIODS",
    "DELTA_T",
    "E_CAPACITY",
    "E_MIN",
    "E_MAX",
    "E_INIT",
    "P_CH_MAX",
    "P_DIS_MAX",
    "ETA_CH",
    "ETA_DIS",
    "TOL",
    "ModelBundle",
    "build_model",
    "apply_secondary_min_throughput",
]
