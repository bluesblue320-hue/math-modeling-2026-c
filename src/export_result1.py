"""Copy the official template to outputs/result1.xlsx without solving.

Mapping A: explicitly correct A2:A145 to physical intervals, keeping row=t+1.
See docs/time_mapping_decision.md section 3.3. All output numbers are kWh.
Only a validated temporary workbook is atomically promoted to the final path.
"""
from __future__ import annotations

import json
import math
import os
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np
import openpyxl
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.model_q1 import DELTA_T, E_INIT, N_PERIODS
from src.preprocess_q1 import format_interval

TEMPLATE = ROOT / "C题" / "附件" / "附件5" / "result1.xlsx"
SOLUTION = ROOT / "outputs" / "q1_solution.csv"
SUMMARY = ROOT / "outputs" / "q1_summary.json"
OUTPUT = ROOT / "outputs" / "result1.xlsx"
VALUE_TOL = 1e-8  # Excel/CSV floating-point serialization only; no rounding.
TOTAL_TOL = 1e-6


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(f"result1 validation failed: {message}")


def close(actual, expected, label: str, tol: float = TOTAL_TOL) -> None:
    require(isinstance(actual, (int, float)) and not isinstance(actual, bool)
            and isinstance(expected, (int, float)) and not isinstance(expected, bool)
            and math.isfinite(actual) and math.isfinite(expected)
            and abs(actual - expected) <= tol, label)


def validate_inputs(sol: pd.DataFrame, summary: dict) -> None:
    require(len(sol) == N_PERIODS, "expected 144 input rows")
    require(sol["model_t"].tolist() == list(range(1, N_PERIODS + 1)), "model_t order must be 1..144")
    expected = [format_interval(i * 10, (i + 1) * 10) for i in range(N_PERIODS)]
    require(sol["physical_interval"].tolist() == expected, "physical intervals must follow Mapping A")
    require(summary.get("validation_all_pass") is True and summary.get("status") == "OPTIMAL",
            "source summary must be validated and OPTIMAL")
    require(summary.get("n_periods") == N_PERIODS, "summary n_periods")
    close(summary.get("delta_t_hours"), DELTA_T, "summary delta_t_hours")
    for direction in ("grid", "charge", "discharge"):
        kw = sol[f"{direction}_kw"].to_numpy(float)
        kwh = sol[f"{direction}_kwh"].to_numpy(float)
        require(bool(np.isfinite(kw).all() and np.isfinite(kwh).all()), f"{direction} must be finite")
        require(bool((kw >= 0).all() and (kwh >= 0).all()), f"{direction} must be nonnegative")
        require(bool(np.allclose(kwh, kw * DELTA_T, rtol=0, atol=VALUE_TOL)), f"{direction}_kwh != kw * 1/6")
        close(float(kwh.sum()), summary.get(f"total_{direction}_energy_kwh"), f"total {direction}")
    close(float(sol["energy_start_kwh"].iloc[0]), E_INIT, "CSV E0")
    close(float(sol["energy_end_kwh"].iloc[-1]), E_INIT, "CSV E144")
    close(summary.get("initial_energy_kwh"), E_INIT, "summary E0")
    close(summary.get("final_energy_kwh"), E_INIT, "summary E144")
    close(float((sol["price_yuan_per_kwh"] * sol["grid_kwh"]).sum()),
          summary.get("objective_cost_yuan"), "objective reconciliation")
    blocks = summary["blocks_4h"]
    require(len(blocks) == 6, "expected six summary blocks")
    for i, block in enumerate(blocks):
        require(block["block"] == format_interval(i * 240, (i + 1) * 240), f"block {i} label/order")
        require(block["model_t_start"] == i * 24 + 1 and block["model_t_end"] == (i + 1) * 24,
                f"block {i} model_t range")
        for direction in ("charge", "discharge"):
            close(float(sol[f"{direction}_kwh"].iloc[i * 24:(i + 1) * 24].sum()),
                  block[f"{direction}_kwh_sum"], f"block {i} {direction}")


def validate_workbook(path: Path, sol: pd.DataFrame, summary: dict) -> None:
    validate_inputs(sol, summary)
    wb = openpyxl.load_workbook(path, data_only=False)
    try:
        require(wb.sheetnames == ["计划购电量", "充放电量"], "official sheet names/order")
        grid, battery = wb.worksheets
        require(grid.max_row == 145, "expected exactly 144 purchase rows")
        for i, row in sol.iterrows():
            excel_row = i + 2
            require(grid.cell(excel_row, 1).value == row["physical_interval"], f"row {excel_row} interval")
            value = grid.cell(excel_row, 2).value
            close(value, float(row["grid_kwh"]), f"row {excel_row} grid kWh", VALUE_TOL)
            require(value >= 0, f"row {excel_row} negative purchase")
            close(value, float(row["grid_kw"]) * DELTA_T, f"row {excel_row} grid conversion", VALUE_TOL)
        for i, block in enumerate(summary["blocks_4h"]):
            # Official 4h labels are retained (unpadded hours).
            expected_label = f"{i * 4}:00-{(i + 1) * 4}:00"
            require(battery.cell(i + 2, 1).value == expected_label, f"block {i} template label")
            for col, direction in ((2, "charge"), (3, "discharge")):
                close(battery.cell(i + 2, col).value, block[f"{direction}_kwh_sum"], f"block {i} {direction} output")
        require(battery["D2"].value == "0:00" and battery["D3"].value == "24:00", "storage time labels")
        close(battery["E2"].value, E_INIT, "output E0")
        close(battery["E3"].value, E_INIT, "output E144")
    finally:
        wb.close()


def export_result1(
    solution: Path = SOLUTION, summary: Path = SUMMARY,
    template: Path = TEMPLATE, output: Path = OUTPUT,
) -> Path:
    solution, summary, template, output = map(Path, (solution, summary, template, output))
    require(output.resolve() not in {p.resolve() for p in (solution, summary, template, TEMPLATE)},
            "output must not overwrite a source or the official template")
    sol = pd.read_csv(solution, encoding="utf-8-sig").reset_index(drop=True)
    summ = json.loads(summary.read_text(encoding="utf-8"))
    validate_inputs(sol, summ)
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".result1-", suffix=".xlsx", dir=output.parent)
    os.close(fd)
    temp_path = Path(temporary)
    try:
        shutil.copyfile(template, temp_path)
        wb = openpyxl.load_workbook(temp_path)
        try:
            require(wb.sheetnames == ["计划购电量", "充放电量"], "unexpected template sheets")
            grid, battery = wb.worksheets
            require(grid.max_row == 145, "unexpected template row count")
            require(grid["A1"].value == "时间段" and grid["B1"].value == "购电量", "template purchase headers")
            for i, row in sol.iterrows():
                grid.cell(i + 2, 1, row["physical_interval"])
                grid.cell(i + 2, 2, float(row["grid_kwh"]))
            for i, block in enumerate(summ["blocks_4h"]):
                battery.cell(i + 2, 2, block["charge_kwh_sum"])
                battery.cell(i + 2, 3, block["discharge_kwh_sum"])
            battery["E2"] = summ["initial_energy_kwh"]
            battery["E3"] = summ["final_energy_kwh"]
            wb.save(temp_path)
        finally:
            wb.close()
        validate_workbook(temp_path, sol, summ)
        os.replace(temp_path, output)
    finally:
        temp_path.unlink(missing_ok=True)
    return output


if __name__ == "__main__":
    print(f"PASS: {export_result1()}")
    print("Mapping A: corrected A2:A145 labels to 00:00-00:10 ... 23:50-24:00; output_row=model_t+1.")
