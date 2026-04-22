import sqlite3
import torch
import csv
import re
import difflib
import heapq
import math
import numpy as np
import multiprocessing as mp
from collections import defaultdict
from sentence_transformers import SentenceTransformer, util, models
from pyecharts import options as opts
from pyecharts.charts import Boxplot, HeatMap, Line, Radar
from pyecharts.commons.utils import JsCode
from pyecharts.charts import Grid

# ==========================================
# 1. 基础配置区
# ==========================================
DB_NAME = "database/b2.db"
EMBEDDING_MODEL_NAME = "analyze/BERT-CCPoem-Model"

SEMANTIC_THRESHOLD = 0.85
LEXICAL_LOW_THRESHOLD = 0.5
HIGH_SIM_THRESHOLD = 0.85
TOP_PAIRS_LIMIT = 1000

CSV_MODEL_SUMMARY = f"result/analysis-4/model_homogeneity_summary_{DB_NAME[-5:-3]}.csv"
CSV_CIPAI_SUMMARY = f"result/analysis-4/model_cipai_homogeneity_{DB_NAME[-5:-3]}.csv"
CSV_HIGH_SIM_PAIRS = f"result/analysis-4/model_high_sim_pairs_{DB_NAME[-5:-3]}.csv"

HTML_BOXPLOT = f"result/analysis-4/model_boxplot_{DB_NAME[-5:-3]}.html"
HTML_HEATMAP = f"result/analysis-4/model_cipai_heatmap_{DB_NAME[-5:-3]}.html"
HTML_KDE = f"result/analysis-4/model_kde_density_{DB_NAME[-5:-3]}.html"
HTML_RADAR = f"result/analysis-4/model_radar_{DB_NAME[-5:-3]}.html"

# ==========================================
# 2. 辅助函数
# ==========================================
def split_into_sentences(text):
    parts = re.split(r'[，。！？；\n]', text)
    return [p.strip() for p in parts if p.strip()]

def map_model_name(raw_name):
    if not raw_name: return "Unknown"
    if raw_name == "doubao-seed-2-0-pro-260215": return "doubao-seed-2.0-pro"
    if raw_name in ["deepseek-reasoner", "deepseek-v3.2"]: return "deepseek-3.2-thinking"
    if raw_name == "qwen3.6-plus": return "qwen3.6-plus"
    if raw_name == "gemini-3.1-pro-preview": return "gemini-3.1-pro"
    return raw_name

def calc_lexical_similarity(text1, text2):
    return difflib.SequenceMatcher(None, text1, text2).ratio()

_texts_global = None

def init_worker(texts):
    global _texts_global
    _texts_global = texts

def calc_lexical_batch(args):
    i, j, sem_sim = args
    lex_sim = calc_lexical_similarity(_texts_global[i], _texts_global[j])
    return (i, j, sem_sim, lex_sim)

def calc_percentiles(values, percentiles=[25, 50, 75, 90, 95]):
    if not values:
        return {p: 0.0 for p in percentiles}
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    result = {}
    for p in percentiles:
        idx = int((p / 100) * (n - 1))
        result[p] = sorted_vals[idx]
    return result

def calc_high_sim_ratio(values, threshold=HIGH_SIM_THRESHOLD):
    if not values:
        return 0.0
    count = sum(1 for v in values if v >= threshold)
    return count / len(values)

def calc_diversity_entropy(values, bins=20):
    if not values:
        return 0.0
    min_v, max_v = 0.0, 1.0
    bin_width = (max_v - min_v) / bins
    counts = defaultdict(int)
    for v in values:
        bin_idx = min(int((v - min_v) / bin_width), bins - 1)
        counts[bin_idx] += 1
    total = len(values)
    entropy = 0.0
    for c in counts.values():
        if c > 0:
            p = c / total
            entropy -= p * math.log2(p)
    max_entropy = math.log2(bins)
    return entropy / max_entropy if max_entropy > 0 else 0.0

