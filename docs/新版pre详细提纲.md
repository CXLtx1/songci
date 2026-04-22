# AI宋词生成项目新版 pre 详细提纲

这份提纲不是 PPT 页面的直接排版稿，而是一份更详细的内容总纲。  
它的目标是先把整场汇报真正要讲清楚的逻辑重新搭起来，避免听众在开头就迷失在 `a1/b1/b2/c1/c2`、`type_a/type_b/type_c`、各种分析表和各种指标里。

整场汇报的核心原则只有一句：

**先让听众明白“这个项目到底在做什么、数据怎么来的、流程怎么走”，再讲结论。**

---

## 一、整个 pre 的总目标

这场汇报最终要让听众清楚六件事：

1. 这个项目到底在研究什么
2. 这些数据库和 prompt 分别代表什么任务
3. 整个项目是怎么从“提问”走到“结果”的
4. AI 写的宋词到底对不对，差在哪里
5. AI 写宋词时偏好哪些意象、哪些主题、是否借鉴真实宋词
6. 这些发现最后能怎样指导我们以后使用 AI 写宋词

因此，整场报告不应再以“结果块”直接开讲，而应先建立一个足够清楚的流程框架。

---

## 二、整体结构

建议整场汇报分成七个大部分：

1. 项目到底在做什么：任务、数据、流程
2. AI 写的宋词对不对：格律与结构能力
3. AI 喜欢用什么意象：默认意象、词牌差异、模型差异、主题差异
4. AI 实际在写什么主题：题材和主题组织
5. AI 宋词是否借鉴真实宋词：真实来源相似性分析
6. AI 宋词是否同质化：相似度方法与三层同质化分析
7. 这些发现对我们之后怎么使用 AI 有什么启发

---

## 三、第一部分：项目到底在做什么

这一部分是全场最重要的部分。  
如果这一部分讲不清楚，后面的所有结果都会失去意义。

### 3.1 先回答项目的核心问题

开头先不用术语，不用代号，直接说人话：

这个项目要研究的是：

- AI 能不能写出形式上基本成立的宋词
- AI 在不同任务要求下会写成什么样
- AI 会偏爱什么意象和主题
- AI 会不会越来越写成固定模板
- AI 写出来的宋词与真实宋词是什么关系


### 3.2 先把任务条件翻译成人话

不要先上 `a1 / b1 / b2 / b3 / c1 / c2`。  
应该先告诉听众，我们其实设计了六种不同任务：

1. 完全自由写一首宋词
2. 固定在五个词牌里写，但不规定主题
3. 固定五个词牌，并要求写“改革主题”
4. 固定五个词牌，并要求写“玉兰主题”
5. 固定写 `沁园春`，同时给出完整格律模板
6. 固定写 `沁园春`，只用较简略的格律要求

这里必须明确改正：

- `c2` 不是“硬性格律要求”
- `c2` 应该表达为：**固定 `沁园春` + 固定主题 + 简略格律要求**

### 3.3 再正式引入数据库代号

在听众先理解了上面六种任务后，再给出对应关系：

| 数据库 | 中文解释 | 任务性质 |
|---|---|---|
| `a1` | 自由生成 | 不限词牌，不限主题 |
| `b1` | 五词牌、无主题 | 只加词牌约束 |
| `b2` | 五词牌、改革主题 | 词牌约束 + 改革主题 |
| `b3` | 五词牌、玉兰主题 | 词牌约束 + 玉兰主题 |
| `c1` | 固定 `沁园春`、玉兰主题、显式格律模板 | 强结构任务 |
| `c2` | 固定 `沁园春`、改革主题、简略格律要求 | 强主题 + 简略格律提示 |

这里的目标不是让听众背代号，而是让他们明白：

**这六个数据库构成了一条逐步增强约束的链。**

### 3.4 prompt 一定要说清楚“让 AI 做什么”

以后在报告中只要提 prompt，不能只说 `type_a`、`type_b`、`type_c`。  
第一次出现时必须配简化说明：

