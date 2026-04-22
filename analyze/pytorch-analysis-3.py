import sqlite3
import torch
import csv
import re
import difflib
import heapq
import numpy as np
import multiprocessing as mp
from collections import defaultdict
from sentence_transformers import SentenceTransformer, util, models
from pyecharts import options as opts
from pyecharts.charts import Graph
from pyecharts.commons.utils import JsCode
import networkx as nx

# ==========================================
# 1. 基础配置区
# ==========================================
DB_NAME = "database/b3.db"
EMBEDDING_MODEL_NAME = "analyze/BERT-CCPoem-Model"

SEMANTIC_THRESHOLD = 0.85
LEXICAL_LOW_THRESHOLD = 0.5
GRAPH_MAX_EDGES = 500

CSV_HIDDEN_CONNECTIONS = f"result/AI-inner-sentence_hidden_connections_{DB_NAME[-5:-3]}.csv"
CSV_POEM_SUMMARY = f"result/AI-inner-sentence-similarity_{DB_NAME[-5:-3]}.csv"
GRAPH_HTML_FILE = f"result/AI-inner-sentence-similarity_network_{DB_NAME[-5:-3]}.html"

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

def calc_lexical_similarity_fast(text1, text2):
    return difflib.SequenceMatcher(None, text1, text2).ratio()

_texts_global = None

def init_worker(texts):
    global _texts_global
    _texts_global = texts

def calc_lexical_batch(args):
    i, j, sem_sim = args
    lex_sim = calc_lexical_similarity_fast(_texts_global[i], _texts_global[j])
    return (i, j, sem_sim, lex_sim)

# ==========================================
# 3. 绘图引擎
# ==========================================
def render_similarity_graph(G, categories_list, title, subtitle, output_file):
    nodes, links = [], []
    
    for node_id, data in G.nodes(data=True):
        raw_content = data.get("content", "")
        formatted_content = raw_content.replace("\n", "<br/>")
        
        nodes.append({
            "name": str(node_id),
            "value": formatted_content,
            "symbolSize": 12 + G.degree(node_id) * 3,
            "category": data.get("model", ""),
            "label": {"show": False}
        })
    
    for u, v, data in G.edges(data=True):
        links.append({
            "source": str(u), "target": str(v),
            "value": f"相似度: {data['weight']*100:.1f}%"
        })

    echarts_categories = [{"name": cat} for cat in categories_list]

    js_formatter = """
    function (params) {
        if (params.dataType === 'edge') {
            return params.name + '<br/>' + params.value;
        } else {
            return '<b>' + params.name + '</b><br/><br/>' + params.value;
        }
    }
    """

    c = (
        Graph(init_opts=opts.InitOpts(width="100%", height="900px", page_title="AI宋词句级相似性网络"))
        .add(
            "", nodes, links,
            categories=echarts_categories,
            layout="force", repulsion=1200,
            edge_symbol=["none", "none"],
            linestyle_opts=opts.LineStyleOpts(width=2, curve=0.2, opacity=0.6, color="source"),
            tooltip_opts=opts.TooltipOpts(
                is_show=True,
                formatter=JsCode(js_formatter),
                background_color="rgba(255, 255, 255, 0.95)",
                border_color="#ccc", border_width=1,
                textstyle_opts=opts.TextStyleOpts(color="#333", font_size=12),
            )
        )
        .set_global_opts(
            title_opts=opts.TitleOpts(title=title, subtitle=subtitle),
            legend_opts=opts.LegendOpts(orient="vertical", pos_left="2%", pos_top="10%")
        )
    )
    c.render(output_file)
    print(f"网络图已生成: {output_file}")

