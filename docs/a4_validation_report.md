# A4 Independent Validation Report

> A4 Independent Validation / Red Team Agent — 问题 1（确定性条件下微网日前优化调度）独立审计报告。
> 本报告与 A3 相互独立：**未使用 A3 的 ModelBuilder、未 import `src.model_q1` / `src.solve_q1`、未调用 `build_model()` / `solve_q1.run()`、未复用 A3 的 PuLP 模型**。
> A3 的全部产物（`outputs/q1_solution.csv`、`q1_summary.json`、`q1_solution.xlsx`、`docs/a3_solver_report.md`）在本报告中一律视为**待证伪的 claim**，而非事实源。

---

## 1. Scope

- **审计对象**：A3 Optimization Agent 对问题 1 的求解结果与实现（commit `1407a46b...`）。
- **审计方法**：`Specification + A2 Data + Independent Calculation + Independent LP Reconstruction`。
  - **Layer 1 Artifact Audit**：从 `data/processed/q1_data.csv` 与 A3 结果 CSV 独立逐行复算全部派生量与约束。
  - **Layer 2 Independent LP**：依据 `docs/model_spec.md` **重新构建**优化模型（一维 721 维决策向量 + numpy 矩阵），用 `scipy.optimize.linprog(method="highs")` 独立求解。
  - **Layer 3 Source Review**：核对 A3 实现与规范的一致性（在完成前两层之后进行）。
- **不修改 A3 结果**：`q1_solution.csv`、`q1_solution.xlsx`、`q1_summary.json`、`src/model_q1.py`、`src/solve_q1.py`、`tests/test_model_q1.py` 均未被改动。
- **独立性守卫**：`tests/test_a4_independent_q1.py` 通过 AST 静态检查断言 A4 文件不含对 A3 模块的 import / 调用。

> **环境说明（可追溯）**：本机工作区 `.git` 原为一个与远端无关联的单 commit 本地仓库（branch `master`，A2 本地初始提交）。A4 通过 `git remote add origin` + `git fetch` + `git checkout -B main origin/main` 将工作区对齐到真正的共享仓库 `origin/main`（A3 commit `1407a46` 已存在于历史中），未执行 `git init`、未 force push、未重建历史。

---

## 2. Source of Truth

| 优先级 | 文件 | 本报告用途 |
| --- | --- | --- |
| 1 | `docs/problem_spec.md` | 题目事实、参数、单位、明确约束 |
| 2 | `docs/time_mapping_decision.md` | 时间映射唯一依据（Mapping A） |
| 3 | `docs/model_spec.md` | 数学模型（目标 / 约束 / 变量 / LP 判定） |
| — | `AGENTS.md`、`docs/data_report.md` | 协作约束与 A2 数据口径 |

**Gate 与不变量核对（全部一致，无冲突）：**

```
docs/time_mapping_decision.md → STATUS: DECIDED ; BLOCK_A2: FALSE ; DECISION: Mapping A (RIGHT_ENDPOINT)
Δt = 1/6 h ; T = 144 ; 状态边界 145
E0 = 6000 kWh ; Emin = 1200 kWh ; Emax = 10800 kWh
Pch,max = Pdis,max = 5000 kW ; ηch = ηdis = 0.90
禁止售电（P_grid ≥ 0）；允许弃光；目标 min Σ c_t·P_grid,t·Δt
```

四个 Source of Truth 在时间口径、参数、单位、目标上**相互一致，无冲突**；A4 未修改任何事实源。

---

## 3. Artifact Audit

| 项目 | 结果 |
| --- | --- |
| `q1_data.csv` 行数 | **144** ✅ |
| `q1_solution.csv` 行数 | **144** ✅ |
| `model_t`（两侧） | 严格 `1,2,…,144`，逐行一致 ✅ |
| `physical_interval`（两侧） | 逐行完全一致 ✅ |
| `t=1` | `00:00-00:10` ✅ |
| `t=61` | `10:00-10:10` ✅ |
| `t=73` | `12:00-12:10` ✅ |
| `t=85` | `14:00-14:10` ✅ |
| `t=97` | `16:00-16:10` ✅ |
| `t=109` | `18:00-18:10` ✅ |
| `t=121` | `20:00-20:10` ✅ |
| `t=144` | `23:50-24:00` ✅ |
| **无时间错位** | ✅ |