- `type_c`：让模型自己选词牌、自己决定主题，自由写一首宋词
- `type_b`：规定只能在五个词牌中选择一个，但不规定主题
- `type_d`：规定词牌，同时给定具体主题情境
- `type_a`：固定 `沁园春`，并直接给出格律模板
- `type_e`：固定 `沁园春`，只用较简略的格律要求提醒模型注意声律

此外，“改革主题”“玉兰主题”也不能只说标签，必须给听众一句简化版说明。

例如：

- 改革主题：一个修仙宗门的年轻长老，希望改变压抑弟子的旧规，但又担心危机中失去秩序与战力
- 玉兰主题：一个大学生在学业和面试受挫后，看见盛开的白玉兰，重新感到生命的价值

### 3.5 项目流程必须画成清楚的一条链

这一部分最好讲成最简单的六步：

1. 设计任务与 prompt
2. 调用不同模型批量生成宋词
3. 把生成结果存入数据库
4. 用格律引擎检查字数、平仄、押韵
5. 提取主题与意象
6. 进一步做真实来源分析与同质化分析


### 3.6 必须展示一小段核心代码

这一部分可以展示两类小代码片段：

#### A. 任务配置代码

用来说明数据库和任务条件是怎样被程序组织起来的。

#### B. `songci_engine` 的关键逻辑

用来说明结果里的“格律分”不是人工印象，而是程序计算出来的。

这部分代码展示不宜太长，但一定要明确解释：

- 词谱从哪里来
- 平水韵和词林正韵怎么被调用
- 评分为什么不是凭空打分

---

## 四、第二部分：AI 写的宋词对不对

这一部分是形式层，也是最容易建立“项目可信度”的地方。

### 4.1 先解释什么叫“写对”

这里要明确告诉听众，我们主要看四件事：

1. 字数是否符合词牌要求
2. 平仄是否基本合格
3. 韵脚是否基本成立
4. 长调中结构是否能持续维持

这里的“对不对”主要是指格律与结构层面的对，不是文学水平高低。

### 4.2 必须明确讲格律评分是怎么计算的

这一部分不能只给分数表，必须先解释评分方式。

根据现有 `songci_engine.py`，可以讲成：

- 初始分数从 `100` 出发
- 每发现一种格律问题就按权重扣分
- 最后分数计算方式是：

```text
score = max(0, 100 - total_penalty × 4)
```

同时说明主要扣分项：

- 平仄错误：每处按较高权重计入惩罚
- 韵脚声调错误：惩罚更高
- 出韵/挤韵：惩罚最高
- 未收录字只警告，不扣分

还可以进一步解释：

- 字数不符会直接导致该变体校验失败
- 多音字会优先按符合平仄或押韵要求的读法处理
- 韵脚优先按平水韵严格匹配，不行再尝试词林正韵通押

### 4.3 再展示不同词牌

有了评分方式后，再给出整体结论：

- 哪些词牌平均格律分更高
- 哪些词牌最难
- 不同的词牌下AI更喜欢犯什么错

### 4.4 再比较不同模型

这一部分回答：

- 哪些模型总体上更懂格律
- 不同模型最不擅长什么词牌
- 不同模型喜欢犯什么格律错误


### 4.5 再比较不同 prompt

这一部分一定要用中文解释，而不是只报 prompt 代号。

例如：

- 自由生成 prompt 会让模型回到熟悉写法
- 固定词牌 prompt 会提升结构稳定性
- 给出完整格律模板会显著提高长调表现
- 只有简略格律提示时，模型更容易在长调中暴露问题
  
这一部分要回答

- 各种prompt引导是否对模型表现有帮助
- 特殊的主题背景对模型的影响多深


---

## 五、第三部分：AI 喜欢用什么意象

这一部分的目标非常明确：

**告诉听众 AI 最喜欢用什么意象，不同条件下它的意象偏好怎样变化。**
  
听众最关心的是：

- 默认最喜欢写什么
- 哪些词牌最容易写什么
- 哪些模型最爱什么
- 不同主题下为什么会变

### 5.1 先看 AI 的默认意象

用 `a1` 和 `b1` 这两组说明：

- 不给主题时，AI 最爱写哪些意象
- 常见的高频意象有哪些
- 哪些意象几乎成了默认起手式

