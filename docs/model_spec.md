# C 题 问题 1：确定性微网日前优化调度模型

## 0. 模型定位与范围

- **场景**：非孤岛式微网，每天 00:00 制定当天 24 h 的购电与储能充放电计划。
- **输入**：附件 1 的日内电价曲线 $c_t$、小区负载功率 $P^{\text{load}}_t$、光伏预测功率 $P^{\text{PV}}_t$；附录 1 的储能参数。
- **目标**：仅最小化**外网购电费用**，即题目"节省购电费用"的经济目标。
- **模型类型**：**确定性线性规划（LP）**（判定依据见第 7 节）。
- **明确排除**：电池退化成本、循环惩罚、寿命折旧、售电收益、紧急购电、5 倍电价、调整购电、违约费用等均**不进入问题 1 主模型**；其中电池退化成本仅作为**扩展模型**可选项（见第 9 节）。

---

## 1. 时间离散化与集合定义

- 计划区间：当天 00:00 – 24:00，共 24 h。
- 时间步长：$\Delta t = 10\ \text{min} = \dfrac{1}{6}\ \text{h}$。
- 时段集合：$\mathcal{T} = \{1, 2, \dots, 144\}$，共 144 个时段，满足 $144 \times \frac{1}{6}\,\text{h} = 24\,\text{h}$。
- **时段 $t$ 覆盖墙钟区间**：$\big[(t-1)\Delta t,\ t\Delta t\big]$。例如 $t = 61$ 对应 $10{:}00\text{–}10{:}10$。
- 状态边界集合：$\mathcal{T}_0 = \{0, 1, \dots, 144\}$，共 145 个边界点；$E_0$ 为 00:00 电量，$E_{144}$ 为 24:00 电量，$E_t$ 为时段 $t$ **结束时**的电量。

> 时间标签映射：附件 1 第 2–145 行标签依次为 00:10, 00:20, …, 24:00（`0:00+1`）。按"**区间结束标签**"口径，标签 $\tau = t\Delta t$ 的整点行对应时段 $t$，即第 $(t+1)$ 行数据对应时段 $t$。该口径是**建模假设 H1**。

---

## 2. 决策变量

| 变量 | 含义 | 单位 | 取值范围 |
| --- | --- | --- | --- |
| $P^{\text{grid}}_t$ | 时段 $t$ 从外网购入的功率 | kW | $\ge 0$ |
| $P^{\text{pv,use}}_t$ | 时段 $t$ 实际利用的光伏功率（可弃光） | kW | $0 \le \cdot \le P^{\text{PV}}_t$ |
| $P^{\text{ch}}_t$ | 时段 $t$ 储能充电功率（微网母线侧计量） | kW | $0 \le \cdot \le 5000$ |
| $P^{\text{dis}}_t$ | 时段 $t$ 储能放电功率（微网母线侧计量） | kW | $0 \le \cdot \le 5000$ |
| $E_t$ | 时段 $t$ **结束时**储能剩余电量 | kWh | $1200 \le \cdot \le 10800$ |

辅助/派生量（由决策变量线性导出，非独立变量）：

| 派生量 | 定义 | 单位 |
| --- | --- | --- |
| $Q^{\text{buy}}_t$ | $Q^{\text{buy}}_t = P^{\text{grid}}_t \cdot \Delta t$（时段购电量） | kWh |
| $P^{\text{curt}}_t$ | $P^{\text{curt}}_t = P^{\text{PV}}_t - P^{\text{pv,use}}_t$（弃光功率） | kW |
| $Q^{\text{ch}}_t,\ Q^{\text{dis}}_t$ | $P^{\text{ch}}_t\Delta t,\ P^{\text{dis}}_t\Delta t$（时段充/放电量，分向记录） | kWh |

> **记号澄清**：题目要求"功率变量统一使用 kW"中的 $P^{\text{load}}$、$P^{\text{PV}}$ **不是决策变量**，而是给定参数（负载、光伏预测均为已知数据）。真正需要优化的功率型决策变量是 $P^{\text{grid}}_t, P^{\text{pv,use}}_t, P^{\text{ch}}_t, P^{\text{dis}}_t$，全部以 kW 表示。

---

## 3. 已知参数

