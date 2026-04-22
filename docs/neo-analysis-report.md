# AI 宋词内部同质化与内容收缩分析报告

## 1. 研究目标

本报告的核心目标是回答：

**不同大模型在不同创作约束与不同 prompt 结构下，生成宋词的内部同质化程度如何变化；这种同质化具体收缩到了哪些词牌、主题类型与意象系统。**

这里的“内部同质化”不是简单看两首词是否相似，而是综合考察：

- 同一模型在同一条件下生成的作品，是否在整体语义上越来越接近
- 是否在句级表达和局部模板上出现重复
- 是否反复调用高度重合的主题类型与意象资源

因此，本报告分为两层：

- 相似性分析：证明“同质化存在且可量化”
- 描述性统计：解释“同质化具体收缩到了什么内容层”

---

## 2. 数据与实验条件

本研究分析 6 个 AI 数据库，并使用 [real_song_ci_dataset.db](/D:/文件/Projects/songci/database/real_song_ci_dataset.db) 作为真实宋词基线。

| 数据库 | 条件说明 | prompt 类型 |
|---|---|---|
| `a1` | 不限制词牌，不限制主题，自由生成 | `type_c` |
| `b1` | 固定五词牌，无主题 | `type_b` |
| `b2` | 固定五词牌，改革主题 | `type_d` |
| `b3` | 固定五词牌，玉兰主题 | `type_d` |
| `c1` | 固定 `沁园春`，玉兰主题 | `type_a` |
| `c2` | 固定 `沁园春`，改革主题 | `type_e` |

其中：

- `b1/b2/b3` 的五个固定词牌为 `菩萨蛮 / 沁园春 / 清平乐 / 祝英台近 / 浪淘沙`
- `c1/c2` 全部固定为 `沁园春`

---

## 3. Prompt 结构说明

本报告中的 prompt 解释基于 [generate/prompts.py](/D:/文件/Projects/songci/generate/prompts.py) 的实际模板。

### 3.1 `type_c`

对应 `a1`。

特点：

- 模型自行选择词牌
- 不指定主题
- 要求输出完整、符合格律、尽量多样、尽量避免抄袭

这是最自由的一组数据，用来观察模型在弱约束下的自发收缩倾向。

### 3.2 `type_b`

对应 `b1`。

特点：

- 指定词牌
- 不指定主题
- 强调格律、完整性、多样性、创新性与避免抄袭

它主要用于测量：**仅增加词牌约束后，模型内部同质化是否上升。**

### 3.3 `type_d`

对应 `b2` 和 `b3`。

特点：

- 指定词牌
- 指定主题与背景
- 明确强调“发挥创造力”“体现文学之美”“尽可能不要抄袭”

它是在 `type_b` 的基础上加入主题与背景，因此主要用于测量：

- 主题本身是否压缩表达空间
- 即使 prompt 明确要求创造力，主题约束是否仍会推高同质化

### 3.4 `type_a`

对应 `c1`。

特点：

- 固定 `沁园春`
- 指定玉兰主题与背景
- 明确强调多样性、创造力、文学性、避免抄袭
- 同时直接提供了 `沁园春` 的详细格律参考模板

因此 `type_a` 不只是“固定词牌 + 固定主题”，还是一种：

**带显式格律骨架提示的强约束 prompt。**

### 3.5 `type_e`

对应 `c2`。

特点：

- 固定 `沁园春`
- 指定改革主题与背景
- 强调用韵与格律
- 没有 `type_d/type_a` 中“发挥创造力”“体现文学之美”“尽可能不要抄袭”的那段引导
- 也没有 `type_a` 中那样直接给出详细格律模板

因此 `type_e` 的特点可以概括为：

- 结构约束仍强
- 但创作引导更短、更硬、更结果导向

这一点对后文解释 `c2` 的内容收缩方式很重要。

---

## 4. 分析框架与指标

### 4.1 相似性分析结果来源

严格主分析结果来自：

