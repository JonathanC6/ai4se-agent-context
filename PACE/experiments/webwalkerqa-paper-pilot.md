# Sonnet 4.6 · WebWalkerQA 近似对照

[论文配置与本机差异](webwalkerqa-paper-check.md) · [题单与运行配置](../results/paper-pilot/config.json)

| 方法 | 第一轮 | 第二轮 | 第三轮 | 三轮平均 | 论文表 1 |
|---|---:|---:|---:|---:|---:|
| REACT | 3/6 | 3/6 | 3/6 | 50.0% | 57.9% |
| PACE | 4/6 | 3/6 | 4/6 | 61.1% | 65.8% |

本次 PACE 相对 ReAct 的准确率差为 +11.1 个百分点。论文为 +7.9 个百分点。两份数据的样本、服务和运行环境不同，单次试跑无法判断统计等效。

## 逐题记录

1 表示判对，0 表示判错，顺序为三个轮次。

| 主测试集行号 | 类型 | 问题 | ReAct | PACE |
|---:|---|---|---|---|
| 262 | single_source | What was the other workshop held on the same day as the Workshop on Software Quality at ICSE 2002? | 0 / 0 / 0 | 0 / 0 / 0 |
| 221 | single_source | What additional content was included during the author response period at ACL 2023 to complement the new policy? | 0 / 0 / 0 | 1 / 0 / 1 |
| 201 | single_source | Which SIGCHI policy documents were updated in 2014? | 1 / 1 / 1 | 1 / 1 / 1 |
| 29 | multi_source | Which committee addresses the transition from relief to development at the NMUN Washington D.C. conference, and what is the payment deadline? | 0 / 1 / 1 | 0 / 1 / 0 |
| 514 | multi_source | Was David Notkin a member of the program committee for ICSE 2002 where he gave the keynote speech on 'ArchJava: Connecting Software Architecture to Implementation'? | 1 / 0 / 0 | 1 / 0 / 1 |
| 489 | multi_source | What is the topic and schedule of Professor Subbarao Kambhampati's lecture at the ACL 2024 conference? | 1 / 1 / 1 | 1 / 1 / 1 |

## 运行用量

token 来自远程服务回包，包含目标网页提取。量化 BGE-M3 在本机执行。

| 方法 | 平均步数 | 展示过摘要或占位符的轨迹 | glimpse | 动作 | 提取网页 | 历史摘要 | 裁判 | 合计 token | 估算费用 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| REACT | 4.67 | 0/18 | 0 | 330,215 | 200,098 | 0 | 22,043 | 552,356 | ¥1.31 |
| PACE | 4.56 | 11/18 | 0 | 241,537 | 229,226 | 123,516 | 21,358 | 615,637 | ¥1.60 |

费用按本地保存的 Labhuan 默认分组、未命中缓存的公开费率估算。逐题输出、观察与评分理由保存于本机结果目录。[模型倍率](https://api.labhuan.com/api/pricing) · [计价单位](https://api.labhuan.com/api/status)
