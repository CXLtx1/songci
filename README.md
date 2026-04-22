# SongCi: AI 宋词生成与量化分析项目

一个围绕“AI 生成宋词是否会出现格律失准、表达同质化与历史借用痕迹”的研究型仓库。

这个项目把宋词生成、格律检测、意象与题材标注、同质化分析、真实宋词对照分析和最终报告写作放在了同一套工作流里。仓库中既有可运行的脚本，也保留了研究过程中形成的数据库、结果文件和长篇文档，适合继续复现、整理或扩展为公开研究项目。

## 项目能做什么

- 用多种大模型按不同提示词与实验条件批量生成宋词，并写入 SQLite 数据库
- 用自建 `SongCiEngine` 按词谱、韵书和词林正韵对生成结果进行格律评分
- 为生成结果补充意象和题材标签，形成可继续分析的结构化语料
- 从整首、句级、词牌、模型等多个层面分析 AI 宋词的同质化趋势
- 将 AI 宋词与真实宋词数据库进行对照，考察语义接近、字面借用和潜在来源
- 输出表格、统计结果、可视化和完整研究文档

## 仓库结构

```text
songci/
├── main.py                   # 统一脚本入口
├── generate/                 # 生成与标注
│   ├── generator.py
│   ├── extract_imagery.py
│   ├── prompts.py
│   ├── tasks.json
│   └── json/
├── engine/                   # 宋词格律检测引擎与规则数据
│   ├── songci_engine.py
│   ├── 词谱.json
│   ├── 韵书.json
│   └── 词林正韵.json
├── analyze/                  # 描述统计、相似性分析、真实来源分析、可视化
├── database/                 # AI 与真实宋词数据库
├── result/                   # 分析输出结果
├── docs/                     # 报告、讲稿与过程文档
├── slides/                   # 幻灯片材料
└── asset/                    # 其他素材，不公开
```

## 核心模块

### 1. 宋词生成

`generate/generator.py` 会读取 `generate/tasks.json` 中的任务配置，调用不同模型生成宋词，并将结果写入对应数据库。生成后会立刻调用 `SongCiEngine` 进行格律评估，保存分数和错误摘要。

相关文件：

- `generate/prompts.py`：实验使用的提示词模板
- `generate/tasks.json`：模型、数据库、主题、并发数等配置
- `database/*.db`：生成结果落库位置

### 2. 格律检测引擎

`engine/songci_engine.py` 是项目的核心基础设施。它会结合：

- `词谱.json`
- `韵书.json`
- `词林正韵.json`

对词作进行字数、平仄、押韵等检查，并输出可用于后续统计的格律分数与错误信息。

### 3. 结构化标注

`generate/extract_imagery.py` 用模型为已生成词作补充：

- `imagery`：意象列表
- `category`：题材类型

这一步把原始文本进一步转成可比较、可统计的结构化语料。

### 4. 分析脚本

`analyze/` 目录下包含多类研究脚本，主要可分为四组：

- `neo-rhythm-stats.py`、`neo-descriptive-stats.py`：格律与语料描述统计
- `neo-analysis.py`：AI 宋词内部同质化分析
- `neo-real-analysis.py`、`neo-real-b1-cipai-report.py`：AI 与真实宋词对照及来源分析
- `pytorch-analysis*.py`、`ai-net*.py`：较早阶段的相似性分析与网络可视化脚本

## 快速开始

### 1. 准备环境

本项目为 Python 项目，当前仓库里还没有整理出正式的依赖锁定文件。按现有脚本，通常至少需要这些库：

- `openai`
- `pandas`
- `numpy`
- `torch`
- `sentence-transformers`
- `scikit-learn`
- `networkx`
- `pyecharts`
- `beautifulsoup4`
- `requests`

如果要运行基于古诗词语义模型的分析脚本，还需要本地准备 `analyze/BERT-CCPoem-Model/`。

### 2. 配置模型与数据路径

当前生成与标注脚本默认直接从仓库内配置读取 API 信息和数据库路径：

- `generate/tasks.json`
- `generate/extract_imagery.py`

在个人研究环境中这样使用没有问题，但如果准备公开发布，建议改成环境变量或不纳入版本控制的本地配置文件。

### 3. 运行脚本

可以从统一入口启动：

```bash
python main.py
```

也可以直接运行单个模块：

```bash
python generate/generator.py
python generate/extract_imagery.py
python analyze/neo-analysis.py
python analyze/neo-real-analysis.py
```

## 主要输出

- `database/`：原始生成结果与真实宋词基线库
- `result/`：CSV、统计汇总、分析中间结果与可视化输出
- `docs/`：研究报告、PPT 内容稿、方法说明和最终整合文档

如果想快速了解项目结论和写作成果，建议优先看：

- [`docs/全项目总报告.md`](docs/全项目总报告.md)
- [`docs/新版pre完整报告.md`](docs/新版pre完整报告.md)
- [`docs/neo-ppt-content.md`](docs/neo-ppt-content.md)

## 致谢

项目分析过程中使用了宋词格律规则数据、真实宋词数据库、本地语义模型以及多家大模型服务。相关研究说明与方法文档可见 `docs/` 目录。