- [neo_model_summary.csv](/D:/文件/Projects/songci/result/neo-analysis/neo_model_summary.csv)
- [neo_cipai_summary.csv](/D:/文件/Projects/songci/result/neo-analysis/neo_cipai_summary.csv)
- [neo_condition_deltas.csv](/D:/文件/Projects/songci/result/neo-analysis/neo_condition_deltas.csv)
- [neo_low_sample_models.csv](/D:/文件/Projects/songci/result/neo-analysis/neo_low_sample_models.csv)

观察分析结果来自：

- [neo_model_summary_observe.csv](/D:/文件/Projects/songci/result/neo-analysis/neo_model_summary_observe.csv)
- [neo_condition_deltas_observe.csv](/D:/文件/Projects/songci/result/neo-analysis/neo_condition_deltas_observe.csv)

### 4.2 描述性统计结果来源

描述性统计结果来自：

- [a1_model_cipai_distribution.csv](/D:/文件/Projects/songci/result/descriptive-stats/a1_model_cipai_distribution.csv)
- [a1_model_cipai_summary.csv](/D:/文件/Projects/songci/result/descriptive-stats/a1_model_cipai_summary.csv)
- [category_distribution_by_db.csv](/D:/文件/Projects/songci/result/descriptive-stats/category_distribution_by_db.csv)
- [category_distribution_by_db_model.csv](/D:/文件/Projects/songci/result/descriptive-stats/category_distribution_by_db_model.csv)
- [category_summary_by_db_model.csv](/D:/文件/Projects/songci/result/descriptive-stats/category_summary_by_db_model.csv)
- [imagery_top_by_db.csv](/D:/文件/Projects/songci/result/descriptive-stats/imagery_top_by_db.csv)
- [imagery_top_by_db_model.csv](/D:/文件/Projects/songci/result/descriptive-stats/imagery_top_by_db_model.csv)
- [imagery_summary_by_db_model.csv](/D:/文件/Projects/songci/result/descriptive-stats/imagery_summary_by_db_model.csv)
- [imagery_overlap_between_dbs.csv](/D:/文件/Projects/songci/result/descriptive-stats/imagery_overlap_between_dbs.csv)

### 4.3 同质化指标含义

本研究把同质化拆成三层：

#### 整词语义层

- `whole_sem_p50`：整首词语义相似度中位数
- `whole_sem_p90`：整首词高相似尾部水平
- `whole_highsim_ratio`：高相似整词对比例

整词语义层综合分：

```text
whole_score
= 0.50 * whole_sem_p50
+ 0.30 * whole_sem_p90
+ 0.20 * whole_highsim_ratio
```

它衡量的是：**同一模型是不是整体越来越在“写同一种东西”。**

#### 句级模板层

- `top1_sent_mean`：每对词最强句匹配的平均相似度
- `topk_sent_mean`：每对词前 k 个最佳句匹配的平均相似度
- `sent_highsim_ratio`：高相似句覆盖率
- `sent_pseudo_ratio`：高语义差值句覆盖率

句级模板层综合分：

```text
sent_score
= 0.40 * sent_highsim_ratio
+ 0.30 * sent_pseudo_ratio
+ 0.30 * top1_sent_mean
```

它衡量的是：**局部句法骨架和表达模板是否重复。**

#### 意象系统层

- `imagery_jaccard_p50`
- `imagery_jaccard_p90`
- `imagery_entropy`
- `top10_imagery_concentration`
- `category_entropy`

意象系统层综合分：

```text
imagery_score
= 0.35 * imagery_jaccard_p50
+ 0.25 * imagery_jaccard_p90
+ 0.20 * top10_imagery_concentration
+ 0.10 * (1 - imagery_entropy)
+ 0.10 * (1 - category_entropy)
```

它衡量的是：**模型是否反复调用同一套意象资源和题材归类。**

### 4.4 综合指标

主报告使用两个综合指标：

```text
core_mihi
= 0.55 * whole_score
+ 0.45 * sent_score
```