| 参数 | 记号 | 数值 | 单位 | 来源 |
| --- | --- | --- | --- | --- |
| 时间步长 | $\Delta t$ | $1/6$ | h | 题目（10 min） |
| 电价 | $c_t$ | 附件 1 B 列 | 元/kWh | 附件 1 |
| 小区负载功率 | $P^{\text{load}}_t$ | 附件 1 C 列 | kW | 附件 1 |
| 光伏预测功率 | $P^{\text{PV}}_t$ | 附件 1 D 列 | kW | 附件 1 |
| 储能最大容量 | $E^{\text{cap}}$ | 12000 | kWh | 附录 1 |
| 运行电量下限 | $E^{\min}$ | 1200 | kWh | 附录 1 |
| 运行电量上限 | $E^{\max}$ | 10800 | kWh | 附录 1 |
| 初始电量 | $E_0$ | 6000 | kWh | 附录 1（2025-01-01 00:00） |
| 最大充电功率 | $P^{\text{ch,max}}$ | 5000 | kW | 附录 1 |
| 最大放电功率 | $P^{\text{dis,max}}$ | 5000 | kW | 附录 1 |
| 充电效率 | $\eta_{\text{ch}}$ | 0.90 | 无量纲 | 附录 1（解释假设 H3） |
| 放电效率 | $\eta_{\text{dis}}$ | 0.90 | 无量纲 | 附录 1（解释假设 H3） |

> $E^{\text{cap}}=12000$ kWh 是设备容量，**不替代**运行上限 $E^{\max}=10800$ kWh。$5000$ kW 是功率限制，**不等于**每时段可充入/放出的 $5000$ kWh。

---

## 4. 目标函数（问题 1 主目标）

仅计外网购电费用：

$$
\min\ C_{\text{buy}} \;=\; \sum_{t=1}^{144} c_t\, Q^{\text{buy}}_t
\;=\; \sum_{t=1}^{144} c_t\, P^{\text{grid}}_t\, \Delta t
$$

其中 $Q^{\text{buy}}_t = P^{\text{grid}}_t\Delta t$ 为时段购电量（kWh）。

- 全天购电量：$Q^{\text{buy}}_{\text{day}} = \displaystyle\sum_{t=1}^{144} Q^{\text{buy}}_t$
- 全天购电费：$C_{\text{day}} = \displaystyle\sum_{t=1}^{144} c_t\,Q^{\text{buy}}_t$（即目标函数值）

> **不含**电池退化成本、循环成本、售电收益、紧急购电惩罚。任何负购电量（售电）均不允许（见约束 C9）。

---

## 5. 全部约束

### C1 功率平衡（供给 = 需求，kW）

$$
P^{\text{grid}}_t + P^{\text{pv,use}}_t + P^{\text{dis}}_t \;=\; P^{\text{load}}_t + P^{\text{ch}}_t,
\qquad \forall t \in \mathcal{T}
$$

- 左端为时段 $t$ 的供电来源：外网 + 实际利用光伏 + 储能放电。
- 右端为用电去向：小区负载 + 储能充电。
- 该式直接满足题目"微网提供的电能不可低于小区负载"要求（此处取**等式**）。由于允许弃光（C2），当光伏富余时通过下调 $P^{\text{pv,use}}_t$ 即可维持平衡；又因超量购电只会增加费用、绝不最优，故等号在最优解处成立。若需写成不等式形式，等价写法为 $P^{\text{grid}}_t + P^{\text{pv,use}}_t + P^{\text{dis}}_t - P^{\text{ch}}_t \ge P^{\text{load}}_t$，两者最优解一致。

### C2 光伏实际利用与弃光（kW）

$$
0 \;\le\; P^{\text{pv,use}}_t \;\le\; P^{\text{PV}}_t, \qquad \forall t \in \mathcal{T}
$$

弃光量 $P^{\text{curt}}_t = P^{\text{PV}}_t - P^{\text{pv,use}}_t \ge 0$。**允许弃光**，多余光伏能量不强制全额消纳。

### C3 储能电量递推（kWh）

$$
E_t \;=\; E_{t-1} + \eta_{\text{ch}}\,P^{\text{ch}}_t\,\Delta t \;-\; \frac{1}{\eta_{\text{dis}}}\,P^{\text{dis}}_t\,\Delta t,
\qquad \forall t \in \mathcal{T}
$$

- 充电：外部充入 $P^{\text{ch}}_t\Delta t$（kWh），存入电池 $ \eta_{\text{ch}} P^{\text{ch}}_t\Delta t$（kWh）。
- 放电：电池释放 $P^{\text{dis}}_t\Delta t / \eta_{\text{dis}}$（kWh），对外送出 $P^{\text{dis}}_t\Delta t$（kWh）。
- 计量侧约定见假设 H4。