# ==========================================
# 4. 主程序
# ==========================================
def main():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print("="*60)
    print(f"[AI宋词句级内部相似性分析 - 优化版] 启动！")
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

    sentences = []
    poem_sentence_map = defaultdict(list)
    
    for poem in records:
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
            poem_sentence_map[poem["id"]].append(sent_data)

    num_sentences = len(sentences)
    print(f"拆分出 {num_sentences} 个句子")

    if num_sentences < 2:
        print("句子数量不足，退出")
        return

    print("\n正在计算句子向量...")
    texts = [s["text"] for s in sentences]
    embeddings = model.encode(texts, batch_size=256, convert_to_tensor=True, show_progress_bar=True)
    print("向量计算完成！")

    print("\n正在计算语义相似度矩阵...")
    cos_matrix = util.cos_sim(embeddings, embeddings)
    
    print("正在准备所有句对（优化版）...")
    
    models_list = [s["model"] for s in sentences]
    models_set = set(models_list)
    
    cos_np = cos_matrix.cpu().numpy() if cos_matrix.is_cuda else cos_matrix.numpy()
    
    i_indices, j_indices = np.triu_indices(num_sentences, k=1)
    sem_sims = cos_np[i_indices, j_indices]
    
    total_pairs = len(i_indices)
    print(f"总句对数: {total_pairs}")
    
    print("正在计算模型同质化指数...")
    model_homogeneity_scores = defaultdict(list)
    for idx in range(total_pairs):
        i, j = i_indices[idx], j_indices[idx]
        if models_list[i] == models_list[j]:
            model_homogeneity_scores[models_list[i]].append(sem_sims[idx])
    
    print(f"\n正在使用多进程计算字面相似度 ({min(4, mp.cpu_count())} 核)...")
    
    top_sem_heap = []
    hidden_conn_heap = []
    
    num_workers = min(4, mp.cpu_count())
    
    def task_generator():
        for idx in range(total_pairs):
            yield (int(i_indices[idx]), int(j_indices[idx]), float(sem_sims[idx]))
    
    with mp.Pool(processes=num_workers, initializer=init_worker, initargs=(texts,)) as pool:
        processed = 0
        for i, j, sem_sim, lex_sim in pool.imap_unordered(calc_lexical_batch, task_generator(), chunksize=100):
            diff = sem_sim - lex_sim
            
            if len(top_sem_heap) < GRAPH_MAX_EDGES:
                heapq.heappush(top_sem_heap, (sem_sim, i, j))
            elif sem_sim > top_sem_heap[0][0]:
                heapq.heapreplace(top_sem_heap, (sem_sim, i, j))
            
            if sem_sim >= SEMANTIC_THRESHOLD and lex_sim <= LEXICAL_LOW_THRESHOLD:
                if len(hidden_conn_heap) < GRAPH_MAX_EDGES:
                    heapq.heappush(hidden_conn_heap, (diff, i, j, sem_sim, lex_sim))
                elif diff > hidden_conn_heap[0][0]:
                    heapq.heapreplace(hidden_conn_heap, (diff, i, j, sem_sim, lex_sim))
            
            processed += 1
            if processed % max(1, total_pairs // 10) == 0:
                print(f"   进度: {processed}/{total_pairs} ({processed*100//total_pairs}%)")
    
    top_sem_heap.sort(key=lambda x: -x[0])
    hidden_conn_heap.sort(key=lambda x: -x[0])
    
    print(f"发现 {len(hidden_conn_heap)} 对『高级伪原创』（高语义相似且低字面重合）")

    print("\n" + "="*60)
    print("模型同质化指数（句级）：")
    for m, scores in sorted(model_homogeneity_scores.items()):
        if scores:
            avg = sum(scores) / len(scores)
            print(f"  - {m}: {avg:.4f} (样本对数: {len(scores)})")

    print(f"\n正在导出 Hidden Connections CSV: {CSV_HIDDEN_CONNECTIONS}")
    with open(CSV_HIDDEN_CONNECTIONS, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "句1模型", "句1词牌", "句1题目", "句1内容",
            "句2模型", "句2词牌", "句2题目", "句2内容",
            "语义相似度", "字面相似度", "差值(伪原创指数)"
        ])
        for item in hidden_conn_heap:
            diff, i, j, sem_sim, lex_sim = item
            s1, s2 = sentences[i], sentences[j]
            writer.writerow([
                s1["model"], s1["cipai"], s1["title"], s1["text"],
                s2["model"], s2["cipai"], s2["title"], s2["text"],
                f"{sem_sim:.4f}", f"{lex_sim:.4f}", f"{diff:.4f}"
            ])
    print("Hidden Connections CSV 导出成功！")

    print("\n正在计算每首词的句级相似度统计...")
    poem_stats = []
    
    for poem_id, sents in poem_sentence_map.items():
        if len(sents) < 2:
            continue
        
        poem_sem_scores = []
        poem_lex_scores = []
        
        sent_indices = [sentences.index(s) for s in sents]
        
        for idx1 in range(len(sent_indices)):
            for idx2 in range(idx1 + 1, len(sent_indices)):
                i, j = sent_indices[idx1], sent_indices[idx2]
                sem_sim = cos_matrix[i][j].item()
                lex_sim = calc_lexical_similarity_fast(texts[i], texts[j])
                poem_sem_scores.append(sem_sim)
                poem_lex_scores.append(lex_sim)
        
        if poem_sem_scores:
            avg_sem = sum(poem_sem_scores) / len(poem_sem_scores)
            avg_lex = sum(poem_lex_scores) / len(poem_lex_scores)
            max_sem = max(poem_sem_scores)
            max_lex = max(poem_lex_scores)
            
            poem_stats.append({
                "poem_id": poem_id,
                "model": sents[0]["model"],
                "cipai": sents[0]["cipai"],
                "title": sents[0]["title"],
                "num_sentences": len(sents),
                "avg_sem_sim": avg_sem,
                "avg_lex_sim": avg_lex,
                "max_sem_sim": max_sem,
                "max_lex_sim": max_lex
            })

    poem_stats.sort(key=lambda x: x["avg_sem_sim"], reverse=True)

    print(f"正在导出词级统计 CSV: {CSV_POEM_SUMMARY}")
    with open(CSV_POEM_SUMMARY, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "词ID", "模型", "词牌", "题目", "句数",
            "平均语义相似度", "平均字面相似度",
            "最高语义相似度", "最高字面相似度"
        ])
        for p in poem_stats:
            writer.writerow([
                p["poem_id"], p["model"], p["cipai"], p["title"], p["num_sentences"],
                f"{p['avg_sem_sim']:.4f}", f"{p['avg_lex_sim']:.4f}",
                f"{p['max_sem_sim']:.4f}", f"{p['max_lex_sim']:.4f}"
            ])
    print("词级统计 CSV 导出成功！")

    print("\n正在构建句级相似性网络图...")
    G = nx.Graph()

    for item in top_sem_heap:
        sem_sim, i, j = item
        s1, s2 = sentences[i], sentences[j]
        
        node1_id = f"{s1['poem_id']}_{s1['sent_idx']}"
        node2_id = f"{s2['poem_id']}_{s2['sent_idx']}"
        
        if not G.has_node(node1_id):
            G.add_node(node1_id,
                content=f"【{s1['model']}】《{s1['title']}》({s1['cipai']})\n{s1['text']}",
                model=s1["model"])
        
        if not G.has_node(node2_id):
            G.add_node(node2_id,
                content=f"【{s2['model']}】《{s2['title']}》({s2['cipai']})\n{s2['text']}",
                model=s2["model"])
        
        G.add_edge(node1_id, node2_id, weight=sem_sim)

    render_similarity_graph(
        G, list(models_set),
        "AI宋词句级相似性网络图谱",
        f"Top {GRAPH_MAX_EDGES} 高语义相似句对",
        GRAPH_HTML_FILE
    )

    print("\n" + "="*60)
    print("分析完成！统计信息：")
    print(f"  - 总词数: {len(records)}")
    print(f"  - 总句数: {num_sentences}")
    print(f"  - 分析句对数: {total_pairs}")
    print(f"  - Hidden Connections 数: {len(hidden_conn_heap)}")
    print(f"  - 涉及模型: {', '.join(sorted(models_set))}")
    print("="*60)

if __name__ == "__main__":
    main()
