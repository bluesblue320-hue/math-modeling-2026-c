# A3 Optimization Report

> A3 Optimization Agent 交付物。问题 1（确定性条件下微网日前优化调度）的求解与验证报告。
> 唯一事实源：`docs/model_spec.md`（数学模型）、`docs/time_mapping_decision.md`（时间映射）、`docs/problem_spec.md`（题目事实）。
> 本报告不含论文正文、不含问题 2/3/4、不生成官方 `result1.xlsx`。

---

## 1. Input

| 项目 | 内容 |
| --- | --- |
| 数据文件 | `data/processed/q1_data.csv`（A2 冻结产物，**唯一**数据输入） |
| 时段数 | 144（`model_t = 1..144`） |
| 时间步长 | 10 min，$\Delta t = 1/6$ h |
| 时间映射 | Mapping A（输入标签 = 区间结束时刻 / 右端点），`source_row = model_t + 1` |
| 单位 | 电价 元/kWh；功率 kW；电量 kWh |
| 前置 Gate | `outputs/a2_validation.json` = PASS / rows 144 / missing 0 / 无重复 / 步长 10 / RIGHT_ENDPOINT / full_day_covered；`docs/time_mapping_decision.md` = `STATUS: DECIDED` / `BLOCK_A2: FALSE` |

A3 **未**重新读取 `C题/附件/附件1.xlsx`，**未**重新解析 `source_label`，**未**做任何 interpolation / resample / shift / sort / 时间重建 / 时间平移。
`model_t = 61` 严格对应 `10:00-10:10`（求解前 Gate 已校验）。

---

## 2. Solver

| 项目 | 内容 |
| --- | --- |
| 建模语言 | Python + PuLP 3.3.2 |
| **实际主求解器** | **`pulp.HiGHS`（HiGHS 1.15.1，经 highspy）** |
| 交叉校验求解器 | `pulp.PULP_CBC_CMD`（COIN-OR CBC 2.10.3） |
| Solver Status | **Optimal**（`pulp.LpStatus[prob.status]`） |
| 模型规模 | 721 个连续变量（4×144 功率 + 145 状态边界），≈ 720 条约束 |

**为什么主求解器不是 CBC（留痕说明）**：本环境**同时具备** CBC 与 HiGHS，按 A3 §15 优先考虑 CBC。
但实测 CBC 写出的解文件仅保留约 8 位有效数字（例如 `E=10550.043`、`P_ch=720.2102`），
由此产生**输出舍入级**的残差下限（平衡残差 ≈ 4×10⁻⁵ kW、递推残差 ≈ 4.7×10⁻⁴ kWh），
无法满足 §21/§22 建议的 1×10⁻⁶ 校验容差；收紧 CBC 的 `primalTolerance/dualTolerance` 亦不改变该结果（属解文件精度而非真实不可行）。
因此按 A3 §15「允许其他成熟 LP Solver」，**主求解器改用 PuLP + HiGHS**（同一 PuLP 模型、未改动任何数学模型），
并用 CBC 作**独立交叉校验**。两求解器最优值一致：HiGHS `35126.948589290` 元 vs CBC `35126.948591235` 元，
绝对差 `1.95×10⁻⁶` 元、相对差 `5.5×10⁻¹¹`。采用 HiGHS 后，全部残差降至机器精度（≈ 5×10⁻¹³）。

---

## 3. Model Implementation

严格实现 `docs/model_spec.md`（未改动）：

| 编号 | 内容 | 实现位置 |
| --- | --- | --- |
| Obj | $\min C_{\text{buy}} = \sum_t c_t P^{\text{grid}}_t \Delta t$（**含 $\Delta t=1/6$**） | `src/model_q1.py: build_model` |
| C1 | 功率平衡（逐 10 min **等式**）：$P^{\text{grid}}_t+P^{\text{pv,use}}_t+P^{\text{dis}}_t=P^{\text{load}}_t+P^{\text{ch}}_t$ | 同上 |
| C2 | 光伏利用 / 允许弃光：$0\le P^{\text{pv,use}}_t\le P^{\text{PV}}_t$ | 同上 |
| C3 | 储能递推（**含 $\Delta t$ 与效率**）：$E_t=E_{t-1}+\eta_{\text{ch}}P^{\text{ch}}_t\Delta t-\frac{1}{\eta_{\text{dis}}}P^{\text{dis}}_t\Delta t$，$\eta_{\text{ch}}=\eta_{\text{dis}}=0.90$ | 同上 |
| C4/C5 | $E_0=6000$；$E_{144}=E_0$ | 同上 |
| C6 | $1200\le E_t\le10800$，$t=0..144$ | 变量上下界 |
| C7/C8 | $0\le P^{\text{ch}}_t,P^{\text{dis}}_t\le5000$ | 变量上下界 |
| C9 | 禁止售电：$P^{\text{grid}}_t\ge0$ | 变量下界 |
| C10 | 可选购电功率平凡上界 —— **默认不启用**（A3 §14） | `enforce_grid_upper_bound=False` |