### C4 初始电量（kWh）

$$
E_0 = 6000
$$

### C5 首尾电量相等（kWh）

$$
E_{144} = E_0 \quad(= 6000)
$$

（题目明确要求 00:00 与 24:00 储电量相同。）

### C6 储能电量运行范围（kWh）

$$
1200 \;\le\; E_t \;\le\; 10800, \qquad \forall t \in \mathcal{T}_0 = \{0,1,\dots,144\}
$$

- 端点 $E_0, E_{144}$ 与区间内 $E_t$ 一并满足。
- 若需无量纲荷电比，另行定义 $\text{SOC}_t = E_t/E^{\text{cap}} = E_t/12000$（对应 10%–90%）；**本模型统一使用 $E_t$，不以 1200–10800 直接表示 SOC**。

### C7 充电功率上限（kW）

$$
0 \;\le\; P^{\text{ch}}_t \;\le\; 5000, \qquad \forall t \in \mathcal{T}
$$

### C8 放电功率上限（kW）

$$
0 \;\le\; P^{\text{dis}}_t \;\le\; 5000, \qquad \forall t \in \mathcal{T}
$$

### C9 购电非负（禁止售电，kW）

$$
P^{\text{grid}}_t \;\ge\; 0, \qquad \forall t \in \mathcal{T}
$$

题目未给出售电许可与上网电价，故不允许反向送电，也不以负购电量抵扣费用（假设 H7）。

### （可选）C10 购电功率数值上界

$$
P^{\text{grid}}_t \;\le\; P^{\text{grid,max}} = \max_t P^{\text{load}}_t + P^{\text{ch,max}}
$$

仅作为数值求解的平凡上界（防止无界搜索），**不代表题目给出的物理约束**（题目未给并网点容量上限，假设 H9）。

---

## 6. 单位（量纲）检查

| 编号 | 公式 | 左端量纲 | 右端量纲 | 结论 |
| --- | --- | --- | --- | --- |
| C1 | $P^{\text{grid}}+P^{\text{pv,use}}+P^{\text{dis}} = P^{\text{load}}+P^{\text{ch}}$ | kW | kW | ✓ |
| C2 | $0 \le P^{\text{pv,use}} \le P^{\text{PV}}$ | kW | kW | ✓ |
| C3 | $E_t = E_{t-1} + \eta_{\text{ch}}P^{\text{ch}}\Delta t - \frac{1}{\eta_{\text{dis}}}P^{\text{dis}}\Delta t$ | kWh | kWh + (－)·kW·h － (－)·kW·h = kWh | ✓ |
| C4 | $E_0 = 6000$ | kWh | kWh | ✓ |
| C5 | $E_{144} = E_0$ | kWh | kWh | ✓ |
| C6 | $1200 \le E_t \le 10800$ | kWh | kWh | ✓ |
| C7 | $0 \le P^{\text{ch}} \le 5000$ | kW | kW | ✓ |
| C8 | $0 \le P^{\text{dis}} \le 5000$ | kW | kW | ✓ |
| C9 | $P^{\text{grid}} \ge 0$ | kW | kW | ✓ |
| Obj | $\min \sum c_t P^{\text{grid}}_t\Delta t$ | 元 | (元/kWh)·kW·h = 元 | ✓ |
| Der. | $Q^{\text{buy}}_t = P^{\text{grid}}_t\Delta t$ | kWh | kW·h = kWh | ✓ |

要点：
- 效率 $\eta$ 无量纲，只出现在功率与时间相乘之处，**不改变量纲**。
- 凡是"功率 × 时间"一律得到电量（kW·h = kWh）；凡是"电价 × 电量"一律得到费用（元）。
- 所有约束端点同量纲，无非同类量相加或比较。
- 6 段汇总（表 2）为 24 个 10 min 时段求和：$Q^{\text{ch}}_{\text{block}} = \sum_{t\in\text{block}} P^{\text{ch}}_t\Delta t$，量纲 kWh ✓。

---

## 7. 模型类型判定：LP

**判定：问题 1 主模型是线性规划（LP）。**

依据：

