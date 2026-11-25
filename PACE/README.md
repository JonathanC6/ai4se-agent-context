# PACE

PACE 在每次调用 agent 前，决定哪些历史交互需要全文、详细摘要、简短摘要或仅保留 ID。完整记录始终留在外部记忆中，agent 可用 `glimpse` 恢复原文。[论文](https://aclanthology.org/2026.acl-long.1252/)

![PACE 的决策与记忆循环](docs/architecture.png)

## 快速运行

在 `PACE/` 下执行。离线示例只需 Python 标准库。下面的在线实验在 Python 3.12 上运行。托管版从环境变量 `PACE_API_KEY` 或本机私有的 `.local.json` 读取凭据，默认地址为 `https://api.labhuan.com/v1`。

```sh
export PYTHONPATH=src
python3 -m pace demo
python3 -m pace run --encoder api --output results/smoke.json
```

WebWalkerQA 默认用 `claude-sonnet-4-6` 生成动作、两级摘要和评分，独立评分会话只看题目、参考答案和预测。早期冻结站点实验使用 `GLM-Embedding-3`，现行在线实验使用本地 BGE-M3 INT8。单任务 CLI 的 `--encoder bge`（其默认值）使用本地 BGE-M3，需要另装 `requirements-bge.txt`。若有 NumPy，余弦计算使用矩阵乘法。

## 模块与数据流

| 路径 | 职责 |
|---|---|
| `src/pace/agent.py` | 执行一个工具动作，生成观察，将本轮 TAO 写入记忆，或用 finish 提交答案。 |
| `src/pace/memory.py` | 保留全文与向量，后台生成两级摘要，为 glimpse 提供全文。 |
| `src/pace/context.py`、`policy.py` | 将原问题和最近两块组成查询，对旧块算余弦和相对权重，按压力选粒度，最后按时间顺序拼接。 |
| `src/pace/providers/` | `api.py` 管理托管请求与 token 用量，`encoding.py` 管理向量和 token 估算。 |
| `benchmarks/` | 冻结站点、提供 search/visit、选择题目、执行与评分。逐步轨迹写入 `results/`。 |

旧块权重为 `M × softmax(cos / 0.3)`。最近两块保留全文，旧块按相关度与压力分档。单次 `glimpse` 最多恢复三块。6K 实验用本地估值安排可见上下文，逐请求读取 Labhuan 的 `usage` 统计开销并检查 80K 网关保护上限。[两种压力公式、回看机制与逐题结果](../WebWalkerQA窗口预算与压力公式实验.md)

## 在线对照实验

新环境使用 Python 3.12，首次运行准备两个 BGE-M3 文件，合计约 586 MB。基准会自动下载并校验固定版本的 WebWalkerQA。

```sh
python3.12 -m venv .venv
.venv/bin/pip install numpy==2.5.5 tokenizers==0.22.2 onnxruntime==1.32.0 -r requirements-reader.txt
model_url=https://huggingface.co/Xenova/bge-m3/resolve/4de13258303883538bd53b696b452bf8099f0858
mkdir -p .cache/bge-m3-pilot
curl -fL "$model_url/tokenizer.json" -o .cache/bge-m3-pilot/tokenizer.json
curl -fL "$model_url/onnx/sentence_transformers_int8.onnx" -o .cache/bge-m3-pilot/sentence_transformers_int8.onnx
export PYTHONPATH=src:../DAG-PACE/src
.venv/bin/python -m unittest discover -s tests
```

### 窗口和压缩启动时机

以下命令运行报告里的五组和同一份修订题单。窗口预算由 `--budget` 指定，默认 6,000。每题最多 24 步，动作模型、网页提取、历史摘要和裁判均使用 Labhuan 的 Claude Sonnet 4.6。首次在线运行前需按下节配置检索服务。

```sh
study_dir=results/webwalker-window-study-matched20
.venv/bin/python -m benchmarks.window_study --budget 6000 --jobs 4 --out "$study_dir" \
  --replace-row 32 115 --replace-row 42 157 --replace-row 50 407 \
  --groups react pace dag-pace pace-window dag-pace-window
.venv/bin/python -m benchmarks.window_study_report --out "$study_dir" \
  --groups react pace dag-pace pace-window dag-pace-window
.venv/bin/python -m benchmarks.window_study_replay --results "$study_dir" \
  --groups pace dag-pace pace-window dag-pace-window --out "$study_dir/pressure-replay.json"
```

五组全部评分后生成 `pressure-comparison.json`。离线回放生成 `pressure-replay.json`，列出固定同一条历史、只切换公式时，哪些步骤展示了不同的块粒度。相同配置和输出目录可续跑，用 `--rows` 可指定其中几题。更换预算或题单时另用新目录。`benchmarks.window_study_calibration` 可在保留上轮轨迹的机器上复算预算选择。

### 检索与取证

| 工具 | 当前在线实验 |
|---|---|
| `search(query)` | agent 每步可改写查询。每个查询最多返回 10 条标题、摘要和完整 URL，过滤题库镜像和转载标准答案。相同查询复用第一次的排序。 |
| `visit(url, goal)` | 从题目入口、搜索结果或已发现链接访问页面。优先用 You.com 取得 Markdown，失败后直读网页或用 pypdf 提取 PDF 文字。指定 `as_of` 会请求离目标日期最近的 Wayback 快照。长文按目标选取最多 24,000 字符交给提取模型，也可指定起始位置。 |
| `reread(source_id, goal)` | 从本题已读页面的原文快照重新提取证据，可按关键词或字符位置换段。 |
| `glimpse(ids)` | 两组 PACE 可恢复已存储的完整历史观察。只恢复一个访问块时，也可附上新目标，通过该块的原文快照重新提取。 |

论文附录 D 使用 Google 搜索、You.com 读取，还列出 PythonInterpreter、GoogleScholar 和 ParseFile。本实验覆盖网页检索、正文与文本 PDF 读取。搜索设置 `SERPER_API_KEY` 时使用 Google Serper。缺少该密钥时使用公开网页搜索桥接。You.com 读取可设置 `YDC_API_KEY`，缺省调用其公开 MCP 接口。每次实际使用的读取服务和回退原因记录在 `reader-题号.jsonl`。相同提供方、URL 和快照日期的原文或访问失败会冻结在 `.cache/research-web-v1/pages/`，三组后续访问共用。

使用公开搜索时，需要有一个能访问搜索引擎的进程处理未命中的查询。在另一个终端从 `PACE/` 执行以下命令。按原始查询检索，保留提供方的排名，以 `[{"query":"原始查询","results":[{"title":"网页标题","snippet":"搜索摘要","url":"链接"}]}]` 格式保存到 `/tmp/search-results.json` 后回填。桥接程序按查询缓存并过滤结果。若希望全程自动运行，可直接配置 Serper。

```sh
export PYTHONPATH=src
.venv/bin/python -m benchmarks.webwalker_dynamic20 pending
.venv/bin/python -m benchmarks.webwalker_dynamic20 answer < /tmp/search-results.json
```

## WebWalkerQA 20 题

在 `PACE/` 下执行。首次准备下载固定版题库与三个会议站点的网页。已有快照会复用，两组共用相同文件。ICSE 公开站点无 sitemap，从首页按层收集最多 120 个同站 HTML 页面。

```sh
export PYTHONPATH=src
python3 -m benchmarks.webwalkerqa prepare
python3 -m benchmarks.webwalkerqa prepare --root https://www2024.thewebconf.org/ --snapshot .cache/webwalkerqa/www2024.json
python3 -m benchmarks.webwalkerqa prepare --root https://www.icse-conferences.org/ --snapshot .cache/webwalkerqa/icse.json
python3 -m benchmarks.paired --jobs 4
```

[固定题单](benchmarks/paired20.json) 含 10 道单源及 10 道多源题。每题上限 16 步，输入预算 128,000。search 通过 BM25 返回最多 8 个页面标题和网址，visit 每次读取最多 4,200 字符。每题记录动作、展示粒度、答案、判分、分类用量和耗时。按原命令续跑会跳过已评分题。新采样应指定不同的 `--out`。[本组实测](experiments/paired20.md) · [两组对照](../DAG-PACE/experiments/comparison.md)

## 对照论文表 1

[配置核对](experiments/webwalkerqa-paper-check.md) · [Sonnet 4.6 六题三轮配对结果](experiments/webwalkerqa-paper-pilot.md)。两臂共用网页工具和裁判；PACE 使用本机 BGE-M3 INT8，ReAct 保留全部交互。运行条件、选题规则及与原论文的差异见配置核对。完成运行后，`PYTHONPATH=src .venv/bin/python -m benchmarks.paper_pilot_report` 可从原始轨迹重建结果表。

## 完整 WebWalkerQA main

完整题单有 680 题，单源和多源各 340 题。先检查 138 个公开站点的入口，再运行付费模型。下面的命令在 `PACE/` 下执行。

```sh
export PYTHONPATH=src
.venv/bin/python -m benchmarks.full_webwalker_preflight
.venv/bin/python -m benchmarks.webwalker_full run --arms pace --repeats 1 --jobs 6
.venv/bin/python -m benchmarks.webwalker_full report
```

可用 `--repeats 3` 追加第二、三轮，或用 `--arms pace react` 加入配对基线。每题从官方入口起步，search 对已发现的站内链接排序，visit 读取并按目标提取网页，支持继续发现链接。成功读取的页面在本机缓存。本模式的站内导航与论文的 Google + You.com 工具不同；网页版本也会影响得分。模型、步数上限、BGE 编码及上下文参数沿用六题试跑。

`results/webwalkerqa-full/` 保存入口检查、逐题答案、轨迹、用量和裁判结果。模型或裁判中断的题可用原命令续跑；访问错误保存在工具观察里，每轮收齐 680 个判分才输出全量准确率。试跑的六题结果独立保存。

新实验默认使用 `semantic-v2` 评分。独立的中英文日期可以直接比对，例如“三月十四日”和“It is March 14th.”。其余答案由裁判逐项核对题目要求，接受等义翻译、同义表达和相容的补充信息。每个判分记录带有版本。已有实验目录沿用原裁判口径。

完整 main 的新实验使用 `full-live-v2` 浏览工具。搜索只返回有词项匹配的链接，访问页面仍可浏览导航链接。HTML 主区只有空白时会回退到可见文本。要在同一台机器上建立独立实验，在 `webwalker_full run` 和 `report` 后传入相同的新目录，例如 `--out results/webwalkerqa-v2`。旧目录继续使用 v1 浏览缓存与行为。新保存的 PACE 轨迹按块记录摘要正文，结合每步的 `shown` 可还原当时展示的块。

固定 20 题的 ReAct 自主浏览实验增加了历史快照与 PDF 读取，保留逐题答案、网页访问及模型用量。[运行方法与配对结果](experiments/webwalker-archive20.md)

固定 20 题的动态搜索、16K 实验使用本地预训练 BGE-M3（INT8 ONNX，1024 维）。标准压力倍率为 `1 + 0.5 * P`。要在已有轨迹上核对平方变体 `1 + 0.5 * P²` 如何改变实际展示的块，在 `PACE/` 下运行 `PYTHONPATH=src .venv/bin/python -m benchmarks.replay_pressure`，无需 API。单任务入口也支持 `--pressure-power 2`。

要验证“步数多、窗口仍空”的情况，可用 `PYTHONPATH=src .venv/bin/python -m benchmarks.replay_pressure --variant occupancy` 免费回放已有轨迹。端到端实验入口为 `benchmarks.webwalker_budget20 --groups pace-occupancy --rows 1 48`，使用与标准组相同的 Labhuan 配置及动态搜索服务。单任务入口支持 `--pressure-mode occupancy`。