这里可以直接展示一组最常见的意象：

- 明月
- 西风
- 孤舟
- 雁字
- 芦花
- 斜阳

### 5.2 不同词牌最喜欢什么意象

这一部分非常重要，因为它比“总体高频意象”更具体。

应该回答：

- `菩萨蛮` 常搭配什么意象
- `清平乐` 常搭配什么意象
- `浪淘沙` 常搭配什么意象
- `祝英台近` 常搭配什么意象
- `沁园春` 常搭配什么意象

重点不是只列词，而是说明：

- 不同词牌会把模型导向不同的景物和情绪表达方式
- 词牌本身会影响意象选择

### 5.3 不同模型最喜欢什么意象

这一部分回答：

- `doubao` 最常用什么
- `deepseek` 最常用什么
- `qwen` 最常用什么

这里应强调：

- 有的模型更偏山水闲适
- 有的模型更偏旅愁离别
- 有的模型会混入现代词语或技术词残留

### 5.4 不同主题下意象会怎样变化

这一部分用 `b2/b3/c1/c2` 来讲：

- 改革主题下最常出现什么意象
- 玉兰主题下最常出现什么意象

重点要说明：

- 改革主题会把模型引向宗门、旧规、灵根、晨钟、仙峰等意象
- 玉兰主题会把模型引向玉兰、素萼、寒窗、琼枝、清芬等意象


---

## 六、第四部分：AI 实际在写什么主题

这一部分比第三部分篇幅略短，但仍然必要。

### 6.1 先说明“无主题”不等于真的没有主题

这里用 `a1/b1` 来说明：

- 即使不规定主题，AI 也会自动滑向一些熟悉题材
- 例如离别羁旅、闲适隐逸、怀古咏史等

### 6.2 再讲给定主题后，AI 会怎么压缩写法

用两个最重要的主题例子：

#### A. 改革主题

不要只说“改革”，要说：

- 宗门旧规压人
- 想改革但有阻力
- 危机来时又担心失去秩序

然后说明 AI 最后常写成哪几种题材：

- 谈禅说理
- 咏物寄托
- 豪情壮志

#### B. 玉兰主题

说明它不只是“写一朵花”，而是“借花写人生受挫后的重振”。

然后说明 AI 常常如何压缩：

- 先写花之洁白清芬
- 再写寒窗、挫折、前路
- 最后把花和自我处境连起来


---

## 七、第五部分：AI 宋词是否借鉴真实宋词


不要用“抄袭”，而要先用“借鉴”“借用关系”“真实来源相似性”。

### 7.1 先说明分析逻辑

这一部分先解释三层：

1. 历史宋词内部本来就有多像
2. AI 整首最像哪些真实宋词
3. AI 某些句子是否反复落到同一首真实宋词

这样听众才知道：

我们不是看到一句像就说抄袭，而是先建立历史基线。

### 7.2 先讲历史基线

告诉听众：

- 真实宋词之间本来就有高相似度
- 尤其短句、套语、常见抒情结构，本来就容易重复


### 7.3 再讲整首与句级结果

这一部分要说清楚：

- 多数 AI 样本更像“传统共相”（要换一个词）或“模板复用”
- 少数样本会出现局部改写式借用

### 7.4 不同词牌的影响


在 `b1` 分词牌结果中，应重点说明：

#### A. `祝英台近`

- 句级语义、字面相似都很高
- 更值得关注局部借用与局部改写

#### B. `浪淘沙`

- 整首语义贴近程度更高
- 更像整体落入真实宋词的熟悉意境

#### C. `沁园春`

- 同词牌吸附最明显
- 但由于 `沁园春` 历史基线本来就高，所以高相似不能简单等同异常借用

#### D. `清平乐` 与 `菩萨蛮`

- 更接近常规模板化
- 没有 `祝英台近` 那么强的局部借用特征

### 7.5 再讲不同模型的差异

这一部分要回答：

- 哪些模型更容易出现局部来源聚集
- 哪些模型更像只是整体风格贴近

---

## 八、第六部分：AI 宋词是否同质化

这一部分先讲方法，再讲结果。  
而且必须围绕“三层同质化”来组织。