1. **目标函数**线性：$\sum_t c_t P^{\text{grid}}_t\Delta t$，是决策变量的一次式。
2. **约束全部线性**：C1–C10 均为线性等式/不等式。
3. **变量连续**：$P^{\text{grid}}_t, P^{\text{pv,use}}_t, P^{\text{ch}}_t, P^{\text{dis}}_t, E_t$ 均为连续非负实数，无 0–1 整数变量。
4. **无需充放电互斥的 0–1 变量**：见下。

> **充放电互斥性论证（A7）**：题目未要求禁止同时充放电。即便允许，由于 $\eta_{\text{ch}},\eta_{\text{dis}} < 1$，在任一时段同时充电与放电会**严格损耗能量**：设 $P^{\text{ch}}_t = P^{\text{dis}}_t = P$，则净对外功率为 $0$，而电量净变化 $\Delta E = P\Delta t\big(\eta_{\text{ch}} - 1/\eta_{\text{dis}}\big) < 0$，纯属浪费并推高费用，**绝不出现在最优解中**。因此 LP 松弛的最优解自动满足"不同时充放电"，无需引入二进制变量。若建模者出于安全/合规需要**强制**互斥（$P^{\text{ch}}_t\cdot P^{\text{dis}}_t = 0$），须引入 0–1 变量 $z_t$ 并用大 M 约束，模型升级为 MILP——但这对问题 1 的最优费用**没有影响**，故本模型保持 LP。

**求解性质**：可行域非空（恒可令 $P^{\text{grid}}_t$ 补足负载、$P^{\text{pv,use}}_t=0$）且有下界 $C_{\text{buy}}\ge 0$，LP 必存在最优解。规模：$144\times4 + 145 = 721$ 个连续变量，约 $144\times 6$ 条约束，可用任何 LP 求解器（如 HiGHS / Gurobi / CPLEX）在秒级求解。

---

## 8. 输出映射（对应表 1、表 2、result1.xlsx）

**表 1（单 10 min 时段购电量，kWh）**：$Q^{\text{buy}}_t = P^{\text{grid}}_t\Delta t$，对应时段号

| 时间段 | 时段号 $t$ |
| --- | --- |
| 10:00–10:10 | 61 |
| 12:00–12:10 | 73 |
| 14:00–14:10 | 85 |
| 16:00–16:10 | 97 |
| 18:00–18:10 | 109 |
| 20:00–20:10 | 121 |

全天购电量 $Q^{\text{buy}}_{\text{day}}=\sum_t Q^{\text{buy}}_t$（kWh），全天购电费 $C_{\text{day}}=\sum_t c_t Q^{\text{buy}}_t$（元）。

**表 2（4 h 汇总充/放电量与首尾电量，kWh）**：每个 4 h 块含 24 个时段：

- 0:00–4:00 → $t=1\!:\!24$；4:00–8:00 → $t=25\!:\!48$；8:00–12:00 → $t=49\!:\!72$；
- 12:00–16:00 → $t=73\!:\!96$；16:00–20:00 → $t=97\!:\!120$；20:00–24:00 → $t=121\!:\!144$。
- 块充电量 $=\sum_{t\in\text{block}} P^{\text{ch}}_t\Delta t$，块放电量 $=\sum_{t\in\text{block}} P^{\text{dis}}_t\Delta t$（分向累计，不以净量代替）。
- 0:00 储电量 $=E_0$，24:00 储电量 $=E_{144}$。

**result1.xlsx**：
- "计划购电量"表 A2:A145 为 144 个 10 min 标签，B 列填 $Q^{\text{buy}}_t$（kWh）。
- 模板标签存在**整体错位**（A2 为 `0:10-0:20`，A145 为 `0:00+1-0:10+1`，缺当天 00:00–00:10，多含次日首段）。本模型**按当天 144 时段生成结果并记录显式映射**，不静默平移；具体映射处理属输出阶段任务（假设 H1、风险项 A2）。
- "充放电量"表：B2:B7 充电量、C2:C7 放电量、E2=E_0、E3=E_144。

---

## 9. 扩展模型（可选，问题 1 主结果不采用）

在**扩展模型**中可加入电池退化成本与充放电互斥，仅用于敏感性/对比分析，**不得计入问题 1 主结果**：

$$
\min\ C_{\text{buy}} + C_{\text{deg}},\qquad
C_{\text{deg}} = \sum_{t=1}^{144} k_{\text{deg}}\big(P^{\text{ch}}_t + P^{\text{dis}}_t\big)\Delta t
$$