```text
mihi_full
= 0.45 * whole_score
+ 0.35 * sent_score
+ 0.20 * imagery_score
```

其中：

- `core_mihi` 更稳定，便于和真实宋词做比较
- `mihi_full` 信息更完整，适合解释意象层收缩

### 4.5 人类基线

- `human_core_mihi`
- `excess_core_homogeneity = core_mihi - human_core_mihi`

`excess_core_homogeneity` 为正，表示 AI 在相同词牌范围内比真实宋词更集中、更同质化。

---

## 5. 严格主分析：同质化如何随约束上升

严格主分析使用 `rhythm_score >= 80` 的样本。

### 5.1 同一条件下的模型结果

#### `b1`：固定五词牌，无主题，`type_b`

| 模型 | `mihi_full` | `core_mihi` |
|---|---:|---:|
| qwen3.6-plus | 0.506810 | 0.606351 |
| doubao-seed-2.0-pro | 0.490574 | 0.589825 |
| deepseek-3.2-thinking | 0.450301 | 0.545057 |
| glm-5 | 0.439374 | 0.528483 |

#### `b2`：固定五词牌，改革主题，`type_d`

| 模型 | `mihi_full` | `core_mihi` |
|---|---:|---:|
| doubao-seed-2.0-pro | 0.517539 | 0.616483 |
| qwen3.6-plus | 0.513706 | 0.617956 |
| deepseek-3.2-thinking | 0.464420 | 0.555794 |

#### `b3`：固定五词牌，玉兰主题，`type_d`

| 模型 | `mihi_full` | `core_mihi` |
|---|---:|---:|
| doubao-seed-2.0-pro | 0.531132 | 0.625642 |
| deepseek-3.2-thinking | 0.522939 | 0.584171 |
| qwen3.6-plus | 0.518089 | 0.600654 |

#### `c1`：固定 `沁园春`，玉兰主题，`type_a`

| 模型 | `mihi_full` | `core_mihi` |
|---|---:|---:|
| doubao-seed-2.0-pro | 0.636859 | 0.767388 |
| deepseek-3.2-thinking | 0.630861 | 0.724666 |
| qwen3.6-plus | 0.595676 | 0.708682 |

#### `c2`：固定 `沁园春`，改革主题，`type_e`

| 模型 | `mihi_full` | `core_mihi` | 状态 |
|---|---:|---:|---|
| doubao-seed-2.0-pro | 0.642379 | 0.768078 | main |
| deepseek-3.2-thinking | 0.610752 | 0.728809 | low_sample |
| qwen3.6-plus | 0.592541 | 0.716466 | low_sample |

### 5.2 主结论：约束增强显著推高同质化

从 `b1 -> b2/b3 -> c1/c2` 可以看到非常清楚的趋势：

- 固定词牌后，同质化已经处在较高水平
- 在固定词牌基础上加入主题后，同质化继续上升
- 固定为单一词牌 `沁园春` 后，同质化进一步抬升到最高区间

用 `mihi_full` 粗看：

- `b1` 主模型大致在 `0.44-0.51`
- `b2/b3` 主模型大致在 `0.46-0.53`
- `c1/c2` 主模型大致在 `0.59-0.64`

这支持一个稳定结论：

**创作约束增强，是 AI 宋词内部同质化上升的首要驱动因素。**

---

## 6. 主题效应：玉兰比改革更容易诱发模板化

相邻条件差分来自 [neo_condition_deltas.csv](/D:/文件/Projects/songci/result/neo-analysis/neo_condition_deltas.csv)。

### 6.1 改革主题效应：`b1 -> b2`

| 模型 | `delta_mihi_full` |
|---|---:|
| deepseek-3.2-thinking | +0.014119 |
| doubao-seed-2.0-pro | +0.026965 |
| qwen3.6-plus | +0.006895 |

### 6.2 玉兰主题效应：`b1 -> b3`