### 8.1 先解释相似度是怎么计算的

这一部分不能直接扔出结论，必须先解释：

我们用了 BERT 古诗词模型，把每首词或每个句子转成高维向量。  
高维向量之间越接近，说明语义越接近。

可以简化说明为：

1. 把文本输入 BERT-CCPoem
2. 得到对应的高维 embedding 向量
3. 计算向量之间的 cosine similarity
4. similarity 越高，表示两首词或两个句子越相似

同时补一句：

- 这主要衡量语义和整体表达方向
- 不是只看有没有一模一样的字

### 8.2 再解释为什么还要看字面相似度

说明：

- 语义相似度看“换词不换意”
- 字面相似度看“有没有直接重复句子或结构”

### 8.3 再正式引入三层同质化

这里必须以三层为核心：

#### 第一层：整首词越来越像

是将整首诗进行相似性分析

看的是：
整体的架构和格式以及全词的主题

#### 第二层：句子越来越像

看的是：
具体的每个句子的表达方式

#### 第三层：意象越来越固定

看的是：

是否总是用相似的意象

### 8.4 再展示整体结果

这里再讲：

- 约束越强，同质化越高
- 固定长调、固定主题时，同质化最明显

### 8.5 再比较不同模型

说明：

- 哪些模型更容易整体收缩
- 哪些模型更容易句级收缩
- 哪些模型更容易意象固定


---

## 九、第七部分：这些发现对我们之后怎么使用 AI 有什么启发

### 9.1 如果想让 AI 更稳地写宋词

建议：

- 给清楚的词牌约束
- 长调最好提供显式模板
- 生成后一定做格律校验

### 9.2 如果想让 AI 写得更多样

建议：

- 不要同时叠太多约束
- 先放开主题或词牌中的一项
- 批量生成后再筛选

### 9.3 如果想减少模板化

建议：

- 不要只看单首输出
- 要批量比较
- 要有去重和人工筛选

### 9.4 如果想避免借用真实宋词的风险

建议：

- 对高风险词牌单独警惕
- 对局部句级高度贴近样本做人工复核
- 在生成流程里加入真实来源比对模块

### 9.5 最后的总结句

一个长句，总结全部的结论

---

## 附：这版 pre 可能会用到的数据与文字来源

下面只列这次新版 pre 真正可能会调用的核心文件，并简单说明用途。  
不追求做完整档案清单，只是方便后面制作时快速知道“这个部分该去哪里找材料”。

### 一、提纲与文字说明

#### [新版pre详细提纲.md](/D:/文件/Projects/songci/docs/新版pre详细提纲.md)

- 用途：这次新版 pre 的总纲
- 作用：确定整场汇报的结构、顺序和每一部分主要内容

#### [neo-ppt-content.md](/D:/文件/Projects/songci/docs/neo-ppt-content.md)

- 用途：上一轮 PPT 内容稿
- 作用：可参考原来的表达、表格和结论，但结构不应直接照搬

#### [neo-presentation-report.md](/D:/文件/Projects/songci/docs/neo-presentation-report.md)

- 用途：主线分析的较完整文字报告
- 作用：后续写页面说明、过渡句、结论句时可参考

#### [neo-analysis-report.md](/D:/文件/Projects/songci/docs/neo-analysis-report.md)

- 用途：主线结果报告之一
- 作用：同质化、模型差异、条件差异等部分的重要文字来源

#### [neo-analysis-report 2.md](/D:/文件/Projects/songci/docs/neo-analysis-report%202.md)

- 用途：主线结果报告补充版
- 作用：可补充查阅某些结果的另一种组织方式或更详细表述

#### [neo-real-analysis-report.md](/D:/文件/Projects/songci/docs/neo-real-analysis-report.md)

- 用途：真实来源借用分析的正式报告
- 作用：第五部分“AI 宋词是否借鉴真实宋词”的主要文字来源

#### [AI宋词真实来源借用研究设计.md](/D:/文件/Projects/songci/docs/AI宋词真实来源借用研究设计.md)

- 用途：真实来源分析的方法设计文档
- 作用：说明这部分分析为什么这样做、三层结构是什么、方法边界在哪里