def calc_composite_score(p50_sem, p90_sem):
    score = 0.55 * p50_sem + 0.45 * p90_sem
    return score

def calc_pseudo_ratio(sem_sims, lex_sims, threshold=0.3):
    if not sem_sims or not lex_sims or len(sem_sims) != len(lex_sims):
        return 0.0
    count = sum(1 for s, l in zip(sem_sims, lex_sims) if (s - l) > threshold)
    return count / len(sem_sims)

# ==========================================
# 3. 可视化引擎
# ==========================================
def render_boxplot(model_data, output_file):
    models = sorted(model_data.keys())
    box_data = []
    for m in models:
        sims = model_data[m]["all_sims"]
        if sims:
            p5 = np.percentile(sims, 5)
            p25 = np.percentile(sims, 25)
            p50 = np.percentile(sims, 50)
            p75 = np.percentile(sims, 75)
            p95 = np.percentile(sims, 95)
            box_data.append([p5, p25, p50, p75, p95])
        else:
            box_data.append([0, 0, 0, 0, 0])
    
    c = Boxplot(init_opts=opts.InitOpts(width="100%", height="600px"))
    c.add_xaxis(models)
    c.add_yaxis("跨词句对相似度", c.prepare_data(box_data))
    c.set_global_opts(
        title_opts=opts.TitleOpts(title="模型内部相似度分布箱线图", subtitle="跨词句对语义相似度"),
        yaxis_opts=opts.AxisOpts(name="相似度", min_=0, max_=1),
        xaxis_opts=opts.AxisOpts(name="模型"),
        tooltip_opts=opts.TooltipOpts(trigger="axis", axis_pointer_type="shadow")
    )
    c.render(output_file)
    print(f"箱线图已生成: {output_file}")

def render_heatmap(cipai_data, output_file):
    models = sorted(set(item["model"] for item in cipai_data))
    cipais = sorted(set(item["cipai"] for item in cipai_data))
    
    data = []
    for m in models:
        for c in cipais:
            matching = [item for item in cipai_data if item["model"] == m and item["cipai"] == c]
            if matching:
                score = matching[0]["composite_score"]
            else:
                score = 0
            data.append([c, m, round(score, 3)])
    
    c = HeatMap(init_opts=opts.InitOpts(width="100%", height="700px"))
    c.add_xaxis(cipais)
    c.add_yaxis("模型", models, data,
        label_opts=opts.LabelOpts(is_show=True, position="inside", formatter="{c}")
    )
    c.set_global_opts(
        title_opts=opts.TitleOpts(title="模型×词牌同质化热力图", subtitle="综合评分（越高越同质化）"),
        tooltip_opts=opts.TooltipOpts(trigger="item", formatter="{b}: {c}"),
        visualmap_opts=opts.VisualMapOpts(
            is_show=True, min_=0, max_=1,
            range_color=["#50a3ba", "#eac736", "#d94e5d"]
        )
    )
    c.render(output_file)
    print(f"热力图已生成: {output_file}")

def render_kde(model_data, output_file):
    models = sorted(model_data.keys())
    
    line = Line(init_opts=opts.InitOpts(width="100%", height="600px"))
    
    x_data = np.linspace(0, 1, 100)
    line.add_xaxis([round(x, 2) for x in x_data])
    
    for m in models:
        sims = model_data[m]["all_sims"]
        if sims and len(sims) > 10:
            from scipy import stats
            kde = stats.gaussian_kde(sims)
            y_data = kde(x_data)
            y_data = [round(y, 4) for y in y_data]
            line.add_yaxis(m, y_data, is_smooth=True, symbol="none")
    
    line.set_global_opts(
        title_opts=opts.TitleOpts(title="相似度概率密度分布(KDE)", subtitle="跨词句对语义相似度"),
        xaxis_opts=opts.AxisOpts(name="相似度", min_=0, max_=1),
        yaxis_opts=opts.AxisOpts(name="密度"),
        tooltip_opts=opts.TooltipOpts(trigger="axis"),
        legend_opts=opts.LegendOpts(pos_top="5%")
    )
    line.render(output_file)
    print(f"KDE密度图已生成: {output_file}")