**原始输入未被改写**（`q1_solution.csv` 中三列 vs `q1_data.csv`）：

| 列 | 逐行最大绝对差 |
| --- | --- |
| `price_yuan_per_kwh` | 0.0 |
| `load_kw` | 0.0 |
| `pv_kw` | 0.0 |

**派生字段（kW → kWh / 区间费用）：**

| 项目 | 逐行最大绝对差 | 容差 | 判定 |
| --- | --- | --- | --- |
| `grid_kwh = grid_kw·Δt` | 2.27×10⁻¹³ | 1e-8 | ✅ |
| `charge_kwh = charge_kw·Δt` | 5.68×10⁻¹⁴ | 1e-8 | ✅ |
| `discharge_kwh = discharge_kw·Δt` | 1.14×10⁻¹³ | 1e-8 | ✅ |
| `curtailment_kwh = curtailment_kw·Δt` | 0.0 | 1e-8 | ✅ |
| `interval_cost = price·grid_kwh` | 1.14×10⁻¹³ | 1e-8 | ✅ |

> **无 ×6 / ÷6 单位错误**：功率与电量换算一致。

**其它一致性**：`q1_solution.xlsx` 的 `solution` sheet 与 `q1_solution.csv` 数值一致（`atol=1e-9`）✅。

---

## 4. Constraint Validation

独立复算（不读取 A3 的 validation 字段）：

| 约束 | 独立结果 | 容差 | 判定 |
| --- | --- | --- | --- |
| C1 功率平衡 max\|residual\| | **9.0949×10⁻¹³ kW**（t=1） | 1e-6 | ✅ |
| C2 光伏 `0 ≤ P_pv_use ≤ P_PV` | 越界 0 | 1e-6 | ✅ |
| 弃光恒等式 `curt = PV − pv_use` | maxdiff 0.0 | 1e-6 | ✅ |
| C3 储能递推 max\|residual\| | **1.8190×10⁻¹² kWh**（t=37, 06:00-06:10） | 1e-6 | ✅ |
| C6 电量范围 `1200 ≤ E ≤ 10800`（145 边界） | min 1200.0 / max 10800.0 | 1e-6 | ✅ |
| C7 充电 `0 ≤ P_ch ≤ 5000` | max 5000.0 | 1e-6 | ✅ |
| C8 放电 `0 ≤ P_dis ≤ 5000` | max 4293.9182 | 1e-6 | ✅ |
| C9 购电非负 `P_grid ≥ 0` | min 0.0 | 1e-6 | ✅ |
| 储能**连续性** `E_end[t] = E_start[t+1]`（t=1..143） | **max error 0.0 kWh** | 1e-6 | ✅ |
| C4 初始电量 | `E_start[1] = 6000.0` | 1e-6 | ✅ |
| C5 首尾相等 | `E_end[144] = E_start[1] = 6000.0` | 1e-6 | ✅ |
| 同时充放电（独立定义 tol=1e-6 kW） | **count = 0**，max min(P_ch,P_dis)=0.0 | — | ✅ |

**可行，无任何约束违例。**

**电量边界观测**：`min E = 1200.0 kWh` 出现在边界 `E_124`（时段 124 结束，20:30–20:40，日内电价峰值）；`max E = 10800.0 kWh` 出现在 `E_34`（时段 34 结束，05:30–05:40，日内电价谷值）。两端均**触及**运行上下限但未越界——符合"削峰填谷"的经济逻辑。

**购电功率**：max 8458.8273 kW。注意 **C10（购电功率上界）未启用**，模型本身不设 5000 kW 购电上限；A4 未以"grid > 5000"判错。

---

## 5. Cost Validation

| 项目 | 数值 |
| --- | --- |
| 独立逐行 `interval_cost` 复算 | maxdiff 1.14×10⁻¹³ |
| **A4 独立重算总费用** `Σ price·grid_kwh` | **35126.948589289634 元** |
| A3 `objective_cost_yuan` | 35126.948589289634 元 |
| 绝对差 | **0.0 元** ✅ |

**Summary Reconciliation**（A3 JSON vs A4 独立复算，全部 ≤ 1e-6）：