#### [相似性分析方法论.md](/D:/文件/Projects/songci/docs/相似性分析方法论.md)

- 用途：相似度与同质化分析的方法说明
- 作用：第六部分介绍 BERT 高维向量、语义相似度、字面相似度时的重要来源

#### [相似性分析数据说明文档.md](/D:/文件/Projects/songci/docs/相似性分析数据说明文档.md)

- 用途：项目数据与结果文件说明
- 作用：第一部分介绍数据库结构、分析粒度、输出文件含义时可引用

### 二、生成流程与 prompt

#### [generate/prompts.py](/D:/文件/Projects/songci/generate/prompts.py)

- 用途：存放 `type_a / type_b / type_c / type_d / type_e` 的 prompt 文案
- 作用：第一部分讲 prompt 设计时的最直接来源

#### [generate/tasks.json](/D:/文件/Projects/songci/generate/tasks.json)

- 用途：任务配置文件
- 作用：说明有哪些任务、数据库如何对应到不同实验条件

#### [generate/generator.py](/D:/文件/Projects/songci/generate/generator.py)

- 用途：批量调用模型生成宋词的主脚本
- 作用：第一部分讲“项目流程”时可以展示生成环节代码

#### [generate/extract_imagery.py](/D:/文件/Projects/songci/generate/extract_imagery.py)

- 用途：意象提取脚本
- 作用：第三、四部分中说明“意象和主题是怎么抽出来的”

### 三、格律引擎与规则数据

#### [engine/songci_engine.py](/D:/文件/Projects/songci/engine/songci_engine.py)

- 用途：格律校验主引擎
- 作用：第二部分“AI 写的宋词对不对”的核心代码来源
- 可用于展示：
  - 词谱载入
  - 平水韵与词林正韵的使用
  - 平仄与押韵的校验逻辑
  - 格律评分公式

#### [engine/词谱.json](/D:/文件/Projects/songci/engine/词谱.json)

- 用途：词牌格律与结构化 `tunes` 数据
- 作用：说明格律分析不是主观判断，而是对照词谱执行

#### [engine/韵书.json](/D:/文件/Projects/songci/engine/韵书.json)

- 用途：平水韵字表
- 作用：格律校验中判断平仄与押韵的基础数据

#### [engine/词林正韵.json](/D:/文件/Projects/songci/engine/词林正韵.json)

- 用途：词林正韵韵部数据
- 作用：格律引擎中宽韵、通押判断的基础数据

### 四、分析脚本

#### [analyze/neo-rhythm-stats.py](/D:/文件/Projects/songci/analyze/neo-rhythm-stats.py)

- 用途：格律统计后处理脚本
- 作用：第二部分数据库级、模型级、错误类型级别的格律结果主要来自这里

#### [analyze/neo-descriptive-stats.py](/D:/文件/Projects/songci/analyze/neo-descriptive-stats.py)

- 用途：描述性统计脚本
- 作用：第三、四部分中意象、题材、类别分布的主要结果来源

#### [analyze/neo-analysis.py](/D:/文件/Projects/songci/analyze/neo-analysis.py)

- 用途：主线同质化分析脚本
- 作用：第六部分“AI 宋词是否同质化”的主要代码来源

#### [analyze/neo-real-analysis.py](/D:/文件/Projects/songci/analyze/neo-real-analysis.py)

- 用途：真实来源三层分析脚本
- 作用：第五部分“AI 宋词是否借鉴真实宋词”的核心脚本
- 主要输出：
  - 历史基线
  - 整首级真实来源检索
  - 句级真实来源检索
  - 来源集中度画像

#### [analyze/neo-real-b1-cipai-report.py](/D:/文件/Projects/songci/analyze/neo-real-b1-cipai-report.py)

- 用途：`b1` 分词牌真实来源相似性后处理脚本
- 作用：第五部分“不同词牌的影响”这一小节的直接来源

#### [analyze/BERT-CCPoem-Model/config.json](/D:/文件/Projects/songci/analyze/BERT-CCPoem-Model/config.json)

- 用途：BERT-CCPoem 模型配置文件
- 作用：第六部分讲“高维向量相似度”时可作为模型来源依据