模型类型为 **LP**：**未**引入 0-1 变量、电池退化成本、售电收益、紧急购电、5 倍电价、违约费用或任何问题 2/3/4 机制。

---

## 4. Optimal Result

| 指标 | 数值 |
| --- | --- |
| **最小购电费用（objective）** | **35126.948589 元** |
| 费用独立复算（$\sum c_t Q^{\text{buy}}_t$） | 35126.948589 元（差 0.0） |
| 全天购电量 $Q^{\text{buy}}_{\text{day}}$ | 59482.698998 kWh |
| 最大购电功率 | 8458.8273 kW |

---

## 5. Storage Result

| 指标 | 数值 |
| --- | --- |
| 总充电量 | 20740.666132 kWh |
| 总放电量 | 16799.939567 kWh |
| 初始电量 $E_0$ | 6000.0 kWh |
| 末端电量 $E_{144}$ | 6000.0 kWh |
| 最小电量 | 1200.0 kWh（触及运行下限） |
| 最大电量 | 10800.0 kWh（触及运行上限） |
| 最大充电功率 | 5000.0 kW（触及上限） |
| 最大放电功率 | 4293.9182 kW |

---

## 6. PV Result

| 指标 | 数值 |
| --- | --- |
| 可用光伏电量 | 55482.835667 kWh |
| 实际利用光伏电量 | 55482.835667 kWh |
| 弃光电量 | 0.0 kWh |

> 在本算例中，储能可全额消纳可用光伏（弃光为 0）；允许弃光（C2）仍作为模型约束保留。

---

## 7. Validation

| 校验项 | 结果 | 容差 | 判定 |
| --- | --- | --- | --- |
| 功率平衡最大残差 | 9.095×10⁻¹³ kW | 1×10⁻⁶ | PASS |
| 储能递推最大残差 | 4.547×10⁻¹³ kWh | 1×10⁻⁶ | PASS |
| 末端电量误差 $\lvert E_{144}-6000\rvert$ | 0.0 kWh | 1×10⁻⁶ | PASS |
| 电量边界 $\min E/\max E$ | 1200.0 / 10800.0 kWh | 越界 ≤ 1×10⁻⁶ | PASS |
| 充电功率上限 | max 5000.0 ≤ 5000 kW | 1×10⁻⁶ | PASS |
| 放电功率上限 | max 4293.9182 ≤ 5000 kW | 1×10⁻⁶ | PASS |
| 光伏利用边界 | $0\le P^{\text{pv,use}}\le P^{\text{PV}}$ | 1×10⁻⁶ | PASS |
| 弃光非负 | min 0.0 ≥ 0 | 1×10⁻⁶ | PASS |
| 购电非负 | min（原始值）0.0 ≥ 0 | 1×10⁻⁶ | PASS |
| 费用独立复算 | 差 0.0 元 | 1×10⁻⁶ | PASS |

- **容差说明**：主求解器（HiGHS）为全双精度，全部残差 ≈ 5×10⁻¹³，**未需要放宽** 1×10⁻⁶ 容差。
- **展示层归零**：仅将 $\lvert v\rvert\le10^{-9}$ 的 Solver 浮点噪声在输出层归零；原始值另记于 `q1_summary.json`（`min_grid_kw_raw`、`negative_grid_raw_count`）。
  本算例 `min_grid_kw_raw = 0.0`、`negative_grid_raw_count = 0`，即**无**负购电。
- **同时充放电检查（强制）**：`tol = 1×10⁻⁶ kW`，`simultaneous_count = 0`，`max min(P_ch, P_dis) = 0.0 kW`。
  无同时充放电时段，故 LP 第一阶段结果**直接采用**。

---

## 8. Secondary Optimization

| 项目 | 内容 |
| --- | --- |
| 是否触发 | **否**（`secondary_optimization_used = false`） |
| 原因 | 同时充放电时段数 = 0（§7） |
| $C^{*}$ / eps_cost / throughput | 不适用（未触发两阶段优化） |

> 未无理由升级 MILP；未做任何额外优化。故问题 1 主结果取第一阶段 LP 最优解。

