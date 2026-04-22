import sqlite3
import torch
import csv
import difflib
import re
import networkx as nx
from itertools import combinations
from sentence_transformers import SentenceTransformer, util, models
from pyecharts import options as opts
from pyecharts.charts import Graph
from pyecharts.commons.utils import JsCode

# ==========================================
# 1. 基础配置区
# ==========================================
DB_NAME = "database/c1.db"

# 🌟 替换为你的清华古诗词模型路径
EMBEDDING_MODEL_NAME = "analyze/BERT-CCPoem-Model"

# [核心判定阈值]
# ⚠️ 注意：换了专用模型后，阈值建议先调低到 0.75 左右探底
SEMANTIC_THRESHOLD = 0.8  
LEXICAL_LOW_THRESHOLD = 0.45 

GRAPH_MAX_EDGES = 1000  # 网络图最大连线数

# 输出文件
HIDDEN_CONNECTIONS_CSV = f"result/AI-inner-whole-hidden_connections_{DB_NAME[-5:-3]}.csv"
GRAPH_HTML_FILE = f"result/AI-inner-whole-semantic_network_{DB_NAME[-5:-3]}.html"

# ==========================================
# 2. 辅助函数
# ==========================================
def map_model_name(raw_name):
    if not raw_name: return "Unknown"
    if raw_name == "doubao-seed-2-0-pro-260215": return "doubao-seed-2.0-pro"
    if raw_name in["deepseek-reasoner", "deepseek-v3.2"]: return "deepseek-3.2-thinking"
    if raw_name == "qwen3.5-plus-2026-02-15": return "qwen3.5-plus"
    return raw_name

def calc_lexical_similarity(text1, text2):
    return difflib.SequenceMatcher(None, text1, text2).ratio()

# ==========================================
# 3. 绘图引擎
# ==========================================
def render_semantic_graph(G, categories_list):
    nodes, links = [],[]
    
    for node_id, data in G.nodes(data=True):
        raw_content = data.get("content", "")
        formatted_content = raw_content.replace("\n", "<br/>")
        formatted_content = re.sub(r'([，。！？；])', r'\1<br/>', formatted_content)
        
        nodes.append({
            "name": str(node_id), 
            "value": formatted_content,
            "symbolSize": 15 + G.degree(node_id) * 4, 
            "category": data.get("model", ""),
            "label": {"show": False}
        })
        
    for u, v, data in G.edges(data=True):
        links.append({
            "source": str(u), "target": str(v),
            "value": f"意境相似度: {data['weight']*100:.1f}%"
        })

    echarts_categories =[{"name": cat} for cat in categories_list]

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
        Graph(init_opts=opts.InitOpts(width="100%", height="800px", page_title="AI宋词暗箱雷同图谱"))
        .add(
            "", nodes, links,
            categories=echarts_categories,
            layout="force", repulsion=1500,
            edge_symbol=["none", "none"],
            linestyle_opts=opts.LineStyleOpts(width=3, curve=0.2, opacity=0.7, color="source"),
            tooltip_opts=opts.TooltipOpts(
                is_show=True, 
                formatter=JsCode(js_formatter),
                background_color="rgba(255, 255, 255, 0.95)",
                border_color="#ccc", border_width=1,
                textstyle_opts=opts.TextStyleOpts(color="#333", font_size=13),
            )
        )
        .set_global_opts(
            title_opts=opts.TitleOpts(
                title="AI宋词高维语义：代表性核心图谱", 
                subtitle=f"精简策略：仅保留 Top {GRAPH_MAX_EDGES} 对最强语义连线"
            ),
            legend_opts=opts.LegendOpts(orient="vertical", pos_left="2%", pos_top="10%")
        )
    )
    c.render(GRAPH_HTML_FILE)
    print(f"📊 语义关系网络图已生成: {GRAPH_HTML_FILE}")

