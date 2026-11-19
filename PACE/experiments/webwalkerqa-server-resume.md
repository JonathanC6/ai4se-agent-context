# WebWalkerQA 暂停记录与服务器续跑

记录时间为 2026-11-19T20:07+08:00。本机已停止全部 PACE 和 ReAct 调用。题号从 1 开始，按固定版本 WebWalkerQA main 文件的行序编号。

| 组别 | 已评分 | 其中答对 | 仅待评分 | 未完成 |
|---|---:|---:|---:|---:|
| PACE | 80 | 14 | 0 | 600 |
| ReAct | 57 | 7 | 0 | 623 |

**PACE 已评分题号**　1–33、35–40、42–55、58–60、64、66、68–71、73–78、80、82–85、87–89、92、94、98、100。

**PACE 有调用或失败记录、但未保存最终结果的题号**　34、41、56–57、61–63、65、67、72、79、81、86、90–91、93、95–97、99、101–110。这些题包含在剩余题单中，服务器会从题首重跑。

**ReAct 已评分题号**　1–10、12–33、36–40、42、44–53、55–56、58–61、63–64、66。

[完整题号清单](../results/webwalkerqa-full/paused-rows.json) 保存两组的已评分、仅待评分、有尝试证据但缺结果、无本地尝试证据及全部剩余题号。未收到服务端回包的在途调用可能没有本地用量记录。当前两组的局部命中率受运行顺序和耗时影响。

## 在 Linux 服务器恢复 PACE

1. 解压迁移包，进入解压得到的 `PACE/`。其中包含本次用到的源码、固定题库、已访问的网页缓存、配置和两组逐题记录。
2. 准备 Python 3.12 虚拟环境。在 PACE 目录下执行下面的命令。本机用量化 BGE-M3 在 CPU 推理。
3. 从本机 `PACE/.cache/bge-m3-pilot/` 单独复制 `tokenizer.json` 和 `sentence_transformers_int8.onnx` 到服务器同名目录，或使用下方下载命令。文件约 586 MB。配置凭据时在服务器终端输入密钥。
4. 核对下方离线计数后启动。已有完整判分会直接跳过；缺最终结果的题会重新执行。仍使用原来的 24 步上限与同一套网页工具。网页缓存未命中的页面取自服务器访问时的公开站点，跨机器网络和页面变化可能影响结果。

```sh
python3.12 -m venv .venv
.venv/bin/pip install numpy==2.5.5 onnxruntime==1.32.0 tokenizers==0.22.2
export PYTHONPATH=src
mkdir -p .cache/bge-m3-pilot
# 已从本机复制权重时，跳过两条 curl。
base=https://huggingface.co/Xenova/bge-m3/resolve/4de13258303883538bd53b696b452bf8099f0858
curl -fL --retry 3 "$base/tokenizer.json" -o .cache/bge-m3-pilot/tokenizer.json
curl -fL --retry 3 "$base/onnx/sentence_transformers_int8.onnx" -o .cache/bge-m3-pilot/sentence_transformers_int8.onnx
sha256sum -c results/webwalkerqa-full/encoder.sha256
.venv/bin/python -m benchmarks.webwalker_full report
# Bash 下静默读取。也可用服务器已配置的 PACE_API_KEY。
read -rs -p 'Labhuan API key: ' PACE_API_KEY
echo
export PACE_API_KEY
export PACE_BASE_URL=https://api.labhuan.com/v1
.venv/bin/python -u -m benchmarks.webwalker_full run --arms pace --repeats 1 --jobs 8
.venv/bin/python -m benchmarks.pace_full_report
```

并发数 8 是服务器起步值，可按 API 限流和 CPU 负载调整。遇到服务中断，以同一条 run 命令续跑。只需使用包中的 preflight.json 和 config.json，重新生成站点预检可能导致配置与已有轨迹不一致。续跑的网页解析会编码含空格等字符的网址；对因字符串中裸引号而解析失败的模型输出，当前版本尝试恢复引号转义。上述两种修复只影响对应格式异常的调用。
