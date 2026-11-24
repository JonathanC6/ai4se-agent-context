# WebWalkerQA 20 题网页工具对照

固定在首轮 ReAct 与 PACE 都已判分的 54 题中抽样。单源和多源分别按 SHA-256(`webwalker-tools20-v1/{官方行号}`) 升序取前 10。选择不使用答案、对错或网页命中信息。完整候选池和题号见[题单](../benchmarks/webwalker_tools20.json)。

| 旧工具 | 正确 | 至少读取一个标注页 | 读齐该题标注页 | 读到的标注页 / 题内标注页总数 |
|---|---:|---:|---:|---:|
| ReAct | 4/20 | 9/20 | 6/20 | 11/30 |
| PACE | 4/20 | 10/20 | 6/20 | 12/30 |

旧结果复用暂停时轨迹。两端共用同一套 URL 匹配规则，忽略协议、www、片段和末尾斜杠，保留路径及查询。只统计收到正文并完成目标提取的 visit，搜索片段、未打开的链接和空页均不计。等价镜像可能漏计。逐题数据由 report 生成。

新搜索用 Serper 查询 Google，按查询语言切换中美地区，每条最多 10 个标题、摘要、URL；visit 调用 You.com Contents 返回 Markdown，再按目标提取。保留基线的 24,000 字符窗口与 offset、Sonnet 4.6、温度 0、24 步、128K、旧版裁判、同一轮数。PACE 沿用原编码器、摘要模型及长度尺度。新旧运行日期不同，无法控制网站更新。公开搜索可能返回题库镜像，解释新增正确题时应核对来源。

开始前约定 ReAct 满 20 题且至少答对 10 题（50%）时继续同题 PACE。论文 ReAct 为 57.9%；该门槛只决定是否追加实验。凭据或接口失败可修复后续跑，已保存的题将复用。模型、搜索和网页读取均可能产生费用。

在 PACE 目录执行。搜索和读取凭据使用环境变量 SERPER_API_KEY、YDC_API_KEY，或放入已忽略的本地配置 .local.json，字段分别为 serper_api_key、you_api_key。模型凭据继续用原配置。

```sh
PYTHONPATH=src .venv/bin/python -m benchmarks.webwalker_tools20 report
PYTHONPATH=src .venv/bin/python -m benchmarks.webwalker_tools20 run
```

结果位于 results/webwalker-tools20/。comparison.json 保存各题新旧正确性、命中页数和汇总。当前只有旧轨迹的实测数。

## 仅配置 Labhuan 密钥的实测

模型仍用 Labhuan Sonnet 4.6。浏览通过 You.com 官方公开 MCP 入口执行：you-search 取前十条 URL、标题和摘要，you-extract 读取 Markdown。You.com 和 Google 的排序不同。该运行独立保存于 `results/webwalker-tools20-you-public/`，沿用同一批题、评分器和 PACE 启动门槛。在 PACE 目录执行以下命令可以续跑或重建对照。

```sh
PYTHONPATH=src .venv/bin/python -m benchmarks.webwalker_tools20 run --public-you --jobs 4
PYTHONPATH=src .venv/bin/python -m benchmarks.webwalker_tools20 report --public-you
```

### 2026-11-23 实测结果

19 道共同有判分的题包括 10 道单源、9 道多源。第 50 题的 You.com 正文读取返回免费额度已用尽，未形成最终答案与判分。没有将其计错。

| 同题指标 | 旧 ReAct | 新 ReAct |
|---|---:|---:|
| 正确 | 4/19 | 6/19 |
| 单源 / 多源正确 | 4/10 · 0/9 | 5/10 · 1/9 |
| 至少读到一页 | 8/19 | 11/19 |
| 读齐标注页 | 6/19 | 10/19 |
| 读到的标注页 | 10/28 | 17/28 |

仅第 47、59 题由错转对。第 47 题读取 EHA 官网任命公告，URL 与标注不同；第 59 题从只命中一张标注页变成两张都读到，答对主席和联系邮箱。第 9 题仍把 7 月 3 日的补助截止日期答成 7 月 1 日；第 25 题仍无法确认历史届次的两个期限。公开搜索在第 2、15 题展示了可识别的 WebWalkerQA 题库链接，两题均未访问这些链接。排除这两题后，旧 3/17，新 5/17。该检查基于链接与标题，无法排除未知镜像。

19 条完整轨迹共 101 步、970,748 个 Labhuan token；含第 50 题中断前的调用，用量日志合计 987,454 个 token（不含连通测试）。固定 20 题的最终得分只能在 6/20 到 7/20 之间，低于预设门槛 10/20。本轮没有启动 PACE。