| 模型 | `delta_mihi_full` |
|---|---:|
| deepseek-3.2-thinking | +0.072638 |
| doubao-seed-2.0-pro | +0.040558 |
| qwen3.6-plus | +0.011278 |

### 6.3 结论

三家主模型都表现出：

- 加入主题会提高同质化
- 玉兰主题带来的提升通常更强

尤其是 `deepseek`：

- `b1 -> b2` 仅增加 `+0.014119`
- `b1 -> b3` 增加 `+0.072638`

这说明：

**“玉兰”比“改革”更容易把模型压缩到相似意象、相似抒情路径和相似表达结构上。**

---

## 7. 同质化首先来自整体语义收缩

### 7.1 `b1 -> b2`

| 模型 | `delta_whole_score` | `delta_sent_score` |
|---|---:|---:|
| deepseek-3.2-thinking | +0.073021 | -0.065387 |
| doubao-seed-2.0-pro | +0.085857 | -0.045697 |
| qwen3.6-plus | +0.069881 | -0.059620 |

### 7.2 `b1 -> b3`

| 模型 | `delta_whole_score` | `delta_sent_score` |
|---|---:|---:|
| deepseek-3.2-thinking | +0.078641 | -0.009196 |
| doubao-seed-2.0-pro | +0.083301 | -0.022218 |
| qwen3.6-plus | +0.019167 | -0.036086 |

### 7.3 解释

固定主题后：

- `whole_score` 普遍明显上升
- `sent_score` 并没有同步上升，很多情况下反而下降

这意味着：

**主题约束首先让模型在“整首词在写什么”上越来越像，而不是立刻让每一句都更像。**

换句话说，主题带来的第一层收缩，是整体语义同质化，而不是句级模板全面复用。

---

## 8. 强结构约束下，句级模板复用才更容易抬升

对 `玉兰-沁园春强约束与prompt精简效应` 这一组差分，最值得注意的是 `b3 -> c1` 中的 `doubao`：

| 模型 | `delta_whole_score` | `delta_sent_score` | `delta_mihi_full` |
|---|---:|---:|---:|
| deepseek-3.2-thinking | -0.030250 | -0.015259 | -0.011594 |
| doubao-seed-2.0-pro | +0.000348 | +0.030238 | +0.009034 |
| qwen3.6-plus | -0.008572 | -0.027915 | -0.020685 |

对 `doubao` 来说：

- `whole_score` 几乎不变
- `sent_score` 上升了 `+0.030238`

这说明 `type_a` 这种：

- 固定 `沁园春`
- 固定主题
- 提供显式格律模板

的强结构 prompt，会把句级表达进一步压缩到更相似的骨架中。

因此可以说：

**在更强的词牌结构约束下，句级模板复用更容易成为同质化上升的重要来源。**

---

## 9. Prompt 结构的影响：能解释趋势，但不能简单归因为单一因果

### 9.1 `type_b -> type_d`

`b1` 使用 `type_b`，`b2/b3` 使用 `type_d`。二者差别在于：

- `type_b`：固定词牌，无主题
- `type_d`：固定词牌 + 固定主题 + 背景，并明确要求创造力与文学性

数据表明：

- 即使 prompt 已经明确强调“多样”“创新”“不要抄袭”
- 只要主题与背景被固定
- 同质化仍然会上升

因此：

**“创造力引导”并不能抵消主题约束带来的表达空间收缩。**

### 9.2 `type_d -> type_a`

`b3` 到 `c1` 的差别，不只是“五词牌到单词牌”，还包括：

- `type_a` 提供了显式的 `沁园春` 格律模板
- `type_a` 是更强的结构化 prompt

因此 `c1` 中更高的同质化，不宜只理解为“单词牌效应”，还应理解为：

**单词牌 + 显式格律模板共同强化了结构收缩。**

### 9.3 `type_d -> type_e`

`b2` 到 `c2` 的比较中，`type_e` 更短、更硬，没有创造力引导。