---

## 9. Baseline

No-Storage Baseline（$P^{\text{ch}}=P^{\text{dis}}=0$，允许弃光；仅用于结果解释，**未进入优化目标**）：

| 指标 | 数值 |
| --- | --- |
| Baseline 购电费用 | 48052.046591 元 |
| Baseline 全天购电量 | 61789.935400 kWh |
| 优化后购电费用 | 35126.948589 元 |
| **节省金额** | **12925.098002 元** |
| **节省比例** | **26.8981 %** |

---

## 10. Key Required Intervals

题目表 1 六个指定 10 min 时段（严格按 Mapping A，未重新解释 `model_t`）：

| 时间段 | model_t | 附件 1 行号 | 购电量（kWh） |
| --- | --- | --- | --- |
| 10:00–10:10 | 61 | 62 | 0.000000 |
| 12:00–12:10 | 73 | 74 | 480.412450 |
| 14:00–14:10 | 85 | 86 | 0.000000 |
| 16:00–16:10 | 97 | 98 | 445.431650 |
| 18:00–18:10 | 109 | 110 | 531.894050 |
| 20:00–20:10 | 121 | 122 | 0.000000 |

附：表 2 六个 4 h 汇总（充/放电量分向累计，不以净量代替）：

| 4 h 区间 | model_t | 充电量 kWh | 放电量 kWh | 购电量 kWh |
| --- | --- | --- | --- | --- |
| 00:00–04:00 | 1–24 | 4500.000000 | 0.000000 | 18487.106183 |
| 04:00–08:00 | 25–48 | 833.333333 | 6365.841200 | 7302.749567 |
| 08:00–12:00 | 49–72 | 4787.964288 | 1702.996983 | 1760.975505 |
| 12:00–16:00 | 73–96 | 5286.035177 | 91.101383 | 3809.993860 |
| 16:00–20:00 | 97–120 | 0.000000 | 5780.131883 | 10419.526717 |
| 20:00–24:00 | 121–144 | 5333.333333 | 2859.868117 | 17702.347167 |
| **0:00 / 24:00 储电量** | — | — | — | **6000.0 / 6000.0** |

---

## 11. A3 Conclusion

```
A3 STATUS: PASS
```

- 前置 Gate（时间映射 + A2 验证）全部通过；数据 144 行、Mapping A、`model_t=61 ↔ 10:00-10:10`。
- 严格实现 `docs/model_spec.md` 的问题 1 确定性 **LP**；Solver Status = **Optimal**。
- 目标函数与储能递推均**包含 $\Delta t=1/6$**；未加入任何禁止项。
- 内部验证全部 PASS：平衡/递推残差 ≈ 5×10⁻¹³、$E_0=E_{144}=6000$、电量范围 1200–10800、充放电上限、光伏边界、购电非负、费用复算。
- 同时充放电计数 = 0，未触发二阶段优化。
- 产物：`outputs/q1_solution.csv`（144 行）、`outputs/q1_solution.xlsx`、`outputs/q1_summary.json`、`src/model_q1.py`、`src/solve_q1.py`、`tests/test_model_q1.py`。
- 测试：`pytest tests/test_preprocess_q1.py tests/test_model_q1.py` → **A2 34 项 + A3 22 项全部 PASS**。
- **READY FOR A4 INDEPENDENT VALIDATION: YES**

---

*本报告基于 2026-09-11 在共享仓库中实跑结果撰写；未修改任何 Source of Truth，未生成官方 `result1.xlsx`，未处理问题 2/3/4。*

## 工程补充（2026-09-11）

上述为原 A3 运行记录，主结果继续保留。得到的是一组最优日前调度方案；A4 已观测到相同最优费用下不同的逐时段轨迹，不能声称唯一最优调度。

`build_model` 新增默认 `ETA_CH/ETA_DIS` 的关键字效率参数，validation 使用对应模型参数。敏感性分析独立输出，见 `q1_efficiency_sensitivity.md`。可选 `python src/solve_q1.py --representative-optimum` 在费用容差内最小化吞吐量，只写 `outputs/representative_optimum/`，不覆盖本报告主结果。吞吐量相同的调度仍可能不唯一，不保证更少切换。

正式导出使用 `python src/export_result1.py`，从官方模板复制生成 `outputs/result1.xlsx`，按时间映射决策第 3.3 节显式修正 144 个标签。另将主求解结果写盘闸门前移至 validation 通过之后，修复 A4 原 M2 所述失败时仍写结果的问题。
