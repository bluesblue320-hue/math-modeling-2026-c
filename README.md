# math-modeling-2026-c：Q1

确定性微网日前 LP。请先读 `AGENTS.md` 与其中列出的三个 Source of Truth。
主效率为双向各 0.90，Mapping A 为输入右端点解释，步长 1/6 h、144 个时段。

## 安装和运行

```bash
python -m pip install -r requirements.txt
python -m pytest -q
python src/solve_q1.py
python src/audit_q1_independent.py
python src/sensitivity_q1_efficiency.py
python src/export_result1.py
```

官方附件未入 Git。克隆后须自行放置 `C题/附件/附件1.xlsx` 和
`C题/附件/附件5/result1.xlsx`。运行依赖冻结的 `data/processed/q1_data.csv`
及 `outputs/a2_validation.json`；不重新清洗、平移或修改数据。

## 结果与正式导出

- `outputs/q1_solution.csv`、`q1_summary.json`：A3 主结果；`q1_solution.xlsx` 为内部检查表。
- `outputs/q1_efficiency_sensitivity.csv`、`.json`：A/B 效率口径比较，不覆盖主结果。
- `outputs/result1.xlsx`：正式结果文件，以官方模板副本填写，不重新求解。

按 `docs/time_mapping_decision.md` 第 3.3 节，导出显式把“计划购电量”
A2:A145 修正为 `00:00-00:10` 至 `23:50-24:00`，保持 `output_row=model_t+1`，
模型不移动。原始模板不变，其余格式和标签保持原样。购电、充电、放电均填 kWh，
后两者按六个 4 h 块分别累计；E0/E144 均为 6000 kWh。

导出自动检查全部 144 行、时间/单位、非负和有限值、JSON 汇总、六块及首尾电量。
不逐时段舍入；Excel/CSV 数值序列化允许绝对误差 1e-8 kWh，汇总允许 1e-6。
先保存临时文件并重新读取验证，通过后原子替换正式路径；失败抛异常并删除临时文件。
若已有上一份成功导出，失败不会覆盖它，不能将旧文件误认为本次生成。

导出模块沿用仓库 Python/openpyxl 依赖，以保持模板格式及运行可复现性。

## 可选代表解

```bash
python src/solve_q1.py --representative-optimum
```

API 为 `run(representative_optimum=False)`，默认关闭。打开时 Stage 1 最小化购电费，
Stage 2 在最优费用 ±1e-6 元内最小化电池吞吐量；仅作为多重最优解的选择规则，
不加入电池退化成本。写入 `outputs/representative_optimum/`，不覆盖主结果。
结果记录第一阶段费用、实际第二阶段费用与吞吐量变化。该规则仍不保证轨迹唯一、
更平滑或切换次数更少。正式导出默认只使用已通过 A4 的原主结果。

完整结果比较见 `docs/q1_efficiency_sensitivity.md`；独立审计见
`docs/a4_validation_report.md`。A4 保留独立参数，不从 A3 导入模型。