严格主分析下：

- `doubao`：`delta_mihi_full = -0.004173`
- `qwen`：`delta_mihi_full = -0.010559`

观察分析下：

- `deepseek`：`-0.002934`
- `doubao`：`-0.010672`
- `qwen`：`-0.016477`

因此目前的数据**不支持**简单断言：

**“去掉创造力提示一定会提高同质化”。**

更稳妥的说法是：

`type_e` 会改变改革主题的内容组织方式，但这种变化并不稳定地表现为综合同质化上升。

---

## 10. 与真实宋词基线的比较：AI 存在明显超额同质化

以 `excess_core_homogeneity` 看，主模型在各条件下几乎全部为正。

### 10.1 `b1`

- qwen3.6-plus：`+0.092521`
- doubao-seed-2.0-pro：`+0.075996`
- deepseek-3.2-thinking：`+0.031228`
- glm-5：`+0.031132`

### 10.2 `b2`

- qwen3.6-plus：`+0.108029`
- doubao-seed-2.0-pro：`+0.106556`
- deepseek-3.2-thinking：`+0.071425`

### 10.3 `b3`

- doubao-seed-2.0-pro：`+0.116791`
- qwen3.6-plus：`+0.091802`
- deepseek-3.2-thinking：`+0.086650`

### 10.4 `c1`

- doubao-seed-2.0-pro：`+0.211539`
- deepseek-3.2-thinking：`+0.168817`
- qwen3.6-plus：`+0.152833`

### 10.5 `c2`

- doubao-seed-2.0-pro：`+0.212229`
- deepseek-3.2-thinking：`+0.176837`
- qwen3.6-plus：`+0.156030`

这支持一个明确结论：

**AI 生成宋词不仅内部同质化，而且在相同词牌范围内显著高于真实宋词的自然创作分布。**

并且，约束越强，这种超额同质化越明显。

---

## 11. 描述性统计一：`a1` 中模型自主选择词牌的结果

### 11.1 自由生成并不等于充分发散

`a1` 对应 `type_c`，理论上模型可以自由选择词牌，但不同模型呈现出非常不同的集中度。

来自 [a1_model_cipai_summary.csv](/D:/文件/Projects/songci/result/descriptive-stats/a1_model_cipai_summary.csv)：

| 模型 | 作品数 | 词牌数 | Top1 词牌 | Top1 占比 | `cipai_entropy` |
|---|---:|---:|---|---:|---:|
| qwen3-max | 48 | 2 | 青玉案 | 0.812500 | 0.696212 |
| doubao-seed-2.0-pro | 50 | 4 | 鹧鸪天 | 0.520000 | 1.466262 |
| qwen3.6-plus | 49 | 9 | 鹧鸪天 | 0.428571 | 2.418726 |
| glm-5 | 50 | 18 | 鹧鸪天 | 0.240000 | 3.696175 |
| glm-4.7 | 45 | 19 | 满江红 / 八声甘州 | 0.133333 | 3.968979 |

最集中的模型是 `qwen3-max`：

- 只用了 `2` 个词牌
- `青玉案` 占比高达 `81.25%`

其次是 `doubao`：

- 只用了 `4` 个词牌
- `鹧鸪天` 占比 `52.00%`

而 `glm-4.7` 与 `glm-5` 的词牌分布明显更分散。

### 11.2 解释

这意味着：

**自由生成并不等于模型会真正均匀地探索词牌空间。**

很多模型在 `type_c` 下，会“自由地回到少数熟悉词牌”，这也是 `a1` 中部分模型同质化偏高的重要来源之一。

---

## 12. 描述性统计二：主题类型 `category` 的收缩

### 12.1 数据库级主题分布

来自 [category_distribution_by_db.csv](/D:/文件/Projects/songci/result/descriptive-stats/category_distribution_by_db.csv)。

#### `a1`：自由生成

- `离别羁旅`：34.33%
- `闲适隐逸`：14.68%
- `豪情壮志`：10.20%

