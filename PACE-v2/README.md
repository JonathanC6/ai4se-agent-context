# PACE-v2

独立的 WebWalkerQA 实验实现。它复用同仓库 PACE 的四级历史、BGE-M3、6K 可见输入计数和评分器。本目录提供实验入口、证据处理及 ReAct 与 v2 共用的动作接口。[三组最终逐题对照](../docs/WebWalkerQA动作接口补跑与三组对照.md) · [实验演进记录](../docs/PACE实验演进记录.md)

| 模块 | 职责 |
|---|---|
| `src/pace_v2/actions.py` | 两组共用动作格式、重试与收尾。连续格式错误时优先提交已有草稿。没有草稿时，模型依据相同可见证据用正文作答。 |
| `src/pace_v2/evidence.py` | 首次检索前拆分事实槽。保存带原文引语、数值、来源、块号的证据，检查草稿缺口以及工具返回是否补上了对应事实。 |
| `src/pace_v2/context.py` | 先调用原四级分档与预算器。仍超限时，缩短最近的观察，保留可恢复的完整块。 |
| `src/pace_v2/browser.py` | 两组共用查询缓存、题库过滤、网页归档与多窗口重读。网页正文在提取前落盘。 |
| `src/pace_v2/episode.py` | 提交前按缺失事实选择 Glimpse、Reread 或新搜索。最多两次自动复核。逐步保存草稿和复核状态，只给正式提交的答案评分。 |
| `src/pace_v2/benchmark.py` | 将固定的 20 题分别交给 ReAct 和 PACE-v2，保存配置、请求流水、逐题结果，离线汇总两组。 |

## 运行

从仓库根目录执行，使用 PACE 已安装的 Python 环境和本地 BGE-M3 权重。在线运行需要 Labhuan 凭据和可用的 You.com 服务。旧的动态查询缓存可选，相同的新查询在两组间复用。

```sh
export PYTHONPATH=PACE-v2/src:PACE/src:PACE:DAG-PACE/src
PACE/.venv/bin/python -m unittest discover -s PACE-v2/tests
PACE/.venv/bin/python -m pace_v2.benchmark run --jobs 3
PACE/.venv/bin/python -m pace_v2.benchmark report
```

五组主对照共用浏览器与可见窗口预算。已有两轮归档时，`prepare` 离线复核复用成绩，`run` 运行其余 76 条，`report` 从已落盘的结果生成配对表和 Markdown。输出目录为 `PACE-v2/results/dag-matched20/`。[首轮五组设计和数据](../docs/WebWalkerQA五组DAG首轮.md)

```sh
PACE/.venv/bin/python -m pace_v2.dag_study prepare
PACE/.venv/bin/python -m pace_v2.dag_study run --jobs 3
PACE/.venv/bin/python -m pace_v2.dag_study report
```

完整运行默认写入 `PACE-v2/results/matched20-actions-v2/`。旧协议归档在 `matched20-facts-v1/`。只补跑旧归档中标为执行异常的“题号、方法”组合时，运行以下命令。

```sh
prior=PACE-v2/results/matched20-facts-v1
out=PACE-v2/results/matched20-actions-v2-retry
PACE/.venv/bin/python -m pace_v2.benchmark run --retry-failures-from "$prior" --out "$out" --jobs 3
PACE/.venv/bin/python -m pace_v2.benchmark report --retry-failures-from "$prior" --out "$out"
```

两组都保留 6K 可见输入预算。动作重试仍失败时，已有草稿可以提交。没有草稿时，收尾请求仅替换系统指令，沿用当前问题和已经可见的证据。首次收尾达到输出上限会再请求一次短答，并标记提交路径。两次均未得到可用文本时记录 `no_valid_answer`，计 0 分。搜索服务报错时，有草稿就提交，否则将错误作为工具观察交回模型。两组使用原裁判。

`comparison.json` 按题标明成绩来源和提交路径。补跑时，`selected_tokens` 汇总最终采用的轨迹，`rerun_tokens` 是本次新增开销，`tokens_by_role` 则计入首轮和补跑的全部请求。旧归档单独保留。

公共记录器现在对所有模型角色记录客户端可见输入及输出，同时保留网关原始 usage。新报告的 `selected_metering_by_role` 按角色给出可见用量及各字段覆盖的响应数。旧归档可用 `python -m pace_v2.token_audit` 离线重建输入。[用量定义与复核结果](../docs/WebWalkerQA用量复核.md)

## 统一 20 题的五组运行

组名依次为 `react`、`pace`、`dag-pace`、`pace-v2`、`pace-v2-dag`。最新版 PACE 和独立 v2 的实验引擎分别来自 `benchmarks.paper_pilot` 与 `pace_v2.episode`，两个 DAG 组加载同一个 `dag_pace.strategy.DependencyStrategy`。新运行的 ReAct 用后一个引擎的全文分支。[题目、五组配置、逐题归因](../docs/WebWalkerQA五组DAG对照.md)

离线复核分数和各角色的本地输入，直接读取 [100 行结果表](experiments/webwalkerqa-unified20.csv)。每行对应一道题与一个系统。correct 留空表示工具异常缺测，0 表示判错（含预算内未交卷），1 表示判对。visible_input 为采用轨迹的输入，discarded_fresh_input 为六题在线批次中未采用尝试的额外输入。

服务器重放这次调度需要固定版本的数据集、BGE 模型资产、既有的 `results/dag-matched20/comparison.json` 和 `shared-search/`。在原部署根目录执行，变量 `PACE_API_KEY` 由调用者注入。第一次运行六道在线题，首轮并发三路。已有评分会复用，剩余组合最多串行再试两轮。report 读取已有结果，无需模型调用。

```sh
export PYTHONPATH=PACE-v2/src:PACE/src:PACE:DAG-PACE/src
.venv/bin/python -m pace_v2.replacement_study plan
printf '%s\n' "$PACE_API_KEY" | .venv/bin/python PACE-v2/ops/start.py --study unified
.venv/bin/python -m pace_v2.replacement_study report
```

输出目录为 `PACE-v2/results/matched20-unified-ddg/`。自动报告留在该目录，仓库 docs 中保留经轨迹核对的分析。
