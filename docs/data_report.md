# Problem 1 Data Report

> A2 Data Engineering Agent 交付物。
> 本报告只描述**问题 1 输入数据的标准化与验证**，不包含数学建模、优化求解或 result1.xlsx 结果。
> 唯一事实源：`docs/time_mapping_decision.md`（时间映射，`STATUS: DECIDED`）、`docs/problem_spec.md`（题目事实）、`docs/model_spec.md`（数学模型）。

---

## 1. Source File

| 项目 | 内容 |
| --- | --- |
| 文件名 | `C题/附件/附件1.xlsx` |
| 工作表 | `Sheet1` |
| 原始使用区域 | `A1:D145`（`max_row=145`，`max_col=4`） |
| 数据行数 | **144**（第 2–145 行；第 1 行为表头） |
| 表头 | A1 `时间` / B1 `电价` / C1 `小区负载` / D1 `光伏发电预测功率` |
| 读取方式 | `openpyxl.load_workbook(..., data_only=True)` 逐单元格真实读取 |
| 源文件 SHA256（前 16 位） | `66b87134f5ecccd6…` |

字段与单位：

| 列 | 原始表头 | 输出字段 | 单位 |
| --- | --- | --- | --- |
| A | 时间 | `source_label` / `source_minute` | 时:分（时刻标签） |
| B | 电价 | `price_yuan_per_kwh` | 元/kWh |
| C | 小区负载 | `load_kw` | kW |
| D | 光伏发电预测功率 | `pv_kw` | kW |

> 附件 1 是**唯一**的问题 1 输入数据源；附件 2/3/4 为全年数据，附件 5 的 `result1.xlsx` 仅为输出模板，均未参与本阶段处理。

---

## 2. Time Parsing

### 2.1 原始时间列的真实类型（实读结果）

A 列**不是单一类型**，实测统计：

| 类型 | 行范围 | 数量 | 示例 | `data_type` | `number_format` |
| --- | --- | --- | --- | --- | --- |
| Excel 时间对象 `datetime.time` | 第 2–61 行 | **60** | `datetime.time(0, 10)` … `datetime.time(10, 0)` | `d` | `h:mm` |
| 字符串 `str` | 第 62–145 行 | **84** | `'10:10'` … `'23:50'`、`'0:00+1'` | `s` | `General` |

- **类型切换点**：第 61 行 = `datetime.time(10, 0)`（时间对象）→ 第 62 行 = `'10:10'`（字符串）。
- 混合类型意味着：**直接 `astype(str)` 后 `sort_values()` 会得到错误顺序/错误解析**（例如 `datetime.time` 与字符串排序规则不一致），必须自行实现可靠的解析函数。

### 2.2 统一解析规则 `parse_source_time()`

实现于 `src/preprocess_q1.py`，把任意单元格统一映射为 `source_minute`（分钟，范围 `10..1440`）：

1. `datetime.datetime` → `hour * 60 + minute`
2. `datetime.time` → `hour * 60 + minute`
3. 字符串以 `'+1'` 结尾（即 `0:00+1`）→ 解析 `'0:00'` 得 `0`，再 **加 1440** 得 **1440**（次日 0:00 = 当天 24:00）
4. 其他字符串 `'H:MM'` / `'HH:MM'` → `H * 60 + MM`
5. 空值 / 非法格式 → 抛 `ValueError`（**不静默填补**）

### 2.3 `0:00+1` 的处理

题目附录 2 明确：`0:00+1` 表示第二天凌晨 0:00，即当天 **24:00**。
因此它在时间轴上排在 `23:50` 之后，对应 `source_minute = 1440`，**不是** `0`。
本阶段按该口径处理，并规范化为标签写法 `0:00+1`（见 §7）。

### 2.4 反解析（展示用）

- `format_label(minute)`：`1440 → '0:00+1'`，其余 → `'HH:MM'`（如 `610 → '10:10'`）。
- `format_interval(start, end)`：`1440` 写作 `'24:00'`（当天 24:00，不使用次日标记），如 `'23:50-24:00'`。

---

## 3. Mapping Rule

### 3.1 采用 Mapping A（标签 = 区间结束时刻 / 右端点）

依据 `docs/time_mapping_decision.md`（`STATUS: DECIDED`、`BLOCK_A2: FALSE`），正式采用 **Mapping A**：
**附件 1 的时间标签是其对应 10 分钟区间的结束时刻。**

> 该映射是**建模解释**（为完整覆盖当天 00:00–24:00、与首尾储电量 0:00/24:00 及表 2 的 4 h 边界一致），
> **不是题目明文定义**（题目仅定义 `0:00+1` = 当天 24:00）。候选 Mapping B（标签 = 区间开始时刻）已 **REJECTED**。