#### `b1`：五词牌，无主题

- `离别羁旅`：42.71%
- `闲适隐逸`：15.74%
- `怀古咏史`：9.77%

#### `b2`：改革主题

- `谈禅说理`：41.08%
- `咏物寄托`：39.65%
- `豪情壮志`：19.27%

#### `b3`：玉兰主题

- `咏物寄托`：92.05%
- `豪情壮志`：5.25%
- `谈禅说理`：1.86%

#### `c1`：沁园春 + 玉兰

- `咏物寄托`：87.66%
- `豪情壮志`：10.89%

#### `c2`：沁园春 + 改革

- `谈禅说理`：57.20%
- `豪情壮志`：32.58%
- `咏物寄托`：9.85%

### 12.2 主题类型的解释

这组数据说明：

- 在无主题条件下，模型最容易自然滑向 `离别羁旅`
- 改革主题主要被模型写成 `谈禅说理 + 咏物寄托 + 豪情壮志`
- 玉兰主题几乎压倒性地收缩到 `咏物寄托`

也就是说：

**同质化不仅表现为文本彼此更像，也表现为主题归类越来越集中。**

### 12.3 模型间的主题翻译差异

来自 [category_summary_by_db_model.csv](/D:/文件/Projects/songci/result/descriptive-stats/category_summary_by_db_model.csv)。

以 `b2` 为例：

- `doubao`：`谈禅说理` 占 `63.00%`
- `qwen3.6-plus`：`咏物寄托` 占 `41.61%`，`豪情壮志` 占 `31.68%`
- `deepseek`：`咏物寄托` 占 `39.00%`，`谈禅说理` 占 `38.50%`

这说明：

- `doubao` 更偏议论化
- `qwen` 更偏寄托化与抒情化
- `deepseek` 介于两者之间

因此，即使面对同一主题，不同模型仍然存在不同的“题材翻译方式”。

---

## 13. 描述性统计三：意象系统的收缩

### 13.1 `a1`：自由生成下的意象惯性

来自 [imagery_summary_by_db_model.csv](/D:/文件/Projects/songci/result/descriptive-stats/imagery_summary_by_db_model.csv)。

几个典型模型：

- `qwen3-max` 的 Top10 意象：
  `芦花、西风、孤舟、烟水、渔灯、明月、渔笛、烟波、星影、寒江`
- `qwen3.6-plus` 的 Top10 意象：
  `孤舟、雁字、西风、芦花、星斗、星槎、暮云、汀洲、烟波、明月`
- `doubao` 的 Top10 意象：
  `清露、岸柳、石径、晚风、野菊、闲云、寒霜、清溪、残荷、软风`
- `deepseek` 的 Top10 意象：
  `数据、代码、算法、星河、键盘、网络、星空、青山、荧屏、光影`

这说明：

- `qwen` 系更偏传统漂泊婉约意象
- `doubao` 更偏自然景物与田园山水意象
- `deepseek` 在自由生成下明显出现现代和技术性意象

### 13.2 `b1`：固定词牌后回到传统宋词意象库

数据库级 Top20 来自 [imagery_top_by_db.csv](/D:/文件/Projects/songci/result/descriptive-stats/imagery_top_by_db.csv)：

`b1` 的高频意象包括：

- `明月`
- `孤舟`
- `西风`
- `暮云`
- `雁字`
- `斜阳`
- `芦花`
- `荻花`

这说明固定词牌但不定主题时，模型会快速回到一套传统词学中最稳妥的常用资源。

### 13.3 `b2` 与 `c2`：改革主题的制度化和宗门化意象

`b2` 的数据库级 Top20 以：

- `樊笼`
- `劫火`
- `灵根`
- `剑气`
- `铁律`
- `青衿`
- `剑阁`
- `清规`
- `宗门`
- `晨钟`
- `暮鼓`

为代表。

`c2` 的数据库级 Top20 则更集中在：

