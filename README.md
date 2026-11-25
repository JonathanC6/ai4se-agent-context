# Agent 上下文实验

[PACE 基线](PACE/README.md) 和 [DAG-PACE 改进版](DAG-PACE/README.md) 使用相同的 WebWalkerQA 题目、网页快照、模型和评分器。实现说明、运行命令和结果分别放在两个目录中。

[PACE 论文](https://aclanthology.org/2026.acl-long.1252/) · [WebWalkerQA 实验进展](docs/WebWalkerQA实验进展.md)

## 最新结果 · WebWalkerQA 固定 20 题

每步可见输入预算为 6,000 token。ReAct 和标准 PACE 沿用 80,000 的网关输入停止条件。两轮新版均只记录网关用量。单源、多源各 10 题。

| 方法 | 答对 / 20 | 单源 / 多源答对 | 提交最终答案 | 全部请求 token，含重试 |
|---|---:|---:|---:|---:|
| ReAct | 6（30%） | 5 / 1 | 10 | 1,245,463 |
| 标准 PACE | 10（50%） | 6 / 4 | 18 | 2,923,460 |
| 新版 PACE（调整前） | 7（35%） | 4 / 3 | 11 | 11,942,183 |
| 新版 PACE（首步格式恢复、交卷前回看） | 10（50%） | 6 / 4 | 18 | 12,931,426 |

标准 PACE 和本轮新版各答对 10 题，其中 8 题相同。本轮多答对第 30、157 题，少答对第 15、40 题，6 次 Glimpse 均成功恢复了历史块。[本轮改动与四道差异题分析](docs/WebWalkerQA标准与新版PACE逐题对照.md) · [前期证据恢复实验](docs/WebWalkerQA新版PACE证据恢复实验.md)

## 早期窗口与压力公式消融

同一批 20 题，ReAct 答对 6 题，标准 PACE 答对 10 题，纯窗口压力 PACE 答对 7 题。两种压力公式下的 DAG-PACE 都答对 7 题。报告说明了 `glimpse` 的主动与自动触发条件、本地 token 估值与单次网关用量的区别，并逐题分析 PACE 净少的 3 分。[窗口预算与压力公式实验报告](docs/WebWalkerQA窗口预算与压力公式实验.md)
