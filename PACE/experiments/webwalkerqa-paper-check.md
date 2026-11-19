# WebWalkerQA 与 PACE 表 1 的核对

2026-11-19。表 1 最右列是 WebWalkerQA。Claude-4-Sonnet 下，ReAct 为 57.9%，Summary 为 61.7%，Folding 为 60.9%，PACE 为 **65.8%**。附录 E 说明 WebWalkerQA 报告三次独立运行的平均答案准确率。[表 1 与附录 A、D、E](https://aclanthology.org/2026.acl-long.1252.pdf)

| 项目 | 论文 | 此前本机 PACE 基线 |
|---|---|---|
| 动作模型 | Claude-4-Sonnet，经 Anthropic 官方 API，论文未给日期 ID | 经 Labhuan 的 claude-sonnet-4-6 |
| 历史块摘要 | Gemini 2.5 Flash-Lite | claude-sonnet-4-6 |
| 语义编码 | BGE-M3 | GLM-Embedding-3 |
| 压力与分档 | 128K 预算，任务长度尺度来自验证轨迹的第 95 百分位，阈值 0.4 / 0.8 / 1.5，λ=0.5，τ=0.3 | 相同名义预算与分档参数，步数尺度固定为 16，每题最多执行 16 步 |
| 浏览 | Google 前 10 条含摘要结果；Visit 通过 You.com 获取页面，再按访问目标提取证据。附录 D 另列学术检索、文件解析和沙箱工具 | 冻结站点 BM25 前 8 条标题与网址，每次访问读取至多 4,200 字符 |
| 评判 | GPT-4o-2024-08-06，按 WebWalkerQA 规范判断答案 | Claude 独立评分，课程版提示 |
| 题单与重复 | 官方 main 有 680 题；论文未公布逐题清单或三轮明细 | 从七个站点选出的 40 题，各一次，13 题的标注来源页未全部收录 |

本机已有的 40 条 PACE 轨迹为 **13/40（32.5%）**，其中来源页齐全的子集为 13/27。此结果用于课程四组的内部比较。目前不能据此判断复现的 benchmark 性能是否与论文一致。[官方数据](https://huggingface.co/datasets/callanwu/WebWalkerQA) · [四组结果](../../DAG-PACE/experiments/ablation40.md)

## 本次实际核查

- 在当前账号查询模型列表并逐项发送最小请求。claude-sonnet-4-6 成功；claude-sonnet-4-20250514、gemini-2.5-flash-lite、gpt-4o-2024-08-06 均未出现在该列表中，本次调用均返回 HTTP 503。Anthropic 官方列出的 Sonnet 4 快照于 2026-06-15 退役。[模型生命周期](https://platform.claude.com/docs/en/docs/about-claude/model-deprecations)
- 目前项目只有 Labhuan 的本地配置；未发现已配置的 You.com、Google 搜索、Gemini 或独立 GPT-4o 裁判凭据。核查开始时本机没有 BGE-M3 权重，后续小样本试跑已缓存 INT8 版本。
- 对 40 条已有轨迹，从记录的 cosine 和压力独立重算权重、阈值和预算调整前的基础档位。375/375 个决策步的阈值一致，1,481/1,481 次旧块权重与分档一致。此核查从已记录的 cosine 开始，没有验证原论文 BGE-M3 向量、工具返回、作者提示或最终准确率。
- 若按公开 main 的全部 680 题与三轮口径规划，共 2,040 条轨迹。旧的 40 条使用另一套配置，不能并入新实验的分母。本次未启动该批量运行。


## 近似对照的预设条件

用户接受替代模型后，两臂新跑相同的六题。候选来源为七个已有站点快照与固定版本的官方主测试集。筛掉未收齐标注来源 URL 的题，按固定盐值和行号的 SHA-256 排序，各题型从不同站点取三题。筛选只读取题号、站点、题型和来源 URL，参考答案与来源标注不进入求解提示。固定行号为单源 262、221、201，多源 29、514、489。四题与之前的课程题重合，所有预测均重新生成。

- 两臂均用 Labhuan Sonnet 4.6 执行动作、按访问目标提取网页、独立评分，PACE 的异步历史摘要也用 4.6。WebWalkerQA 是唯一测试集。每题每臂重复三次，共 36 条轨迹。三轮均使用温度 0，未指定随机种子，重复的独立 API 会话不等于论文的三个不同种子。
- PACE 稠密编码使用固定版本 BGE-M3 的第三方 INT8 ONNX 转换，本机执行 1,024 维编码；最多 8,192 个分词 token。通过相同的 PACE 预算器，保持最近两块全文。ReAct 始终显示全部历史，关闭 glimpse，不生成历史摘要。[量化模型](https://huggingface.co/Xenova/bge-m3/tree/4de13258303883538bd53b696b452bf8099f0858/onnx)
- 128,000 输入预算，调用前以字节保守估算，调用后采用服务端 token 反馈。剔除与试跑重叠的四题，用既有 36 条最多 16 步的基线轨迹估出第 95 百分位为 16。它仍受旧轨迹步数截断影响。另设 24 步执行上限。
- 搜索覆盖同一冻结站点的网页，BM25 返回前十条标题、网址和片段；Visit 将页面文本和访问目标发给独立模型调用，返回提取依据、证据与摘要。每次输入最多 24,000 个字符，可用 offset 继续读取。试跑没有 Google 实时搜索、You.com、Python、Scholar 或文件解析服务。
- 每次执行保留逐步动作、展示档位、原始观察、最终答案、判分理由和按角色累计的 API token。题目是配对单位，三轮重复无法将六道题变成十八道独立题。

在 `PACE/` 目录使用已准备好的本机环境运行：

```sh
PYTHONPATH=src .venv/bin/python -m benchmarks.paper_pilot --jobs 6
```

新环境需要 Python 3.10+、NumPy、tokenizers 和 onnxruntime。将固定模型版本中的 `tokenizer.json` 和 `onnx/sentence_transformers_int8.onnx` 按各自文件名放入 `.cache/bge-m3-pilot/`；两个文件合计 585,681,892 字节。原始轨迹和配置在 `results/paper-pilot/`，使用相同命令可续跑。

## 本次结果如何解读

按原始裁判记录，PACE 三轮共答对 11/18，ReAct 答对 9/18。分题型看，PACE 单源 5/9、ReAct 单源 3/9，多源两组均为 6/9。第 221 题贡献两次净胜，裁判对“作者回复期开始后”与“作者回复期间”的措辞有不同解读。第 514 题贡献一次净胜，六份回答都确认 David Notkin 是程序委员会成员，同时质疑题干的主题演讲前提，判分却有正有负。第 29 题 PACE 少答对一次，两组回答对不同年份的委员会主题作了不同限定。其余三题没有胜负差。以上分析保留原始判分。

PACE 有 11/18 条轨迹向动作模型展示过压缩历史，三轮合计主动调用 glimpse 0 次。动作模型消耗的 token 减少了 26.9%，计入摘要、网页提取和裁判后，总量增加了 11.5%。这批题观察到了压缩效果，但题目数量和判分敏感性限制了准确率结论。[逐题结果与用量](webwalkerqa-paper-pilot.md)
