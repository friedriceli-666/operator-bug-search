# operator-bug-search

面向 GitHub 的自动化检索仓库，用于大规模收集 NVIDIA GPU 上与算子误差、错误结果、数值异常、精度回退相关的 bug 线索，并整理成可继续筛选的数据集。

当前实现重点是：

- 先广泛收集，不提前强行区分具体算子类型
- 以 GitHub 的 issue / PR / code search 为主入口
- 保留原始快照，方便后续人工复核
- 统一抽取 GPU 型号、仓库、复现代码线索、错误描述等字段

## 仓库结构

```text
operator-bug-search/
├── configs/
│   └── default_search_config.json
├── data/
│   ├── normalized/
│   └── raw/
├── src/operator_bug_search/
│   ├── cli.py
│   ├── config.py
│   ├── github_client.py
│   ├── models.py
│   ├── pipeline.py
│   ├── query_builder.py
│   └── storage.py
├── tests/
│   ├── test_pipeline.py
│   └── test_query_builder.py
└── pyproject.toml
```

## 检索设计

数据源分三类：

- GitHub Issues / Pull Requests：最容易拿到 bug 描述、环境、GPU 型号、复现步骤
- GitHub Code Search：用于补充含有 `A100` / `A800` / `wrong result` / `precision` / `numerical` 等关键词的测试程序、复现脚本、issue 链接
- Repository Search：可作为后续扩展，用于锁定框架仓库、算子库、benchmark 仓库

默认查询会组合以下维度：

- GPU 型号：`A100`、`A800`、`H100`、`H800`、`V100`、`T4`、`L40S`
- bug 关键词：`wrong result`、`incorrect output`、`accuracy`、`precision`、`numerical`、`miscompare`、`NaN`
- 领域关键词：`cuda`、`cublas`、`cudnn`、`tensorrt`、`pytorch`、`triton`

这样做的目的不是一次检索就精确命中，而是先最大化召回。

## 环境要求

- Python 3.11+
- 建议提供 `GITHUB_TOKEN`，否则 GitHub Search API 很容易撞上限流

## 快速开始

```bash
cd /home/chaofanli/operator-bug-search
python -m venv .venv
source .venv/bin/activate
pip install -e .
export GITHUB_TOKEN=ghp_xxx
operator-bug-search collect --config configs/default_search_config.json --max-pages 3
```

如果你希望直接使用仓库内已经创建好的 conda 环境：

```bash
conda activate searchbug
```

或者从环境文件重建：

```bash
cd /home/chaofanli/operator-bug-search
conda env create -f environment.yml
conda activate searchbug
```

执行后会产出：

- 原始响应：`data/raw/*.jsonl`
- 标准化样本：`data/normalized/github_findings.jsonl`
- 汇总 CSV：`data/normalized/github_findings.csv`

## 样本字段

标准化记录的核心字段包括：

- `source_type`：`issue` / `pull_request` / `code`
- `github_id`
- `html_url`
- `repo_full_name`
- `title`
- `body`
- `state`
- `labels`
- `matched_gpu_models`
- `matched_bug_keywords`
- `suspected_stack`
- `has_repro_code`
- `code_snippets`
- `query`
- `collected_at`

## 推荐工作流

第一阶段：大规模召回

- 扩充 GPU 型号列表
- 扩充 bug 关键词
- 先抓 issue / PR，再抓 code search

第二阶段：规则筛选

- 保留正文或代码中显式出现 GPU 型号的记录
- 保留正文里出现 `wrong result` / `precision` / `accuracy` / `miscompare` 的记录
- 优先保留含代码块、最小复现、测试脚本、commit 链接的记录

第三阶段：人工复核与数据集整理

- 归档复现程序
- 标注 bug 现象
- 补全环境信息和受影响 GPU
- 后续再映射到具体算子类型

## 常用命令

抓取：

```bash
operator-bug-search collect --config configs/default_search_config.json --max-pages 5
```

只抓 issue / PR：

```bash
operator-bug-search collect --config configs/default_search_config.json --targets issues,pulls
```

只抓 code search，并补充文件内容：

```bash
operator-bug-search collect \
  --config configs/default_search_config.json \
  --targets code \
  --fetch-code-content
```

指定输出目录：

```bash
operator-bug-search collect \
  --config configs/default_search_config.json \
  --output-dir ./my-data
```

断点续跑：

```bash
operator-bug-search collect \
  --config configs/default_search_config.json \
  --max-pages 5 \
  --resume
```

## 现阶段限制

- GitHub Search API 本身有速率限制，必须控制分页和查询数
- 不是每个 bug 都会直接写明算子名
- code search 命中的是“线索文件”，不一定就是最终最小复现程序
- 部分复现代码可能出现在 issue comment 中，当前实现默认抓 issue comments，但不抓完整 timeline event
- `--resume` 依赖本地 checkpoint 和已写入的 jsonl，适合单机单目录继续跑，不适合多个进程同时写同一输出目录

## 后续可以继续加的能力

- 增加 GraphQL / HTML fallback
- 自动下载 issue 中引用的 gist / 附件 / 复现脚本
- 用 LLM 或规则把 bug 现象归一化为标签
- 自动聚类相似 bug，减少重复样本