#### [analyze/BERT-CCPoem-Model/pytorch_model.bin](/D:/文件/Projects/songci/analyze/BERT-CCPoem-Model/pytorch_model.bin)

- 用途：BERT-CCPoem 模型权重
- 作用：不是展示材料，但说明相似度分析确实基于古诗词专用模型

### 五、数据库文件

#### [database/a1.db](/D:/文件/Projects/songci/database/a1.db)

- 用途：自由生成数据
- 作用：讲“AI 默认会写什么”“默认意象是什么”时的重要来源

#### [database/b1.db](/D:/文件/Projects/songci/database/b1.db)

- 用途：五词牌、无主题数据
- 作用：讲词牌影响、默认结构压力、不同词牌差异时的重要来源

#### [database/b2.db](/D:/文件/Projects/songci/database/b2.db)

- 用途：五词牌、改革主题数据
- 作用：讲改革主题下的意象、主题组织与真实来源借用风险

#### [database/b3.db](/D:/文件/Projects/songci/database/b3.db)

- 用途：五词牌、玉兰主题数据
- 作用：讲玉兰主题下的意象与主题压缩

#### [database/c1.db](/D:/文件/Projects/songci/database/c1.db)

- 用途：固定 `沁园春`、玉兰主题、显式格律模板数据
- 作用：比较显式格律模板对长调生成的帮助

#### [database/c2.db](/D:/文件/Projects/songci/database/c2.db)

- 用途：固定 `沁园春`、改革主题、简略格律要求数据
- 作用：比较简略格律提示与显式格律模板的差异

#### [database/real_song_ci_dataset.db](/D:/文件/Projects/songci/database/real_song_ci_dataset.db)

- 用途：真实宋词对照数据库
- 作用：第五部分真实来源借用分析的主要对照库

#### [database/real_poetry_dataset.db](/D:/文件/Projects/songci/database/real_poetry_dataset.db)

- 用途：更大范围的历代诗词数据库
- 作用：目前主要作为补充参照库；后续若扩展真实来源分析，可继续使用

### 六、结果数据文件

#### [result/rhythm-stats/rhythm_summary_by_db.csv](/D:/文件/Projects/songci/result/rhythm-stats/rhythm_summary_by_db.csv)

- 用途：数据库级格律统计
- 作用：第二部分比较不同任务条件下格律表现

#### [result/rhythm-stats/rhythm_summary_by_db_model.csv](/D:/文件/Projects/songci/result/rhythm-stats/rhythm_summary_by_db_model.csv)

- 用途：数据库 × 模型格律统计
- 作用：第二部分比较不同模型在不同任务下的格律差异

#### [result/rhythm-stats/rhythm_issue_breakdown_by_db.csv](/D:/文件/Projects/songci/result/rhythm-stats/rhythm_issue_breakdown_by_db.csv)

- 用途：数据库级错误类型拆分
- 作用：第二部分中“字数错、平仄错、出韵错”的分析来源

#### [result/descriptive-stats/imagery_top_by_db.csv](/D:/文件/Projects/songci/result/descriptive-stats/imagery_top_by_db.csv)

- 用途：按数据库统计高频意象
- 作用：第三部分“AI 默认最喜欢什么意象”的直接来源

#### [result/descriptive-stats/imagery_top_by_db_model.csv](/D:/文件/Projects/songci/result/descriptive-stats/imagery_top_by_db_model.csv)

- 用途：按数据库和模型统计高频意象
- 作用：第三部分“不同模型喜欢什么意象”的主要来源

#### [result/descriptive-stats/imagery_top_by_db_category.csv](/D:/文件/Projects/songci/result/descriptive-stats/imagery_top_by_db_category.csv)

- 用途：按数据库和类别统计高频意象
- 作用：第三、四部分中“不同主题/题材下意象怎么变化”的主要来源

#### [result/descriptive-stats/category_distribution_by_db.csv](/D:/文件/Projects/songci/result/descriptive-stats/category_distribution_by_db.csv)

- 用途：按数据库统计主题/题材类别分布
- 作用：第四部分“AI 实际在写什么主题”的主要表格来源