- `青衿`
- `灵根`
- `樊笼`
- `丹炉`
- `晨钟`
- `暮鼓`
- `仙峰`
- `弟子`
- `剑阁`
- `宗门`
- `铁律`
- `剑气`

这说明改革主题并不是被写成抽象政治口号，而是被大量编码进：

**修仙宗门 / 制度束缚 / 改革冲突** 这一固定语义场。

### 13.4 `b3` 与 `c1`：玉兰主题的高强度意象收缩

`b3` 的高频意象主要包括：

- `玉兰`
- `寒窗`
- `素萼`
- `玉树`
- `暗香`
- `春风`
- `书山`
- `长街`
- `春寒`
- `冰绡`
- `孤灯`
- `琼枝`
- `琼英`
- `素影`
- `清香`

`c1` 的高频意象主要包括：

- `玉兰`
- `琼枝`
- `寒窗`
- `琼英`
- `玉树`
- `清芬`
- `风埃`
- `素萼`
- `春风`
- `长风`
- `孤灯`
- `春寒`
- `清香`
- `素影`

这说明玉兰主题下的同质化，已经不是“泛泛地都在写花”，而是收缩到一套稳定的意象骨架：

**玉兰 / 素洁 / 春寒 / 寒窗 / 奋进或困顿**

---

## 14. 新增统计：数据库间意象重叠率

数据库间意象重叠率来自 [imagery_overlap_between_dbs.csv](/D:/文件/Projects/songci/result/descriptive-stats/imagery_overlap_between_dbs.csv)。

这里提供两个层次：

- `distinct_imagery_jaccard`：全部独特意象集合的 Jaccard
- `top20_overlap_count` 与 `top20_overlap_jaccard`：高频核心意象的重叠程度

### 14.1 最强的两个重叠关系

#### `b3` 与 `c1`：玉兰主题的跨条件高重叠

- `distinct_imagery_jaccard = 0.274739`
- `shared_distinct_imagery_count = 658`
- `top20_overlap_count = 16`
- `top20_overlap_jaccard = 0.666667`

共享 Top20 意象包括：

`书山、孤灯、寒窗、春寒、春风、清香、玉兰、玉树、琼枝、琼英、白雪、素影、素萼、长街、青衫、风霜`

这说明：

**无论是五词牌玉兰主题，还是固定沁园春玉兰主题，模型调用的核心意象系统高度一致。**

#### `b2` 与 `c2`：改革主题的跨条件高重叠

- `distinct_imagery_jaccard = 0.219302`
- `shared_distinct_imagery_count = 534`
- `top20_overlap_count = 14`
- `top20_overlap_jaccard = 0.538462`

共享 Top20 意象包括：

`云、剑影、剑气、剑阁、劫火、宗门、春风、晨钟、暮鼓、樊笼、灵根、铁律、长风、青衿`

这说明：

**改革主题在不同 prompt 与不同词牌条件下，也会稳定收缩到一套共享的世界观意象池。**

### 14.2 无主题条件与主题条件的重叠明显更低

例如：

- `a1` 与 `b1`：`top20_overlap_count = 15`
- `a1` 与 `b2`：`2`
- `a1` 与 `b3`：`1`
- `a1` 与 `c2`：`0`
- `b1` 与 `c2`：`0`

这说明一旦主题固定，模型调用的核心意象资源就会迅速从“常规宋词意象库”转向某种主题专属意象池。

### 14.3 解释意义

数据库间意象重叠率补强了前面的相似性分析：

- `b3` 与 `c1` 的高重叠，解释了为什么玉兰条件下同质化尤其高
- `b2` 与 `c2` 的高重叠，解释了为什么改革主题会收缩到制度化、宗门化表达
- 无主题条件与主题条件之间重叠很低，说明主题会重塑意象系统，而不是只在原有意象库中做轻微偏转

因此可以更清楚地说：

**很多同质化并不是“整首词重复”，而是“模型能调用的核心意象资源池明显变窄，而且跨条件反复回到同一组高频意象”。**

