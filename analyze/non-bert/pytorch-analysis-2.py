import sqlite3
import torch
import csv
import difflib
import networkx as nx
from itertools import combinations
from sentence_transformers import SentenceTransformer, util
from pyecharts import options as opts
from pyecharts.charts import Graph
import re
from pyecharts.commons.utils import JsCode
# ==========================================
# 1. 基础配置区
# ==========================================
DB_NAME = "database/song_ci_research_B_3.db"
EMBEDDING_MODEL_NAME = "BAAI/bge-large-zh-v1.5"

# [核心判定阈值]
SEMANTIC_THRESHOLD = 0.88  
LEXICAL_LOW_THRESHOLD = 0.45 

#[新增：网络图"去毛线球"精简配置]
GRAPH_MAX_EDGES = 1000      # 只保留全局相似度最高的 Top 100 条连线（控制图的密度）

# 输出文件
HIDDEN_CONNECTIONS_CSV = "result/B-3-hidden_connections_report.csv"
GRAPH_HTML_FILE = "result/B-3-semantic_network_universe.html"

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
# 3. 绘图引擎 (原生 JS 接管换行版)
# ==========================================
def render_semantic_graph(G, categories_list):
    nodes, links = [],[]
    
    for node_id, data in G.nodes(data=True):
        raw_content = data.get("content", "")
        
        # 1. 先把 Python 里原本的换行符 \n 替换成 <br/>
        formatted_content = raw_content.replace("\n", "<br/>")
        # 2. 在逗号、句号等标点符号后面强行加上 <br/>
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
            "value": f"语义相似度: {data['weight']*100:.1f}%"
        })

    echarts_categories =[{"name": cat} for cat in categories_list]

    # 🌟 核心魔法：原生 JS 代码接管 Tooltip 渲染
    js_formatter = """
    function (params) {
        if (params.dataType === 'edge') {
            return params.name + '<br/>' + params.value;
        } else {
            return '<b>节点 ID: ' + params.name + '</b><br/><br/>' + params.value;
        }
    }
    """

    c = (
        Graph(init_opts=opts.InitOpts(width="100%", height="800px", page_title="AI宋词核心语义簇"))
        .add(
            "", nodes, links,
            categories=echarts_categories,
            layout="force", repulsion=1500,
            edge_symbol=["none", "none"],
            linestyle_opts=opts.LineStyleOpts(width=3, curve=0.2, opacity=0.7, color="source"),
            tooltip_opts=opts.TooltipOpts(
                is_show=True, 
                # 🌟 使用 JsCode 包装我们的 JS 函数，彻底绕过 ECharts 的安全转义
                formatter=JsCode(js_formatter),
                background_color="rgba(255, 255, 255, 0.95)",  # 调亮背景色防重叠
                border_color="#ccc",
                border_width=1,
                textstyle_opts=opts.TextStyleOpts(color="#333", font_size=13),
            )
        )
        .set_global_opts(
            title_opts=opts.TitleOpts(
                title="AI宋词高维语义：代表性核心图谱", 
                subtitle="鼠标悬停可查看详情（已修复自动换行）"
            ),
            legend_opts=opts.LegendOpts(orient="vertical", pos_left="2%", pos_top="10%")
        )
    )
    c.render(GRAPH_HTML_FILE)
    print(f"📊 图表已修复换行问题并重新生成: {GRAPH_HTML_FILE}")

# ==========================================
# 4. 主程序
# ==========================================
def main():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"🖥️ 设备: {device.upper()} | 正在加载模型: {EMBEDDING_MODEL_NAME} ...")
    model = SentenceTransformer(EMBEDDING_MODEL_NAME, device=device)

    # 1. 读取数据库并映射名称
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
        cipai_groups.setdefault(r["cipai"],[]).append(r)
        models_set.add(r["model_name"])

    model_homogeneity_scores = {m:[] for m in models_set}
    cipai_homogeneity_scores = {c:[] for c in cipai_groups.keys()}
    
    hidden_connections =[]
    all_potential_edges =[] # 【修改点】收集所有连线，先不急着画图

    # 2. 逐个词牌进行分析
    for cipai, subset in cipai_groups.items():
        if len(subset) < 2: continue
        
        texts =[row["content"] for row in subset]
        embeddings = model.encode(texts, convert_to_tensor=True)
        cos_matrix = util.cos_sim(embeddings, embeddings)

        for i in range(len(texts)):
            for j in range(i + 1, len(texts)):
                p1, p2 = subset[i], subset[j]
                
                sem_sim = cos_matrix[i][j].item()
                lex_sim = calc_lexical_similarity(p1["content"], p2["content"])

                # A. 指标统计
                cipai_homogeneity_scores[cipai].append(sem_sim)
                if p1["model_name"] == p2["model_name"]:
                    model_homogeneity_scores[p1["model_name"]].append(sem_sim)

                # B. 暗箱雷同
                if sem_sim >= SEMANTIC_THRESHOLD and lex_sim <= LEXICAL_LOW_THRESHOLD:
                    hidden_connections.append({
                        "cipai": cipai, "sem_sim": sem_sim, "lex_sim": lex_sim,
                        "p1": p1, "p2": p2
                    })

                # C. 收集语义达标的网络图连线备选池
                if sem_sim >= SEMANTIC_THRESHOLD:
                    all_potential_edges.append((p1, p2, sem_sim))

    # ==========================================
    # 【新增阶段】网络拓扑修剪 (Graph Pruning)
    # ==========================================
    # 1. 按照相似度从高到低排序所有找出来的连线
    all_potential_edges.sort(key=lambda x: x[2], reverse=True)
    # 2. 截断：只保留前 GRAPH_MAX_EDGES 条最强关联
    representative_edges = all_potential_edges[:GRAPH_MAX_EDGES]
    
    # 3. 构建精简后的图
    G = nx.Graph()
    for p1, p2, sem_sim in representative_edges:
        # 只有存在连线的节点才会被加入图中（天然剔除孤立节点）
        if not G.has_node(p1["id"]):
            G.add_node(p1["id"], content=f"【{p1['model_name']} - {p1['cipai']}】《{p1['title']}》\n{p1['content']}", model=p1["model_name"])
        if not G.has_node(p2["id"]):
            G.add_node(p2["id"], content=f"【{p2['model_name']} - {p2['cipai']}】《{p2['title']}》\n{p2['content']}", model=p2["model_name"])
        G.add_edge(p1["id"], p2["id"], weight=sem_sim)


    # 3. 输出各项指标 (同质化指数 / 暗箱雷同)
    print("\n" + "="*50)
    for m, scores in model_homogeneity_scores.items():
        if scores:
            print(f"  - {m}: {sum(scores)/len(scores):.4f} (样本对数: {len(scores)})")

    print("\n📉 各词牌【全局套路化指数】(所有模型在该词牌下的平均语义相似度)：")
    for c, scores in cipai_homogeneity_scores.items():
        if scores:
            print(f"  - 《{c}》: {sum(scores)/len(scores):.4f}")

    print("\n" + "="*50)
    hidden_connections.sort(key=lambda x: x["sem_sim"] - x["lex_sim"], reverse=True) 
    print(f"🕵️ 共发现 {len(hidden_connections)} 对『伪原创』！已导出至 {HIDDEN_CONNECTIONS_CSV}")

    # 5. 生成精简版网络图
    print("\n" + "="*50)
    render_semantic_graph(G, list(models_set))

if __name__ == "__main__":
    main()