并加互斥约束 $P^{\text{ch}}_t \le M z_t,\ P^{\text{dis}}_t \le M(1-z_t),\ z_t\in\{0,1\}$，模型升级为 **MILP**。其中 $k_{\text{deg}}$（元/kWh 吞吐）为题外引入参数，题目未给，须明确标注为假设。

---

## 10. 必要建模假设

| 编号 | 假设 | 说明/依据 |
| --- | --- | --- |
| H1 | **时间标签口径**：附件 1 标签为"区间结束"标签，标签 $\tau=t\Delta t$ 的整点行 = 时段 $t$；第 $(t+1)$ 行对应时段 $t$。 | A1；使 144 行恰好覆盖当天 00:00–24:00 |
| H2 | 每个 10 min 时段内功率（负载、光伏、购电、充放电）视为**恒定/平均值**，电价在该时段恒定。 | A3；离散化假设 |
| H3 | "充放电效率 90%"解释为**充电、放电各 0.90**，即 $\eta_{\text{ch}}=\eta_{\text{dis}}=0.90$，往返效率 $=0.81$。 | A4；标注为解释假设，不与"往返 90%"口径混用 |
| H4 | **计量侧**：$P^{\text{ch}}_t$ 在微网母线侧计量（电池内增加 $\eta_{\text{ch}}P^{\text{ch}}_t\Delta t$）；$P^{\text{dis}}_t$ 为对外输出功率（电池内减少 $P^{\text{dis}}_t\Delta t/\eta_{\text{dis}}$）。 | A5；统一连接功率、输出电量与 $E_t$ |
| H5 | 问题 1 作为 $E_0=6000$ kWh 初值下的**代表日**，由首尾相等得 $E_{144}=6000$。 | A6 |
| H6 | 最优解中不与外网售电，$P^{\text{grid}}_t\ge 0$；光伏富余通过**弃光**处理。 | A8、A9 |
| H7 | 无充放电互斥约束（由 H3 效率<1 自动成立）；如强制互斥则为扩展 MILP。 | A7 |
| H8 | 忽略自放电、线路损耗、辅助用电；**不计电池退化/折旧成本**（仅扩展模型）。 | A11 |
| H9 | 不设并网点购电功率上限、爬坡限制、最小充放电功率、最短运行时间或切换次数（题目未给）；C10 的 $P^{\text{grid,max}}$ 仅为数值平凡上界。 | A10 |
| H10 | 光伏预测视为**确定性**计划输入，问题 1 不引入预测误差、备用或鲁棒区间。 | A12 |
| H11 | 数值不逐时段舍入，统一保留足够精度后再汇总，保证 $\sum Q^{\text{buy}}_t$ 与首尾电量一致。 | A13 |

---

## 11. 全景 LP 汇总

$$
\begin{aligned}
\min_{P^{\text{grid}},P^{\text{pv,use}},P^{\text{ch}},P^{\text{dis}},E}\quad
& \sum_{t=1}^{144} c_t\,P^{\text{grid}}_t\,\Delta t \\[2pt]
\text{s.t.}\quad
& P^{\text{grid}}_t + P^{\text{pv,use}}_t + P^{\text{dis}}_t = P^{\text{load}}_t + P^{\text{ch}}_t, && \forall t\in\mathcal{T} \\
& 0 \le P^{\text{pv,use}}_t \le P^{\text{PV}}_t, && \forall t\in\mathcal{T} \\
& E_t = E_{t-1} + \eta_{\text{ch}}P^{\text{ch}}_t\Delta t - \tfrac{1}{\eta_{\text{dis}}}P^{\text{dis}}_t\Delta t, && \forall t\in\mathcal{T} \\
& E_0 = 6000,\quad E_{144}=E_0 \\
& 1200 \le E_t \le 10800, && \forall t\in\mathcal{T}_0 \\
& 0 \le P^{\text{ch}}_t \le 5000,\quad 0 \le P^{\text{dis}}_t \le 5000, && \forall t\in\mathcal{T} \\
& P^{\text{grid}}_t \ge 0, && \forall t\in\mathcal{T} \\
& \Delta t = \tfrac{1}{6}\ \text{h},\quad \mathcal{T}=\{1,\dots,144\} &&
\end{aligned}
$$

**输出**：$Q^{\text{buy}}_t = P^{\text{grid}}_t\Delta t$（kWh）、全天购电量、全天购电费、各 4 h 块充/放电量、$E_0$ 与 $E_{144}$。