#### [result/descriptive-stats/category_distribution_by_db_model.csv](/D:/文件/Projects/songci/result/descriptive-stats/category_distribution_by_db_model.csv)

- 用途：按数据库和模型统计题材类别
- 作用：第四部分比较不同模型在不同任务下写什么主题

#### [result/neo-analysis/neo_model_summary.csv](/D:/文件/Projects/songci/result/neo-analysis/neo_model_summary.csv)

- 用途：模型级同质化结果
- 作用：第六部分比较不同模型整体同质化程度

#### [result/neo-analysis/neo_cipai_summary.csv](/D:/文件/Projects/songci/result/neo-analysis/neo_cipai_summary.csv)

- 用途：词牌级同质化结果
- 作用：第六部分说明不同词牌的同质化差异

#### [result/neo-analysis/neo_condition_deltas.csv](/D:/文件/Projects/songci/result/neo-analysis/neo_condition_deltas.csv)

- 用途：不同条件之间的同质化变化
- 作用：第六部分说明“约束增强 -> 同质化升高”

#### [result/neo-real-analysis/reference_baseline_whole.csv](/D:/文件/Projects/songci/result/neo-real-analysis/reference_baseline_whole.csv)

- 用途：真实宋词整首级历史基线
- 作用：第五部分判断 AI 整首相似是否异常

#### [result/neo-real-analysis/reference_baseline_sentence.csv](/D:/文件/Projects/songci/result/neo-real-analysis/reference_baseline_sentence.csv)

- 用途：真实宋词句级历史基线
- 作用：第五部分判断 AI 句级相似是否异常

#### [result/neo-real-analysis/ai_whole_alignment_topk.csv](/D:/文件/Projects/songci/result/neo-real-analysis/ai_whole_alignment_topk.csv)

- 用途：AI 整首对真实宋词的 TopK 来源检索结果
- 作用：第五部分分析 AI 整首最像哪些真实词作

#### [result/neo-real-analysis/ai_sentence_alignment_details.csv](/D:/文件/Projects/songci/result/neo-real-analysis/ai_sentence_alignment_details.csv)

- 用途：AI 句级对真实宋词的详细检索结果
- 作用：第五部分分析局部借用、局部改写、来源集中度

#### [result/neo-real-analysis/ai_poem_source_profile.csv](/D:/文件/Projects/songci/result/neo-real-analysis/ai_poem_source_profile.csv)

- 用途：AI 作品级来源画像
- 作用：第五部分做整首与句级综合判断时最重要的汇总表

#### [result/neo-real-analysis/b1_cipai_similarity_summary.csv](/D:/文件/Projects/songci/result/neo-real-analysis/b1_cipai_similarity_summary.csv)

- 用途：`b1` 分词牌真实来源相似性补充汇总
- 作用：第五部分“不同词牌的影响”的主要结果表

#### [result/neo-real-analysis/b1_cipai_similarity_report.md](/D:/文件/Projects/songci/result/neo-real-analysis/b1_cipai_similarity_report.md)

- 用途：`b1` 分词牌结果的文字版摘要
- 作用：第五部分写作时可直接参考文字解释

#### [result/neo-real-analysis/run_metadata.json](/D:/文件/Projects/songci/result/neo-real-analysis/run_metadata.json)

- 用途：真实来源分析的运行元信息
- 作用：第一部分说明样本量、数据库规模、句子规模时可直接引用

### 七、最常用的核心来源

如果后面正式开始做新版 pre，真正最常用的其实只有下面这些：

- 提纲与文字：`新版pre详细提纲.md`、`neo-real-analysis-report.md`、`neo-presentation-report.md`
- prompt 与流程：`generate/prompts.py`、`generate/tasks.json`、`generate/generator.py`
- 格律：`engine/songci_engine.py`、`result/rhythm-stats/*.csv`
- 意象与主题：`result/descriptive-stats/*.csv`
- 同质化：`result/neo-analysis/*.csv`
- 真实来源：`result/neo-real-analysis/*.csv`

也就是说，真正制作时完全没必要把项目里所有旧文件重新翻一遍，  
只需要围绕上面这几组核心来源组织材料就够了。
