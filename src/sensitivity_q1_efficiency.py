"""Q1 efficiency interpretation sensitivity; never overwrites the A3 results."""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pandas as pd
import pulp

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.model_q1 import ETA_CH, ETA_DIS, build_model
from src.solve_q1 import (
    check_a2_gate, check_time_mapping_gate, load_data, solve_stage,
    extract_solution, run_validation, compute_baseline,
)


def run(output_dir: Path = ROOT / "outputs") -> dict:
    check_time_mapping_gate()
    check_a2_gate()
    df = load_data()
    inputs = [df[c].astype(float).tolist() for c in ("price_yuan_per_kwh", "load_kw", "pv_kw")]
    baseline = compute_baseline(df)["baseline_cost_yuan"]
    scenarios = []
    solutions = []
    for name, ch, dis in (("A", ETA_CH, ETA_DIS), ("B", math.sqrt(0.90), math.sqrt(0.90))):
        bundle = build_model(*inputs, eta_ch=ch, eta_dis=dis)
        status, solver = solve_stage(bundle, stage_label=f"efficiency_{name}")
        cost = float(pulp.value(bundle.cost_expr))
        sol = extract_solution(df, bundle)
        validation = run_validation(df, sol, cost, eta_ch=bundle.eta_ch, eta_dis=bundle.eta_dis)
        if not validation["all_checks_pass"]:
            raise RuntimeError(f"Scenario {name} validation failed: {validation['checks']}")
        if validation["simultaneous_charge_discharge_count"]:
            raise RuntimeError(f"Scenario {name} requires simultaneous-charge/discharge review")
        scenarios.append({
            "scenario": name, "eta_ch": ch, "eta_dis": dis,
            "round_trip_efficiency": ch * dis,
            "objective_cost_yuan": cost,
            "total_grid_energy_kwh": sum(sol["grid_kwh"]),
            "total_charge_energy_kwh": sum(sol["ch_kwh"]),
            "total_discharge_energy_kwh": sum(sol["dis_kwh"]),
            "min_storage_energy_kwh": min(sol["energy"]),
            "max_storage_energy_kwh": max(sol["energy"]),
            "max_charge_power_kw": max(sol["ch"]),
            "max_discharge_power_kw": max(sol["dis"]),
            "total_pv_curtailment_kwh": sum(sol["curt_kwh"]),
            "baseline_cost_yuan": baseline,
            "savings_yuan": baseline - cost,
            "savings_rate": (baseline - cost) / baseline,
            "solver_status": status, "solver": solver,
            "validation_all_pass": validation["all_checks_pass"],
            "simultaneous_charge_discharge_count": validation["simultaneous_charge_discharge_count"],
        })
        solutions.append(sol)
    a, b = scenarios
    delta = b["objective_cost_yuan"] - a["objective_cost_yuan"]
    comparison = {
        "objective_B_minus_A_yuan": delta,
        "objective_relative_change_percent": delta / a["objective_cost_yuan"] * 100,
        "dispatch_max_abs_difference_kw": {
            key: max(abs(x - y) for x, y in zip(solutions[0][key], solutions[1][key]))
            for key in ("grid", "ch", "dis")
        },
    }
    payload = {"main_scenario": "A", "scenarios": scenarios, "comparison": comparison}
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(scenarios).to_csv(output_dir / "q1_efficiency_sensitivity.csv", index=False, encoding="utf-8-sig")
    (output_dir / "q1_efficiency_sensitivity.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
    )
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