### 3.2 映射公式

| 量 | 公式 | 说明 |
| --- | --- | --- |
| `model_t` | `t`（`t = 1..144`） | 模型时段编号 |
| `physical_interval` | `[10(t-1), 10t]` 分钟 | 时段覆盖的墙钟区间 |
| `source_minute` | `10t` | 标签相对当天 00:00 的分钟数 |
| `source_excel_row` | `t + 1` | 附件 1 电子表格行号（第 1 行为表头） |
| `source_label` | `10t` 的标签写法（`1440 → '0:00+1'`） | 附件 1 A 列原值 |
| `interval_start_min` | `10(t-1)` | |
| `interval_end_min` | `10t` | |

等价表述：`source label = interval end`；`source_row = model_t + 1`。

### 3.3 边界

- 第一时段：`model_t = 1` ↔ `00:00-00:10` ↔ 标签 `00:10` ↔ 第 2 行。
- 最后时段：`model_t = 144` ↔ `23:50-24:00` ↔ 标签 `0:00+1` ↔ 第 145 行。
- 全天覆盖 **00:00–24:00**，共 144 个连续 10 min 区间，无 gap、无 overlap、无次日额外区间。

### 3.4 本阶段不做的事

- **不**重新解释时间映射（不改为左端点、不平移、不循环 shift）。
- **不**删除首条 `00:10`、**不**虚构 `00:00` 数据点、**不**增加次日 `00:10`。
- 输出侧（`result1.xlsx`）的模板错位属后续 Export Agent 职责，本阶段**不修改**任何 result 文件。

---

## 4. Data Quality

| 检查项 | 结果 | 判定 |
| --- | --- | --- |
| 行数（A） | 144（= 144 时段） | PASS |
| `model_t` 是否严格 1..144、无重复（B、I） | 严格递增、无重复、无缺失 | PASS |
| `source_minute` 是否严格 10..1440、步长 10（C） | 序列恰为 `{10,20,…,1440}`，相邻差恒为 10 | PASS |
| `physical_interval` 是否覆盖 00:00–24:00、无 gap/overlap（D） | 连续覆盖 1440 min | PASS |
| `source_excel_row` 是否 2..145（E） | 连续 2..145 | PASS |
| 数值缺失（F） | 缺失值 = **0** | PASS |
| 数值类型（G） | price / load / pv 均可无损转 float（原列 `data_type='n'`） | PASS |
| 合理性（H） | `price ∈ [0.3713, 1.3952]`、`load ∈ [3309.3934, 5958.9696]`、`pv ∈ [0.0000, 7612.3160]`，**无负值** | PASS |
| 重复：`source_label` / `model_t` / `physical_interval`（I） | 三者重复数均为 **0** | PASS |
| 关键映射点（J） | 8/8 全部一致（见 §6） | PASS |

- 负值计数：`negative_price_count = 0`、`negative_load_count = 0`、`negative_pv_count = 0`。
- **未做任何插值 / 填充 / 重采样 / 平滑**（无 linear / spline / ffill / bfill / resample / rolling）。
- 若存在缺失或负值，脚本**不自动修改**，而是记录到 JSON 并令验证 FAIL，交由人工确认。

---

## 5. Statistics

| 字段 | 单位 | min | max | mean |
| --- | --- | --- | --- | --- |
| `price_yuan_per_kwh` | 元/kWh | 0.3713 | 1.3952 | 0.766197 |
| `load_kw` | kW | 3309.3934 | 5958.9696 | 4626.033671 |
| `pv_kw` | kW | 0.0000 | 7612.3160 | 2311.784819 |

补充描述（仅用于数据理解，非模型结论）：

- 电价峰值 `1.3952` 位于 `t=124`（`20:30-20:40`）；电价谷值 `0.3713` 位于 `t=34`（`05:30-05:40`）。
- 负载峰值 `5958.9696` kW 位于 `t=55`（`09:00-09:10`）；负载谷值 `3309.3934` kW 位于 `t=133`（`22:00-22:10`）。
- 光伏峰值 `7612.3160` kW 位于 `t=73`（`12:00-12:10`）；`pv = 0` 共 55 个时段；`pv > 0` 出现在 `t=28..116`（约 04:30–19:30）。

