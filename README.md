# Agent 上下文实验

[PACE 基线](PACE/README.md) 和 [DAG-PACE 改进版](DAG-PACE/README.md) 使用相同的 WebWalkerQA 题目、网页快照、模型和评分器。实现说明、运行命令和结果分别放在两个目录中。

[PACE 论文](https://aclanthology.org/2026.acl-long.1252/) · [WebWalkerQA 实验进展](WebWalkerQA实验进展.md)

## 6,000 token 窗口下的 WebWalkerQA 对照

同一批 20 题，ReAct 答对 6 题，标准 PACE 答对 10 题，纯窗口压力 PACE 答对 7 题。两种压力公式下的 DAG-PACE 都答对 7 题。报告说明了 `glimpse` 的主动与自动触发条件、本地 token 估值与单次网关用量的区别，并逐题分析 PACE 净少的 3 分。[窗口预算与压力公式实验报告](WebWalkerQA窗口预算与压力公式实验.md)