| 字段 | A3 | A4 | abs diff |
| --- | --- | --- | --- |
| objective_cost_yuan | 35126.948589289634 | 35126.948589289634 | 0.0 |
| total_grid_energy_kwh | 59482.69899835391 | 59482.69899835392 | 7.28×10⁻¹² |
| total_charge_energy_kwh | 20740.666131687245 | 20740.66613168725 | 3.64×10⁻¹² |
| total_discharge_energy_kwh | 16799.939566666668 | 16799.939566666668 | 0.0 |
| total_pv_available_kwh | 55482.835666666666 | 55482.835666666666 | 0.0 |
| total_pv_used_kwh | 55482.835666666666 | 55482.835666666666 | 0.0 |
| total_curtailment_kwh | 0.0 | 0.0 | 0.0 |
| initial_energy_kwh | 6000.0 | 6000.0 | 0.0 |
| final_energy_kwh | 6000.0 | 6000.0 | 0.0 |
| min_energy_kwh | 1200.0 | 1200.0 | 0.0 |
| max_energy_kwh | 10800.0 | 10800.0 | 0.0 |
| max_charge_kw | 5000.0 | 5000.0 | 0.0 |
| max_discharge_kw | 4293.9182 | 4293.9182 | 0.0 |
| max_grid_kw | 8458.8273 | 8458.8273 | 0.0 |
| simultaneous_charge_discharge_count | 0 | 0 | 0.0 |

> `objective_abs_diff_yuan` 在 A3 JSON 中自报 0.0，A4 独立复算亦为 0.0，二者一致。

---

## 6. Energy Reconciliation

全天微网能量（独立累计，Δt = 1/6 h）：

| 项目 | 数值 (kWh) |
| --- | --- |
| Load Energy | 111024.808100 |
| Grid Energy | 59482.698998 |
| PV Used Energy | 55482.835667 |
| Charge Energy | 20740.666132 |
| Discharge Energy | 16799.939567 |

**母线全天守恒** `Grid + PV_used + Discharge = Load + Charge`：
residual = **2.91×10⁻¹¹ kWh** ✅

**光伏能量**：

| 项目 | 数值 (kWh) |
| --- | --- |
| PV available | 55482.835667 |
| PV used | 55482.835667 |
| PV curtailed | 0.0 |
| 恒等式 residual | **0.0** ✅ |

> 本算例储能与负载可在全程消纳全部光伏（弃光为 0），且逐时段 `pv_used = pv`（因 `Σ(pv−pv_used)=0` 且每项 ≥ 0）。允许弃光约束 C2 仍被正确保留。

**电池全天净能量变化**（`E_144 = E_0` 的必然推论）：

`ηch·Q_charge − Q_discharge/ηdis = 0.9×20740.666132 − 16799.939567/0.9`
= **3.64×10⁻¹² kWh** ≈ 0 ✅

与 `E_144 − E_0 = 0.0 kWh` 一致（差 3.64×10⁻¹² kWh）。

---

## 7. Baseline Validation

独立 No-Storage Baseline（`P_ch = P_dis = 0`，允许弃光）：

| 项目 | A3 | A4 独立重算 |
| --- | --- | --- |
| Baseline grid_kw | — | `max(load − pv, 0)` |
| Baseline 购电费 | 48052.046590846665 元 | **48052.046590846665 元**（diff 0.0） |
| Baseline 购电量 | 61789.9354 kWh | 61789.9354 kWh |
| 优化后费用 | 35126.948589289634 元 | 35126.948589289634 元 |
| **节省金额** | 12925.098001557031 元 | **12925.098001557031 元** |
| **节省比例** | 26.8981217629 % | **26.8981217629 %** |

✅ Baseline 与 savings 完全一致。

---

## 8. Independent LP Reconstruction

A4 **未**复用 A3 的 PuLP 模型；按 `docs/model_spec.md` 重新建立：

| 项目 | 内容 |
| --- | --- |
| 决策向量 | `x = [P_grid(144), P_pv_use(144), P_ch(144), P_dis(144), E_0..E_144(145)]` |
| 变量数 | **721**（4×144 + 145） |
| 等式约束 | **290** = 144（功率平衡）+ 144（储能递推）+ 1（`E_0=6000`）+ 1（`E_144=E_0`） |
| 不等式 / 边界 | `0 ≤ P_grid`、`0 ≤ P_pv_use ≤ P_PV_t`、`0 ≤ P_ch ≤ 5000`、`0 ≤ P_dis ≤ 5000`、`1200 ≤ E_k ≤ 10800` |
| 目标 | `min Σ c_t·P_grid_t·Δt`（仅 grid 分量非零系数 `c_t·Δt`） |
| 求解器 | **`scipy.optimize.linprog(method="highs")`**（HiGHS，非 PuLP 模型） |
| Solver status | **0 / "Optimization terminated successfully. (HiGHS Status 7: Optimal)"** |
| 首尾处理 | 采用 `E_0 = 6000` 与 `E_144 = E_0` 两条等式（与 `E_144 = 6000` 数学等价） |

