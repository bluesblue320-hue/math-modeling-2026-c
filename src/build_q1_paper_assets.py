# -*- coding: utf-8 -*-
"""从已通过验证的 Q1 结果生成论文素材（表 1 / 表 2 / 指标 JSON / 4+1 张图）。

**只读取** ``outputs/q1_solution.csv`` 与 ``outputs/q1_summary.json``，
**不重新求解**、不重新清洗数据、不改动任何主模型结果。
所有数值均来源于上述 validated outputs，脚本内不含手算的 hardcode 结果。

产物：
  outputs/paper/q1_table1.csv          论文表 1（六个关键 10 min 时段购电量 + 汇总）
  outputs/paper/q1_table2.csv          论文表 2（六个 4 h 时段充/放电量 + E(00:00)/E(24:00)）
  outputs/paper/q1_paper_metrics.json  论文统一引用指标
  outputs/paper/figures/*.png          论文图（4 张必需 + 1 张可选电价背景图）

运行：  python src/build_q1_paper_assets.py
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # 无 GUI 后端，保证可复现

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.model_q1 import E_INIT, E_MAX, E_MIN, ETA_CH, ETA_DIS, N_PERIODS  # noqa: E402

SOLUTION = ROOT / "outputs" / "q1_solution.csv"
SUMMARY = ROOT / "outputs" / "q1_summary.json"
PAPER_DIR = ROOT / "outputs" / "paper"
FIGURES_DIR = PAPER_DIR / "figures"

# 题目表 1 的六个关键 10 min 时段（Mapping A 物理区间标签）。
TABLE1_INTERVALS = [
    "10:00-10:10",
    "12:00-12:10",
    "14:00-14:10",
    "16:00-16:10",
    "18:00-18:10",
    "20:00-20:10",
]

# 论文图统一风格（白底、清晰、非 debug）。
FIGSIZE = (10.0, 4.6)
DPI = 200


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(f"paper asset build failed: {message}")


def load_validated() -> tuple[pd.DataFrame, dict]:
    """读取并校验现有 validated outputs（不求解）。"""
    _require(SOLUTION.exists(), f"missing {SOLUTION}")
    _require(SUMMARY.exists(), f"missing {SUMMARY}")
    sol = pd.read_csv(SOLUTION, encoding="utf-8-sig").reset_index(drop=True)
    summ = json.loads(SUMMARY.read_text(encoding="utf-8"))

    _require(len(sol) == N_PERIODS, "solution must have 144 rows")
    _require(sol["model_t"].tolist() == list(range(1, N_PERIODS + 1)), "model_t must be 1..144")
    _require(summ.get("status") == "OPTIMAL" and summ.get("validation_all_pass") is True,
             "source summary must be OPTIMAL and validated")
    _require(sol["physical_interval"].astype(str).tolist()[0] == "00:00-00:10"
             and sol["physical_interval"].astype(str).tolist()[-1] == "23:50-24:00",
             "solution must follow Mapping A intervals")
    for label in TABLE1_INTERVALS:
        _require(label in set(sol["physical_interval"].astype(str)), f"missing interval {label}")
    return sol, summ


def build_table1(sol: pd.DataFrame, summ: dict) -> list[dict]:
    """六个关键时段购电量（kWh），数值直接取自 validated q1_solution.csv。"""
    by_interval = {str(r.physical_interval): float(r.grid_kwh) for r in sol.itertuples()}
    return [{"时间段": label, "购电量(kWh)": by_interval[label]} for label in TABLE1_INTERVALS]


def build_table1_summary(summ: dict) -> list[dict]:
    b = summ["baseline_no_storage"]
    return [
        {"指标": "全天购电量(kWh)", "数值": float(summ["total_grid_energy_kwh"])},
        {"指标": "全天购电费用(元)", "数值": float(summ["objective_cost_yuan"])},
        {"指标": "无储能购电费用(元)", "数值": float(b["baseline_cost_yuan"])},
        {"指标": "节省金额(元)", "数值": float(b["saving_yuan"])},
        {"指标": "节省比例(%)", "数值": float(b["saving_rate"]) * 100.0},
    ]


def build_table2(summ: dict) -> list[dict]:
    """六个 4 h 时段的充/放电量（kWh），来自 validated summary blocks_4h。"""
    rows = []
    for block in summ["blocks_4h"]:
        rows.append({
            "时间段": block["block"],
            "充电量(kWh)": float(block["charge_kwh_sum"]),
            "放电量(kWh)": float(block["discharge_kwh_sum"]),
        })
    return rows


def build_table2_energy(sol: pd.DataFrame) -> list[dict]:
    """E(00:00) 与 E(24:00)（kWh），取自 solution 首尾状态。"""
    e_start = float(sol["energy_start_kwh"].iloc[0])
    e_end = float(sol["energy_end_kwh"].iloc[-1])
    _require(abs(e_start - E_INIT) <= 1e-6 and abs(e_end - E_INIT) <= 1e-6,
             "E(00:00)/E(24:00) must equal initial energy 6000 kWh")
    return [{"时刻": "00:00", "储电量(kWh)": e_start}, {"时刻": "24:00", "储电量(kWh)": e_end}]


def build_metrics(summ: dict) -> dict:
    """论文统一引用指标（全部来自 validated summary / solution）。"""
    b = summ["baseline_no_storage"]
    return {
        "objective_cost_yuan": float(summ["objective_cost_yuan"]),
        "total_grid_energy_kwh": float(summ["total_grid_energy_kwh"]),
        "baseline_cost_yuan": float(b["baseline_cost_yuan"]),
        "saving_yuan": float(b["saving_yuan"]),
        "saving_rate": float(b["saving_rate"]),
        "total_charge_energy_kwh": float(summ["total_charge_energy_kwh"]),
        "total_discharge_energy_kwh": float(summ["total_discharge_energy_kwh"]),
        "min_energy_kwh": float(summ["min_energy_kwh"]),
        "max_energy_kwh": float(summ["max_energy_kwh"]),
        "pv_curtailment_kwh": float(summ["total_curtailment_kwh"]),
        "efficiency_main": {
            "eta_ch": ETA_CH,
            "eta_dis": ETA_DIS,
            "round_trip": ETA_CH * ETA_DIS,
        },
    }


# --------------------------------------------------------------------------
# CSV 写出
# --------------------------------------------------------------------------
def _write_sectioned_csv(path: Path, blocks: list[tuple[list[str], list[dict]]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        for index, (header, rows) in enumerate(blocks):
            if index:
                writer.writerow([])
            writer.writerow(header)
            for row in rows:
                writer.writerow([row[key] for key in header])


def write_tables(sol: pd.DataFrame, summ: dict) -> dict[str, Path]:
    t1 = build_table1(sol, summ)
    t1_sum = build_table1_summary(summ)
    t2 = build_table2(summ)
    t2_e = build_table2_energy(sol)
    _write_sectioned_csv(PAPER_DIR / "q1_table1.csv", [
        (["时间段", "购电量(kWh)"], t1),
        (["指标", "数值"], t1_sum),
    ])
    _write_sectioned_csv(PAPER_DIR / "q1_table2.csv", [
        (["时间段", "充电量(kWh)", "放电量(kWh)"], t2),
        (["时刻", "储电量(kWh)"], t2_e),
    ])
    return {"table1": PAPER_DIR / "q1_table1.csv", "table2": PAPER_DIR / "q1_table2.csv"}


def write_metrics(summ: dict) -> Path:
    metrics = build_metrics(summ)
    path = PAPER_DIR / "q1_paper_metrics.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# 绘图
# --------------------------------------------------------------------------
def _time_edges() -> np.ndarray:
    """0..24 h 的 145 个区间边界（小时）。"""
    return np.arange(N_PERIODS + 1) / (N_PERIODS / 24.0)


def _finish(fig, ax, title: str, ylabel: str, out: Path, *, legend_loc: str = "best") -> None:
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.set_xlabel("Time (h)")
    ax.set_ylabel(ylabel)
    ax.set_xlim(0, 24)
    ax.set_xticks(range(0, 25, 2))
    ax.grid(True, alpha=0.3, linewidth=0.6)
    ax.legend(loc=legend_loc, fontsize=9, framealpha=0.9)
    fig.tight_layout()
    fig.savefig(out, dpi=DPI)
    plt.close(fig)


def _step_x() -> np.ndarray:
    return np.arange(N_PERIODS) / (N_PERIODS / 24.0)


def plot_power_dispatch(sol: pd.DataFrame, out: Path) -> None:
    x = _step_x()
    fig, ax = plt.subplots(figsize=FIGSIZE)
    ax.step(x, sol["load_kw"], where="post", color="#1f77b4", linewidth=1.5, label="Load")
    ax.step(x, sol["pv_kw"], where="post", color="#2ca02c", linewidth=1.5, label="PV available")
    ax.step(x, sol["grid_kw"], where="post", color="#d62728", linewidth=1.8, label="Grid purchase")
    ax.fill_between(x, 0, sol["pv_kw"], step="post", color="#2ca02c", alpha=0.10)
    ax.fill_between(x, 0, sol["grid_kw"], step="post", color="#d62728", alpha=0.08)
    _finish(fig, ax, "Q1 Power Dispatch: Load, PV and Grid Purchase", "Power (kW)", out)


def plot_storage_charge_discharge(sol: pd.DataFrame, summ: dict, out: Path) -> None:
    x = _step_x()
    ch = sol["charge_kw"].to_numpy(float)
    dis = -sol["discharge_kw"].to_numpy(float)  # 镜像到负半轴，便于区分
    count = int(summ.get("simultaneous_charge_discharge_count", -1))
    fig, ax = plt.subplots(figsize=FIGSIZE)
    ax.fill_between(x, 0, ch, step="post", color="#17becf", alpha=0.75, label="Charge")
    ax.fill_between(x, 0, dis, step="post", color="#ff7f0e", alpha=0.75, label="Discharge")
    ax.axhline(0, color="black", linewidth=0.8)
    ax.text(0.02, 0.97, f"simultaneous charge & discharge count = {count}",
            transform=ax.transAxes, va="top", ha="left", fontsize=9,
            bbox=dict(boxstyle="round", fc="white", ec="0.7"))
    _finish(fig, ax, "Q1 Storage Charge / Discharge Power",
            "Power (kW)   [+charge  /  -discharge]", out)


def plot_storage_energy(sol: pd.DataFrame, out: Path) -> None:
    edges = _time_edges()
    energy = np.empty(N_PERIODS + 1)
    energy[0] = float(sol["energy_start_kwh"].iloc[0])
    energy[1:] = sol["energy_end_kwh"].to_numpy(float)
    fig, ax = plt.subplots(figsize=FIGSIZE)
    ax.plot(edges, energy, color="#9467bd", linewidth=1.8, label="Stored energy $E_t$")
    ax.fill_between(edges, E_MIN, energy, color="#9467bd", alpha=0.12)
    ax.axhline(E_MIN, color="#8c564b", linestyle="--", linewidth=1.2, label=f"$E_{{\\min}}$ = {E_MIN:.0f} kWh")
    ax.axhline(E_MAX, color="#7f7f7f", linestyle="--", linewidth=1.2, label=f"$E_{{\\max}}$ = {E_MAX:.0f} kWh")
    ax.axhline(E_INIT, color="#2ca02c", linestyle=":", linewidth=1.4,
               label=f"$E_0 = E_{{144}}$ = {E_INIT:.0f} kWh")
    ax.annotate(f"$E_0$={energy[0]:.0f}", xy=(edges[0], energy[0]), xytext=(1.6, E_INIT + 300),
                arrowprops=dict(arrowstyle="->", color="#2ca02c"), color="#2ca02c", fontsize=9)
    ax.annotate(f"$E_{{144}}$={energy[-1]:.0f}", xy=(edges[-1], energy[-1]), xytext=(19.5, energy[-1] + 1700),
                arrowprops=dict(arrowstyle="->", color="#2ca02c"), color="#2ca02c", fontsize=9)
    _finish(fig, ax, "Q1 Stored Energy Profile", "Stored energy (kWh)", out, legend_loc="lower left")


def plot_cost_comparison(metrics: dict, out: Path) -> None:
    labels = ["No Storage", "Optimized Storage"]
    values = [metrics["baseline_cost_yuan"], metrics["objective_cost_yuan"]]
    colors = ["#7f7f7f", "#1f77b4"]
    fig, ax = plt.subplots(figsize=(6.4, 4.6))
    bars = ax.bar(labels, values, color=colors, width=0.55)
    for bar, value in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, value + 600, f"{value:,.2f}",
                ha="center", va="bottom", fontsize=10)
    saving_pct = metrics["saving_rate"] * 100.0
    ax.annotate(
        f"Saving = {metrics['saving_yuan']:,.2f} yuan  (~{saving_pct:.2f}%)",
        xy=(0.5, max(values) * 0.55), ha="center", fontsize=11, fontweight="bold",
        bbox=dict(boxstyle="round", fc="#fff3cd", ec="#d6a400"),
    )
    ax.set_ylabel("Purchase cost (yuan)")
    ax.set_title("Q1 Purchase Cost: No Storage vs Optimized Storage", fontsize=12, fontweight="bold")
    ax.set_ylim(0, max(values) * 1.18)
    ax.grid(True, axis="y", alpha=0.3, linewidth=0.6)
    fig.tight_layout()
    fig.savefig(out, dpi=DPI)
    plt.close(fig)


def plot_price_and_storage(sol: pd.DataFrame, out: Path) -> None:
    """可选：电价背景 + 充放电行为，论证低价充电 / 高价放电。"""
    x = _step_x()
    fig, ax = plt.subplots(figsize=FIGSIZE)
    ax.step(x, sol["price_yuan_per_kwh"], where="post", color="#d62728", linewidth=1.6,
            label="Price (yuan/kWh)")
    ax.set_ylabel("Price (yuan/kWh)", color="#d62728")
    ax.tick_params(axis="y", labelcolor="#d62728")
    ax2 = ax.twinx()
    ax2.bar(x, sol["charge_kw"], width=0.12, color="#17becf", alpha=0.7, label="Charge")
    ax2.bar(x, -sol["discharge_kw"], width=0.12, color="#ff7f0e", alpha=0.7, label="Discharge")
    ax2.axhline(0, color="black", linewidth=0.7)
    ax2.set_ylabel("Power (kW)   [+charge / -discharge]")
    ax.set_title("Q1 Price Background and Storage Response", fontsize=12, fontweight="bold")
    ax.set_xlabel("Time (h)")
    ax.set_xlim(0, 24)
    ax.set_xticks(range(0, 25, 2))
    ax.grid(True, alpha=0.3, linewidth=0.6)
    lines = ax.get_legend_handles_labels()[0] + ax2.get_legend_handles_labels()[0]
    labels = ax.get_legend_handles_labels()[1] + ax2.get_legend_handles_labels()[1]
    ax.legend(lines, labels, loc="upper left", fontsize=9, framealpha=0.9)
    fig.tight_layout()
    fig.savefig(out, dpi=DPI)
    plt.close(fig)


def build_figures(sol: pd.DataFrame, summ: dict, metrics: dict) -> list[Path]:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    outputs = [
        FIGURES_DIR / "q1_power_dispatch.png",
        FIGURES_DIR / "q1_storage_charge_discharge.png",
        FIGURES_DIR / "q1_storage_energy.png",
        FIGURES_DIR / "q1_cost_comparison.png",
        FIGURES_DIR / "q1_price_and_storage.png",
    ]
    plot_power_dispatch(sol, outputs[0])
    plot_storage_charge_discharge(sol, summ, outputs[1])
    plot_storage_energy(sol, outputs[2])
    plot_cost_comparison(metrics, outputs[3])
    plot_price_and_storage(sol, outputs[4])
    for path in outputs:
        _require(path.exists() and path.stat().st_size > 0, f"figure not written: {path}")
    return outputs


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------
def run() -> dict:
    sol, summ = load_validated()
    tables = write_tables(sol, summ)
    metrics_path = write_metrics(summ)
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    figures = build_figures(sol, summ, metrics)
    return {
        "table1": tables["table1"],
        "table2": tables["table2"],
        "metrics": metrics_path,
        "figures": figures,
        "metrics_values": metrics,
    }


if __name__ == "__main__":
    result = run()
    print("=" * 72)
    print("Q1 PAPER ASSETS: PASS")
    print("=" * 72)
    print(f"table1 : {result['table1']}")
    print(f"table2 : {result['table2']}")
    print(f"metrics: {result['metrics']}")
    print(f"figures: {len(result['figures'])} -> {result['figures'][0].parent}")
    for fig in result["figures"]:
        print(f"  - {fig.name}")
    m = result["metrics_values"]
    print(f"objective={m['objective_cost_yuan']:.6f} yuan, "
          f"saving={m['saving_yuan']:.6f} yuan ({m['saving_rate']*100:.4f}%)")