---

## 15. 观察分析：趋势具有稳健性

观察分析纳入了 `rhythm_score = 0` 的样本，用来检验趋势是否稳定。

来自 [neo_model_summary_observe.csv](/D:/文件/Projects/songci/result/neo-analysis/neo_model_summary_observe.csv)：

- `b1`：主模型 `mihi_full` 大约在 `0.448880-0.494526`
- `b2`：`0.488065-0.531551`
- `b3`：`0.509607-0.537725`
- `c1`：`0.542741-0.638981`
- `c2`：`0.572603-0.631295`

并且 `c2` 在观察分析中，`deepseek` 和 `qwen` 都能进入 `main`：

- `deepseek-3.2-thinking`：`0.612784`
- `qwen3.6-plus`：`0.572603`

这说明：

- 严格主分析中的 `c2` 低样本问题，确实部分来自高格律筛选
- 但即使放宽格律门槛，整体趋势并没有翻转

因此，主结论具有稳健性。

---

## 16. 综合结论

基于相似性分析、主题统计、意象统计与数据库间意象重叠率，本研究可以得出以下结论。

### 16.1 AI 宋词内部同质化会随着约束增强而显著上升

从 `b1` 到 `b2/b3` 再到 `c1/c2`，`mihi_full` 与 `core_mihi` 都整体上升。  
这说明固定词牌、固定主题、固定单一词牌等约束，会逐步压缩模型输出空间。

### 16.2 主题会显著重塑内容分布，其中玉兰比改革更容易诱发模板化

玉兰主题在 `category` 上几乎压倒性地收缩到 `咏物寄托`，在意象上也稳定收缩到：

`玉兰、素萼、琼枝、清香、春寒、寒窗、书山、孤灯`

相比之下，改革主题主要收缩到：

`谈禅说理、豪情壮志、咏物寄托`

以及：

`樊笼、灵根、青衿、晨钟、暮鼓、宗门、铁律、剑气`

### 16.3 同质化首先表现为整体语义收缩，而不是立即表现为句级模板全面重复

`b1 -> b2/b3` 中，`whole_score` 普遍上升而 `sent_score` 常常下降。  
这说明主题首先让作品“在讲同一种东西”，随后才可能在强结构约束下进一步出现句级模板复用。

### 16.4 强结构 prompt 会加强句级与意象层的收缩

`type_a` 的显式 `沁园春` 格律模板，使 `c1` 在部分模型上出现更强的句级收缩。  
`type_e` 则没有稳定提高综合同质化，但它确实让改革主题更集中地组织到议论化、制度化、宗门化意象系统中。

### 16.5 AI 相对于真实宋词存在明显超额同质化

所有主条件下 `excess_core_homogeneity` 基本为正，并且在 `c1/c2` 条件下达到最高。  
说明 AI 生成宋词不仅彼此更像，而且在相同词牌范围内比真实宋词的自然创作分布更集中。

### 16.6 自由生成也并不真正自由

`a1` 中不少模型会回到少数熟悉词牌。  
尤其 `qwen3-max` 几乎把自由生成压缩为“反复写青玉案”，这说明模型在弱约束下也存在明显的默认创作路径。

---

## 17. 需要谨慎表述的边界

- `a1` 适合作为探索性结果，不适合作为严格横向排名，因为不同模型实际选择的词牌不同。
- `c2` 严格主分析中 `deepseek` 与 `qwen` 属于低样本结果，应与观察分析一起解释。
- `type_e` 的影响目前应写成“改变了改革主题的内容收缩方式”，而不是“去掉创造力提示必然提高同质化”。

---

## 18. 最终一句话总结

**AI 宋词的内部同质化，不只是“文本彼此更像”，更是随着词牌、主题与 prompt 结构的约束增强，模型在整体语义、题材归类和核心意象资源上逐步收缩到少数稳定模板；而这种收缩已经显著高于真实宋词的自然创作分布。**
