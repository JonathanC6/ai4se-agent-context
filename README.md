# Agent 上下文实验

[PACE 基线](PACE/README.md) 和 [DAG-PACE 改进版](DAG-PACE/README.md) 使用相同的 WebWalkerQA 题目、网页快照、模型和评分器。实现说明、运行命令和结果分别放在两个目录中。

[PACE 论文](https://aclanthology.org/2026.acl-long.1252/) · [WebWalkerQA 实验进展](docs/WebWalkerQA实验进展.md)

从论文复现、DAG 消融到独立 PACE-v2，实验演进记录按轮次整理改动依据、逐题发现和下一轮要验证的问题。[持续更新的实验演进记录](docs/PACE实验演进记录.md) · [PACE-v2 运行说明](PACE-v2/README.md)

## 最新结果 · 五组 WebWalkerQA 对照

同一套 20 题、每步 6,000 个可见输入 token，五组取得 90/100 个评分。ReAct 答对 6/20；PACE-v2 加 DAG 从 5/20 增至 7/20，本地输入增加 25.2%。最新版 PACE 和它的 DAG 版各有五题因搜索异常缺测，在双方有评分的 15 题上分别答对 8 题和 7 题。第 536 题在依赖块升档后答对，但简要摘要此前已保留两个关键姓名。[题单、五组设置与逐题归因](docs/WebWalkerQA五组DAG对照.md) · [100 个实验组合的结果表](PACE-v2/experiments/webwalkerqa-unified20.csv)

## 此前结果 · 修复动作接口后的固定 20 题

ReAct 答对 8/20，历史标准 PACE 答对 10/20，独立 PACE-v2 答对 7/20。ReAct 和 PACE-v2 保留 35 条已有轨迹，只补跑 5 条执行异常。5 条都交卷，均判错。PACE-v2 最终交卷 20 题，ReAct 交卷 15 题。第 2 题是两组唯一的得分差异。[三组逐题对照与 token 开销](docs/WebWalkerQA动作接口补跑与三组对照.md) · [首次配对运行与压缩分析](docs/PACE实验演进记录.md#两组跑完后差的一分来自哪里)

同轮 PACE-v2 的可见输入比 ReAct 多约 57.3 万 token，其中动作占 49.3%，摘要占 31.1%。网关输入与实际请求的差异及历史标准 PACE 的分项单独核算。[WebWalkerQA 用量复核](docs/WebWalkerQA用量复核.md)

## 此前结果 · 标准 PACE 与两轮新版

每步可见输入预算为 6,000 token。ReAct 和标准 PACE 沿用 80,000 的网关输入停止条件。两轮新版均只记录网关用量。单源、多源各 10 题。

| 方法 | 答对 / 20 | 单源 / 多源答对 | 提交最终答案 | 网关回报 token，含重试 |
|---|---:|---:|---:|---:|
| ReAct | 6（30%） | 5 / 1 | 10 | 1,245,463 |
| 标准 PACE | 10（50%） | 6 / 4 | 18 | 2,923,460 |
| 新版 PACE（调整前） | 7（35%） | 4 / 3 | 11 | 11,942,183 |
| 新版 PACE（首步格式恢复、交卷前回看） | 10（50%） | 6 / 4 | 18 | 12,931,426 |

标准 PACE 和本轮新版各答对 10 题，其中 8 题相同。本轮多答对第 30、157 题，少答对第 15、40 题，6 次 Glimpse 均成功恢复了历史块。[本轮改动与四道差异题分析](docs/WebWalkerQA标准与新版PACE逐题对照.md) · [前期证据恢复实验](docs/WebWalkerQA新版PACE证据恢复实验.md)

## 早期窗口与压力公式消融

同一批 20 题，ReAct 答对 6 题，标准 PACE 答对 10 题，纯窗口压力 PACE 答对 7 题。两种压力公式下的 DAG-PACE 都答对 7 题。报告说明了 `glimpse` 的主动与自动触发条件、本地 token 估值与单次网关用量的区别，并逐题分析 PACE 净少的 3 分。[窗口预算与压力公式实验报告](docs/WebWalkerQA窗口预算与压力公式实验.md)
