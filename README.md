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
python src/build_q1_paper_assets.py
```

官方附件未入 Git。克隆后须自行放置 `C题/附件/附件1.xlsx` 和
`C题/附件/附件5/result1.xlsx`。运行依赖冻结的 `data/processed/q1_data.csv`
及 `outputs/a2_validation.json`；不重新清洗、平移或修改数据。

## 结果与正式导出

- `outputs/q1_solution.csv`、`q1_summary.json`：A3 主结果；`q1_solution.xlsx` 为内部检查表。
- `outputs/q1_efficiency_sensitivity.csv`、`.json`：A/B 效率口径比较，不覆盖主结果。

### 双版本 result1（`src/export_result1.py`）

正式输出采用**双版本**策略，两份都先在临时文件写出并重新读取验证，**两份全部通过后**
才原子替换正式路径；任何一份失败都不会发布损坏结果。官方模板源文件本身永不被修改。
两份数值写入顺序均为 `model_t = t` → 表格第 `t + 1` 行（`output_row = model_t + 1`）。

- `outputs/result1_submission.xlsx` —— **官方模板保留版本**（submission-safe）。
  严格保留官方模板的全部已有时间标签、文字、格式、sheet 与结构，**只填写原本需要填写的
  数值单元格**（计划购电量 B2:B145、六个 4h 充/放电量、E0、E144）；
  `计划购电量!A2:A145` **保持官方模板原样，绝不修改**。其时间标签来自官方模板，
  **不代表重新定义模型时间映射**。
- `outputs/result1_corrected_mapping.xlsx` —— **Mapping A 修正版本**。
  数值与提交版一致，但 `计划购电量!A2:A145` 显式修正为当天物理区间
  `00:00-00:10 … 23:50-24:00`（`docs/time_mapping_decision.md` 第 3.3 节）。
  用于内部核对、论文、数据分析与 Mapping A 物理解释；**不默认作为正式提交文件**。

导出自动检查全部 144 行、时间/单位、非负和有限值、JSON 汇总、六块及首尾电量；
提交版额外逐格比对官方模板（A 列、sheet、合并单元格、样式、行数）。不逐时段舍入；
Excel/CSV 数值序列化允许绝对误差 1e-8 kWh，汇总允许 1e-6。

导出模块沿用仓库 Python/openpyxl 依赖，以保持模板格式及运行可复现性。

## 论文素材（`src/build_q1_paper_assets.py`）

**只读取** `outputs/q1_solution.csv` 与 `outputs/q1_summary.json`，**不重新求解**、
不含手算 hardcode；统一从 validated outputs 生成：

- `outputs/paper/q1_table1.csv`：论文表 1（六个关键 10 min 时段购电量 + 汇总）。
- `outputs/paper/q1_table2.csv`：论文表 2（六个 4 h 充/放电量 + E(00:00)/E(24:00)）。
- `outputs/paper/q1_paper_metrics.json`：论文统一引用指标（避免各处复制错数字）。
- `outputs/paper/figures/`：4 张必需图 + 1 张可选电价背景图（`matplotlib`，白底论文风格）。

写作口径与技术事实见 `docs/q1_paper_notes.md`；主模型冻结状态见 `docs/q1_freeze_note.md`。

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