# ==========================================
# 4. 主程序
# ==========================================
def main():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print("="*60)
    print(f"🖥️ 设备: {device.upper()} | 正在加载古诗词专家模型: {EMBEDDING_MODEL_NAME} ...")
    
    # 🌟 修复后的 BERT-CCPoem 组装加载逻辑
    try:
        word_embedding_model = models.Transformer(EMBEDDING_MODEL_NAME)
        pooling_model = models.Pooling(
            word_embedding_model.get_word_embedding_dimension(),
            pooling_mode_mean_tokens=True,
            pooling_mode_cls_token=False,
            pooling_mode_max_tokens=False
        )
        model = SentenceTransformer(modules=[word_embedding_model, pooling_model], device=device)
        print("✅ BERT-CCPoem 模型加载成功！")
    except Exception as e:
        print(f"❌ 模型加载失败，请检查路径: {e}")
        return

    # 1. 读取数据库
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT id, cipai, title, content, model_name FROM ci_data WHERE content != ''")
    records =[dict(r) for r in cursor.fetchall()]
    conn.close()

    for r in records:
        r["model_name"] = map_model_name(r["model_name"])

    cipai_groups = {}
    models_set = set()
    for r in records:
        cipai_groups.setdefault(r["cipai"], []).append(r)
        models_set.add(r["model_name"])

    model_homogeneity_scores = {m:[] for m in models_set}
    cipai_homogeneity_scores = {c:[] for c in cipai_groups.keys()}
    
    hidden_connections = []
    all_potential_edges =[] 

    # 2. 计算各维度数据
    for cipai, subset in cipai_groups.items():
        if len(subset) < 2: continue
        
        texts = [row["content"] for row in subset]
        embeddings = model.encode(texts, convert_to_tensor=True)
        cos_matrix = util.cos_sim(embeddings, embeddings)

        for i in range(len(texts)):
            for j in range(i + 1, len(texts)):
                p1, p2 = subset[i], subset[j]
                
                sem_sim = cos_matrix[i][j].item()
                lex_sim = calc_lexical_similarity(p1["content"], p2["content"])

                # A. 记录同质化得分
                cipai_homogeneity_scores[cipai].append(sem_sim)
                if p1["model_name"] == p2["model_name"]:
                    model_homogeneity_scores[p1["model_name"]].append(sem_sim)

                # B. 暗箱雷同（高维相似，字面不同）
                if sem_sim >= SEMANTIC_THRESHOLD and lex_sim <= LEXICAL_LOW_THRESHOLD:
                    hidden_connections.append({
                        "cipai": cipai, "sem_sim": sem_sim, "lex_sim": lex_sim,
                        "p1": p1, "p2": p2
                    })

                # C. 用于画图的边收集
                if sem_sim >= SEMANTIC_THRESHOLD:
                    all_potential_edges.append((p1, p2, sem_sim))

    # 构建精简图
    all_potential_edges.sort(key=lambda x: x[2], reverse=True)
    representative_edges = all_potential_edges[:GRAPH_MAX_EDGES]
    
    G = nx.Graph()
    for p1, p2, sem_sim in representative_edges:
        if not G.has_node(p1["id"]):
            G.add_node(p1["id"], content=f"【{p1['model_name']} - {p1['cipai']}】《{p1['title']}》\n{p1['content']}", model=p1["model_name"])
        if not G.has_node(p2["id"]):
            G.add_node(p2["id"], content=f"【{p2['model_name']} - {p2['cipai']}】《{p2['title']}》\n{p2['content']}", model=p2["model_name"])
        G.add_edge(p1["id"], p2["id"], weight=sem_sim)

    # 3. 输出指标
    print("\n" + "="*50)
    for m, scores in model_homogeneity_scores.items():
        if scores:
            print(f"  - {m}: 同质化指数 {sum(scores)/len(scores):.4f} (样本对数: {len(scores)})")

    # 4. 🌟 修复遗失的写入 CSV 逻辑
    print("\n" + "="*50)
    hidden_connections.sort(key=lambda x: x["sem_sim"] - x["lex_sim"], reverse=True) 
    print(f"🕵️ 共发现 {len(hidden_connections)} 对『高级伪原创』！正在导出至 {HIDDEN_CONNECTIONS_CSV} ...")

    with open(HIDDEN_CONNECTIONS_CSV, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["词牌", "语义相似度(意境)", "字面相似度(重复率)", "差值(伪原创指数)", 
                         "模型A", "词A题目", "词A正文", "模型B", "词B题目", "词B正文"])
        
        for pair in hidden_connections:
            diff = pair["sem_sim"] - pair["lex_sim"]
            p1, p2 = pair["p1"], pair["p2"]
            writer.writerow([
                pair["cipai"], f"{pair['sem_sim']:.4f}", f"{pair['lex_sim']:.4f}", f"{diff:.4f}",
                p1["model_name"], p1["title"], p1["content"],
                p2["model_name"], p2["title"], p2["content"]
            ])
            
    print("✅ CSV 报告导出成功！")

    # 5. 画图
    print("\n" + "="*50)
    render_semantic_graph(G, list(models_set))

if __name__ == "__main__":
    main()