def render_radar(model_data, output_file):
    models = sorted(model_data.keys())
    
    schema = [
        opts.RadarIndicatorItem(name="语义P50", max_=1),
        opts.RadarIndicatorItem(name="语义P90", max_=1),
        opts.RadarIndicatorItem(name="综合评分", max_=1),
    ]
    
    data_radar = []
    for m in models:
        d = model_data[m]
        values = [
            round(d["p50_sem"], 3),
            round(d["p90_sem"], 3),
            round(d["composite_score"], 3),
        ]
        data_radar.append(opts.RadarItem(value=values, name=m))
    
    c = Radar(init_opts=opts.InitOpts(width="100%", height="600px"))
    c.add_schema(schema)
    for i, m in enumerate(models):
        c.add(m, [data_radar[i]], color=["#5470c6", "#91cc75", "#fac858", "#ee6666", "#73c0de"][i % 5])
    c.set_global_opts(
        title_opts=opts.TitleOpts(title="模型同质化雷达图", subtitle="综合评分 = 0.55×P50 + 0.45×P90"),
        legend_opts=opts.LegendOpts(pos_top="5%")
    )
    c.render(output_file)
    print(f"雷达图已生成: {output_file}")

# ==========================================
# 4. 主程序
# ==========================================
def main():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print("="*60)
    print(f"[模型内宋词相似性分析] 启动！")
    print(f"设备: {device.upper()} | 模型: {EMBEDDING_MODEL_NAME}")
    print(f"CPU核心数: {mp.cpu_count()}")
    print("="*60)

    print("\n正在加载模型...")
    try:
        word_embedding_model = models.Transformer(EMBEDDING_MODEL_NAME)
        pooling_model = models.Pooling(
            word_embedding_model.get_word_embedding_dimension(),
            pooling_mode_mean_tokens=True,
            pooling_mode_cls_token=False,
            pooling_mode_max_tokens=False
        )
        model = SentenceTransformer(modules=[word_embedding_model, pooling_model], device=device)
        print("模型加载成功！")
    except Exception as e:
        print(f"模型加载失败: {e}")
        return

    print(f"\n正在读取数据库: {DB_NAME}")
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT id, cipai, title, content, model_name FROM ci_data WHERE content != ''")
    records = [dict(r) for r in cursor.fetchall()]
    conn.close()

    for r in records:
        r["model_name"] = map_model_name(r["model_name"])

    print(f"共读取 {len(records)} 首词")

    model_groups = defaultdict(list)
    for poem in records:
        model_groups[poem["model_name"]].append(poem)
    
    print(f"模型分组: {list(model_groups.keys())}")

    model_results = {}
    cipai_results = []
    all_high_sim_pairs = []

    for model_name, poems in model_groups.items():
        print(f"\n{'='*50}")
        print(f"正在分析模型: {model_name} ({len(poems)} 首词)")
        print(f"{'='*50}")

        sentences = []
        poem_id_map = defaultdict(list)
        cipai_sentence_map = defaultdict(list)
        
        for poem in poems:
            poem_sents = split_into_sentences(poem["content"])
            for idx, s in enumerate(poem_sents):
                sent_data = {
                    "poem_id": poem["id"],
                    "model": poem["model_name"],
                    "cipai": poem["cipai"],
                    "title": poem["title"],
                    "text": s,
                    "sent_idx": idx
                }
                sentences.append(sent_data)
                poem_id_map[poem["id"]].append(len(sentences) - 1)
                cipai_sentence_map[poem["cipai"]].append(len(sentences) - 1)

        num_sentences = len(sentences)
        print(f"拆分出 {num_sentences} 个句子")

        if num_sentences < 2:
            print("句子数量不足，跳过")
            continue

        print("\n正在计算句子向量...")
        texts = [s["text"] for s in sentences]
        embeddings = model.encode(texts, batch_size=256, convert_to_tensor=True, show_progress_bar=False)
        print("向量计算完成！")

        print("\n正在计算语义相似度矩阵...")
        cos_matrix = util.cos_sim(embeddings, embeddings)
        cos_np = cos_matrix.cpu().numpy() if cos_matrix.is_cuda else cos_matrix.numpy()

        print("正在筛选跨词句对...")
        cross_poem_pairs = []
        poem_ids_list = [s["poem_id"] for s in sentences]
        
        for i in range(num_sentences):
            for j in range(i + 1, num_sentences):
                if poem_ids_list[i] != poem_ids_list[j]:
                    sem_sim = cos_np[i, j]
                    cross_poem_pairs.append((i, j, sem_sim))

        total_cross_pairs = len(cross_poem_pairs)
        print(f"跨词句对数: {total_cross_pairs}")

        print(f"\n正在使用多进程计算字面相似度 ({min(4, mp.cpu_count())} 核)...")
        
        high_sim_heap = []
        all_sem_sims = []
        all_lex_sims = []
        all_diffs = []
        
        num_workers = min(4, mp.cpu_count())
        
        def task_generator():
            for i, j, sem_sim in cross_poem_pairs:
                yield (int(i), int(j), float(sem_sim))
        
        with mp.Pool(processes=num_workers, initializer=init_worker, initargs=(texts,)) as pool:
            processed = 0
            for i, j, sem_sim, lex_sim in pool.imap_unordered(calc_lexical_batch, task_generator(), chunksize=100):
                all_sem_sims.append(sem_sim)
                all_lex_sims.append(lex_sim)
                all_diffs.append(sem_sim - lex_sim)
                
                if sem_sim >= HIGH_SIM_THRESHOLD:
                    if len(high_sim_heap) < TOP_PAIRS_LIMIT:
                        heapq.heappush(high_sim_heap, (sem_sim, i, j, lex_sim))
                    elif sem_sim > high_sim_heap[0][0]:
                        heapq.heapreplace(high_sim_heap, (sem_sim, i, j, lex_sim))
                
                processed += 1
                if processed % max(1, total_cross_pairs // 10) == 0:
                    print(f"   进度: {processed}/{total_cross_pairs} ({processed*100//total_cross_pairs}%)")

        high_sim_heap.sort(key=lambda x: -x[0])
        
        percentiles_sem = calc_percentiles(all_sem_sims)
        percentiles_lex = calc_percentiles(all_lex_sims)
        percentiles_diff = calc_percentiles(all_diffs)
        high_ratio_sem = calc_high_sim_ratio(all_sem_sims)
        high_ratio_lex = calc_high_sim_ratio(all_lex_sims, threshold=LEXICAL_LOW_THRESHOLD)
        pseudo_ratio = calc_pseudo_ratio(all_sem_sims, all_lex_sims)
        entropy_sem = calc_diversity_entropy(all_sem_sims)
        entropy_lex = calc_diversity_entropy(all_lex_sims)
        composite = calc_composite_score(
            percentiles_sem[50], percentiles_sem[90]
        )

        model_results[model_name] = {
            "poem_count": len(poems),
            "sentence_count": num_sentences,
            "cross_pair_count": total_cross_pairs,
            "p25_sem": percentiles_sem[25],
            "p50_sem": percentiles_sem[50],
            "p75_sem": percentiles_sem[75],
            "p90_sem": percentiles_sem[90],
            "p95_sem": percentiles_sem[95],
            "p50_lex": percentiles_lex[50],
            "p90_lex": percentiles_lex[90],
            "p50_diff": percentiles_diff[50],
            "p90_diff": percentiles_diff[90],
            "high_ratio_sem": high_ratio_sem,
            "high_ratio_lex": high_ratio_lex,
            "pseudo_ratio": pseudo_ratio,
            "entropy_sem": entropy_sem,
            "entropy_lex": entropy_lex,
            "composite_score": composite,
            "all_sims": all_sem_sims,
        }

        print(f"\n模型 {model_name} 统计:")
        print(f"  - 语义P50: {percentiles_sem[50]:.4f}, P90: {percentiles_sem[90]:.4f}")
        print(f"  - 字面P50: {percentiles_lex[50]:.4f}, P90: {percentiles_lex[90]:.4f}")
        print(f"  - 差值P50: {percentiles_diff[50]:.4f}, P90: {percentiles_diff[90]:.4f}")
        print(f"  - 高语义相似比例: {high_ratio_sem:.4f}")
        print(f"  - 高字面相似比例: {high_ratio_lex:.4f}")
        print(f"  - 伪原创比例: {pseudo_ratio:.4f}")
        print(f"  - 综合评分: {composite:.4f}")

        for item in high_sim_heap:
            sem_sim, i, j, lex_sim = item
            s1, s2 = sentences[i], sentences[j]
            all_high_sim_pairs.append({
                "model": model_name,
                "s1": s1, "s2": s2,
                "sem_sim": sem_sim, "lex_sim": lex_sim,
            })

        print("\n正在计算词牌级统计...")
        for cipai, sent_indices in cipai_sentence_map.items():
            if len(sent_indices) < 2:
                continue
            
            cipai_sem_sims = []
            cipai_lex_sims = []
            cipai_diffs = []
            poem_ids_in_cipai = [poem_ids_list[idx] for idx in sent_indices]
            
            for idx1 in range(len(sent_indices)):
                for idx2 in range(idx1 + 1, len(sent_indices)):
                    i, j = sent_indices[idx1], sent_indices[idx2]
                    if poem_ids_in_cipai[idx1] != poem_ids_in_cipai[idx2]:
                        sem_sim = cos_np[i, j]
                        lex_sim = calc_lexical_similarity(texts[i], texts[j])
                        cipai_sem_sims.append(sem_sim)
                        cipai_lex_sims.append(lex_sim)
                        cipai_diffs.append(sem_sim - lex_sim)
            
            if cipai_sem_sims:
                cipai_percentiles_sem = calc_percentiles(cipai_sem_sims)
                cipai_percentiles_lex = calc_percentiles(cipai_lex_sims)
                cipai_percentiles_diff = calc_percentiles(cipai_diffs)
                cipai_high_ratio_sem = calc_high_sim_ratio(cipai_sem_sims)
                cipai_high_ratio_lex = calc_high_sim_ratio(cipai_lex_sims, threshold=LEXICAL_LOW_THRESHOLD)
                cipai_pseudo_ratio = calc_pseudo_ratio(cipai_sem_sims, cipai_lex_sims)
                cipai_entropy_sem = calc_diversity_entropy(cipai_sem_sims)
                cipai_composite = calc_composite_score(
                    cipai_percentiles_sem[50], cipai_percentiles_sem[90]
                )
                
                cipai_results.append({
                    "model": model_name,
                    "cipai": cipai,
                    "poem_count": len(set(poem_ids_in_cipai)),
                    "sentence_count": len(sent_indices),
                    "cross_pair_count": len(cipai_sem_sims),
                    "p50_sem": cipai_percentiles_sem[50],
                    "p90_sem": cipai_percentiles_sem[90],
                    "p50_lex": cipai_percentiles_lex[50],
                    "p90_lex": cipai_percentiles_lex[90],
                    "p50_diff": cipai_percentiles_diff[50],
                    "high_ratio_sem": cipai_high_ratio_sem,
                    "high_ratio_lex": cipai_high_ratio_lex,
                    "pseudo_ratio": cipai_pseudo_ratio,
                    "entropy_sem": cipai_entropy_sem,
                    "composite_score": cipai_composite,
                })

    print("\n" + "="*60)
    print("正在导出 CSV 报告...")
    
    print(f"导出模型级统计: {CSV_MODEL_SUMMARY}")
    with open(CSV_MODEL_SUMMARY, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "模型", "词数", "句数", "跨词句对数",
            "语义P25", "语义P50", "语义P75", "语义P90", "语义P95",
            "字面P50", "字面P90", "差值P50", "差值P90",
            "高语义比例", "高字面比例", "伪原创比例",
            "语义熵", "字面熵", "综合评分"
        ])
        for m, d in sorted(model_results.items()):
            writer.writerow([
                m, d["poem_count"], d["sentence_count"], d["cross_pair_count"],
                f"{d['p25_sem']:.4f}", f"{d['p50_sem']:.4f}", f"{d['p75_sem']:.4f}",
                f"{d['p90_sem']:.4f}", f"{d['p95_sem']:.4f}",
                f"{d['p50_lex']:.4f}", f"{d['p90_lex']:.4f}",
                f"{d['p50_diff']:.4f}", f"{d['p90_diff']:.4f}",
                f"{d['high_ratio_sem']:.4f}", f"{d['high_ratio_lex']:.4f}",
                f"{d['pseudo_ratio']:.4f}",
                f"{d['entropy_sem']:.4f}", f"{d['entropy_lex']:.4f}",
                f"{d['composite_score']:.4f}"
            ])

    print(f"导出词牌级统计: {CSV_CIPAI_SUMMARY}")
    with open(CSV_CIPAI_SUMMARY, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "模型", "词牌", "词数", "句数", "跨词句对数",
            "语义P50", "语义P90", "字面P50", "字面P90", "差值P50",
            "高语义比例", "高字面比例", "伪原创比例",
            "语义熵", "综合评分"
        ])
        for item in cipai_results:
            writer.writerow([
                item["model"], item["cipai"], item["poem_count"], item["sentence_count"],
                item["cross_pair_count"],
                f"{item['p50_sem']:.4f}", f"{item['p90_sem']:.4f}",
                f"{item['p50_lex']:.4f}", f"{item['p90_lex']:.4f}",
                f"{item['p50_diff']:.4f}",
                f"{item['high_ratio_sem']:.4f}", f"{item['high_ratio_lex']:.4f}",
                f"{item['pseudo_ratio']:.4f}",
                f"{item['entropy_sem']:.4f}",
                f"{item['composite_score']:.4f}"
            ])

    print(f"导出高相似句对: {CSV_HIGH_SIM_PAIRS}")
    with open(CSV_HIGH_SIM_PAIRS, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "模型", "句1词牌", "句1题目", "句1内容",
            "句2词牌", "句2题目", "句2内容",
            "语义相似度", "字面相似度", "差值(伪原创指数)"
        ])
        for pair in all_high_sim_pairs[:TOP_PAIRS_LIMIT]:
            s1, s2 = pair["s1"], pair["s2"]
            diff = pair["sem_sim"] - pair["lex_sim"]
            writer.writerow([
                pair["model"], s1["cipai"], s1["title"], s1["text"],
                s2["cipai"], s2["title"], s2["text"],
                f"{pair['sem_sim']:.4f}", f"{pair['lex_sim']:.4f}", f"{diff:.4f}"
            ])

    print("\n正在生成可视化图表...")
    
    render_boxplot(model_results, HTML_BOXPLOT)
    render_heatmap(cipai_results, HTML_HEATMAP)
    render_kde(model_results, HTML_KDE)
    render_radar(model_results, HTML_RADAR)

    print("\n" + "="*60)
    print("分析完成！统计信息：")
    print(f"  - 分析模型数: {len(model_results)}")
    print(f"  - 词牌组合数: {len(cipai_results)}")
    print(f"  - 高相似句对数: {len(all_high_sim_pairs)}")
    print("="*60)

if __name__ == "__main__":
    main()