**独立最优目标值**：**35126.948589289634 元**。

---

## 9. Optimality Cross-check

| 项目 | 数值 |
| --- | --- |
| A3 objective `C_A3` | 35126.948589289634 元 |
| A4 recomputed A3 objective | 35126.948589289634 元（diff 0.0） |
| **A4 independent LP objective `C_A4`** | **35126.948589289634 元** |
| 绝对差 `|C_A3 − C_A4|` | **0.0 元** ≤ 1e-4 ✅ |
| 相对差 | **0.0** ≤ 1e-9 ✅ |

**结论：A3 的解为问题 1 LP 的一个最优可行解。**

**多重最优解（multiple-optimum-compatible）**：A4 独立解与 A3 解的目标值相同、全天 grid/charge/discharge 总量相同（≤1e-11），但**逐时段 dispatch 不完全相同**（`grid_kw` / `charge_kw` 最大逐时段差达 ~2000 kW，出现在电价相同的时段之间重排）。这属于 LP 的**多重最优解/退化**现象，**不是缺陷**：按任务口径，只要 A3 解满足全部约束且目标值等于独立最优值，即判定为有效最优解。A4 独立解已保存为 `outputs/a4_independent_solution.csv` 作为证据。

**Solver 一致性旁证**：A3 自报 HiGHS 35126.948589290 元、CBC 35126.948591235 元（相对差 5.5×10⁻¹¹）；A4 独立 scipy/HiGHS 35126.948589289634 元。三个独立求解运行一致。

---

## 10. Key Output Cross-check

**题目表 1 六个指定 10 min 时段**（A4 独立从 `q1_solution.csv` 提取）：

| 时间段 | model_t | 附件 1 行 | grid_kw | grid_kwh | 与 A3 差异 |
| --- | --- | --- | --- | --- | --- |
| 10:00–10:10 | 61 | 62 | 0.0 | **0.000000** | 0.0 |
| 12:00–12:10 | 73 | 74 | 2882.4747 | **480.412450** | 0.0 |
| 14:00–14:10 | 85 | 86 | 0.0 | **0.000000** | 0.0 |
| 16:00–16:10 | 97 | 98 | 2672.5899 | **445.431650** | 5.7×10⁻¹⁴ |
| 18:00–18:10 | 109 | 110 | 3191.3643 | **531.894050** | 0.0 |
| 20:00–20:10 | 121 | 122 | 0.0 | **0.000000** | 0.0 |

**题目表 2 六个 4 h 汇总**（A4 独立累计，与 A3 全部一致）：

| 4 h 区间 | model_t | 充电量 kWh | 放电量 kWh | 购电量 kWh |
| --- | --- | --- | --- | --- |
| 00:00–04:00 | 1–24 | 4500.000000 | 0.000000 | 18487.106183 |
| 04:00–08:00 | 25–48 | 833.333333 | 6365.841200 | 7302.749567 |
| 08:00–12:00 | 49–72 | 4787.964288 | 1702.996983 | 1760.975505 |
| 12:00–16:00 | 73–96 | 5286.035177 | 91.101383 | 3809.993860 |
| 16:00–20:00 | 97–120 | 0.000000 | 5780.131883 | 10419.526717 |
| 20:00–24:00 | 121–144 | 5333.333333 | 2859.868117 | 17702.347167 |
| 0:00 / 24:00 储电量 | — | — | — | **6000.0 / 6000.0** |

所有 4 h 分块与 A3 的 `blocks_4h` 差异 ≤ 1.8×10⁻¹²。

---

## 11. Source Code Review

（在 Layer 1 + Layer 2 完成之后进行。）

`src/model_q1.py` 与 `docs/model_spec.md` **逐条一致**：