> 单位换算说明（供 A3 使用，A2 不代为换算）：
> 若后续需要把某时段的**功率** $P$（kW）转换为该时段的**电量** $Q$（kWh），使用
> $$Q = P \times \Delta t,\qquad \Delta t = \frac{1}{6}\ \text{h},$$
> 因此 $\text{kW} \times \text{h} = \text{kWh}$。
> **A2 不把 `load_kw` / `pv_kw` 乘以 $1/6$**：A3 的数学模型使用功率型变量，倍率应在求解/输出阶段统一施加。

---

## 6. Key Mapping Validation

题目表 1 六个时段 + 首尾时段的完整映射（实读校验，全部 `ok = true`）：

| physical interval | model_t | source label | source row | source minute | 校验 |
| --- | --- | --- | --- | --- | --- |
| 00:00-00:10 | 1 | `00:10` | 2 | 10 | OK |
| 10:00-10:10 | 61 | `10:10` | 62 | 610 | OK |
| 12:00-12:10 | 73 | `12:10` | 74 | 730 | OK |
| 14:00-14:10 | 85 | `14:10` | 86 | 850 | OK |
| 16:00-16:10 | 97 | `16:10` | 98 | 970 | OK |
| 18:00-18:10 | 109 | `18:10` | 110 | 1090 | OK |
| 20:00-20:10 | 121 | `20:10` | 122 | 1210 | OK |
| 23:50-24:00 | 144 | `0:00+1` | 145 | 1440 | OK |

**直接回答：** 「论文表 1 的 10:00–10:10 对应附件 1 哪一行？」
→ **附件 1 第 62 行**（标签 `10:10`），`model_t = 61`，物理区间 `[600, 610]` min。

---

## 7. Output Dataset

文件：`data/processed/q1_data.csv`（UTF-8 with BOM，145 行 = 1 表头 + 144 数据行）。

| 字段 | 类型 | 单位 | 含义 |
| --- | --- | --- | --- |
| `model_t` | int | — | 模型时段编号，1..144，唯一 |
| `physical_interval` | str | — | 物理区间 `HH:MM-HH:MM`，如 `00:00-00:10`、`23:50-24:00` |
| `interval_start_min` | int | min | 区间左端点分钟数 = `10(t-1)` |
| `interval_end_min` | int | min | 区间右端点分钟数 = `10t` |
| `source_excel_row` | int | — | 附件 1 行号 = `t+1`（2..145） |
| `source_label` | str | — | 附件 1 A 列标签，`1440` 写作 `0:00+1` |
| `source_minute` | int | min | 标签分钟数 = `10t`（10..1440） |
| `price_yuan_per_kwh` | float | **元/kWh** | 外网购电单价 $c_t$ |
| `load_kw` | float | **kW** | 小区负载功率 $P^{\text{load}}_t$ |
| `pv_kw` | float | **kW** | 光伏预测功率 $P^{\text{PV}}_t$ |

**单位约定（重要）：**

- `price_yuan_per_kwh` 单位 **元/kWh**；`load_kw`、`pv_kw` 单位 **kW**（均为功率，未乘 $1/6$）。
- 功率 → 电量换算仅在后续阶段使用：$Q = P \times \Delta t$，$\Delta t = 1/6$ h，故 kW × h = kWh。
- 本数据集**不含** `P_grid`、`P_ch`、`P_dis`、`E_t`、`P_pv_use`、`P_curt` —— 这些属 A3 Optimization Agent。

首行 / 末行示例：

```
model_t,physical_interval,interval_start_min,interval_end_min,source_excel_row,source_label,source_minute,price_yuan_per_kwh,load_kw,pv_kw
1,00:00-00:10,0,10,2,00:10,10,0.4248,3439.8466,0.0
...
144,23:50-24:00,1430,1440,145,0:00+1,1440,0.4276,3444.7259,0.0
```

---

## 8. A2 Conclusion

```
A2 STATUS: PASS
```

- 前置 Gate 通过：`docs/time_mapping_decision.md` 为 `STATUS: DECIDED`、`BLOCK_A2: FALSE`。
- 四个 Source of Truth（`AGENTS.md`、`problem_spec.md`、`time_mapping_decision.md`、`model_spec.md`）时间口径一致，**无冲突**，未做任何修改。
- 附件 1 经**真实读取**（非抄录），时间列统一解析，按 Mapping A 生成 144 行标准化数据集，全部完整性检查（A–J）通过。
- 未插值、未填补、未平滑、未平移、未重新解释映射；未修改 `result1.xlsx`；未生成储能/优化变量。
- 产物：`data/processed/q1_data.csv`、`outputs/a2_validation.json`、`src/preprocess_q1.py`、`tests/test_preprocess_q1.py`（34 项测试全部通过）、本报告。

**READY FOR A3: YES**