| 检查项 | 结论 |
| --- | --- |
| 目标是否含 Δt | ✅ `prices[t-1]*p_grid[t]*DELTA_T` |
| 效率方向 | ✅ `E_t = E_{t-1} + 0.9·P_ch·Δt − (P_dis/0.9)·Δt`（与 C3 同向） |
| 是否误加 grid 上限 | ✅ 未加；C10 默认 `enforce_grid_upper_bound=False` |
| P_ch / P_dis 符号 | ✅ 平衡式 `+P_grid +P_pv_use +P_dis = load +P_ch`，方向正确 |
| PV 使用上界 | ✅ `p_pv_use[t] ≤ pv[t-1]`，下界 0 |
| E 索引 / off-by-one | ✅ `energy[0..144]`，递推 `energy[t] − energy[t-1]` |
| E_144 首尾 | ✅ `energy[144] == energy[0]`，且 `E_0=6000` |
| 费用用 kW 还是 kWh | ✅ 用 `grid_kwh = grid·Δt`，非 kW |
| 是否引入 0-1 / MILP / 退化成本 | ✅ 均未引入（LP 保持） |
| 是否有 clamp 篡改真实结果 | ✅ `_clamp` 仅对 \|v\| ≤ 1e-9 归零（展示层），原始值另记 `min_grid_kw_raw`；本算例 raw min grid = 0.0，无影响 |
| 是否在输出阶段篡改数据 | ✅ 未发现；输出由模型解直接导出 |

`src/solve_q1.py` 的 A3 自校验逻辑（`run_validation`）与 A4 独立复算口径一致；CBC 交叉校验为独立求解器旁证。

---

## 12. Findings

### Critical
无。

### Major
无。

### Minor（不影响本轮数值结果，但建议后续 Fix Agent 处理）

| ID | 位置 | 描述 | 本轮影响 |
| --- | --- | --- | --- |
| **M1** | `src/solve_q1.py:_val` | `_val()` 在变量值为 `None` 时返回 `0.0`，而非报错；理论上会以静默 0 掩盖未赋值变量。本算例 Solver = Optimal 且 721 个变量全部有值，无影响。建议改为在非 Optimal 或 None 时抛错。 | 无 |
| **M2** | `src/solve_q1.py:run` | 输出文件（`q1_solution.csv` / `.xlsx` / `q1_summary.json`）在 `write_outputs()` 中**先于**最终 `validation_all_pass` 闸门写出；若校验失败，磁盘上仍会留下看似正式的结果文件。建议先校验、后写盘（或失败时清理）。 | 无（本轮 `validation_all_pass = True`） |
| **M3** | 问题 1 LP 固有 | LP 存在多重最优解：A4 独立最优解与 A3 解目标相同但逐时段 dispatch 不同（同价时段间 grid/charge 重排，最大差 ~2000 kW）。A3 解为**有效最优解**，非缺陷；后续可采用 model_spec §7 方案 B（固定 C\* 后最小化吞吐量）选择代表解，但该次目标也不保证轨迹唯一。 | 无 |

---

## 13. Final Verdict

```
A4 STATUS: PASS
```

判定依据（全部满足）：

- ✅ A3 solution **可行**（C1–C9、首尾、连续性、递推、边界全部独立复算通过）；
- ✅ 时间映射 PASS（Mapping A，`model_t` / `physical_interval` 逐行一致，关键锚点全对）；
- ✅ 单位 PASS（无 ×6/÷6 错误）；
- ✅ 费用独立复算 PASS（差 0.0 元）；
- ✅ Summary 主要结果一致（全部 ≤ 1e-6）；
- ✅ 独立 LP：**Optimal**，且 `C_A3 ≈ C_A4`（绝对差 0.0 元，相对差 0.0）；
- ✅ 无 Critical Finding、无 Major Finding；
- ⚠️ Minor Finding 3 项（M1/M2/M3），均已记录，不影响本轮数值结果。

**READY FOR RESULT EXPORT: YES**

---

*生成本报告时，A4 未修改任何 A3 文件，未生成官方 `result1.xlsx`，未开始论文写作。*

## 本轮工程修复注记（2026-09-11）

保留以上独立审计的历史证据。本轮未修改 A4 程序、独立参数或独立性守卫。M2 的先写盘问题已在 A3 中修复，M1 的 `_val(None)` 行为仍为既有待改进项。A4 脚本的 findings 文本为固定历史描述，重新运行不会动态撤销已修复的 M2。M3 表述修正为选择代表解，不声称唯一化。
