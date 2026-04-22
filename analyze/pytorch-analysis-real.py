import sqlite3
import torch
import re
import networkx as nx
from sentence_transformers import SentenceTransformer, util ,models
from pyecharts import options as opts
from pyecharts.charts import Graph
from pyecharts.commons.utils import JsCode

# ==========================================
# 1. 基础配置区
# ==========================================
DB_NAME = "database/real_song_ci_dataset.db"
EMBEDDING_MODEL_NAME = "analyze/BERT-CCPoem-Model"

# 🎯 目标分析的词牌名（你可以修改为 "念奴娇", "满江红", "水调歌头" 等）
TARGET_CIPAI = "浣溪沙"

# [核心判定阈值]
SEMANTIC_THRESHOLD = 0.8 
GRAPH_MAX_EDGES = 1000      # 只保留全局相似度最高的 Top 150 条连线

# 输出文件
GRAPH_HTML_FILE = f"result/BERT-historical_network_{TARGET_CIPAI}.html"

# ==========================================
# 2. 绘图引擎
# ==========================================
def render_historical_graph(G, categories_list, cipai_name):
    nodes, links = [],[]
    
    for node_id, data in G.nodes(data=True):
        raw_content = data.get("content", "")
        author = data.get("author", "佚名")
        
        # 处理换行排版
        formatted_content = raw_content.replace("\n", "<br/>")
        formatted_content = re.sub(r'([，。！？；])', r'\1<br/>', formatted_content)
        
        # 将作者和正文拼接，存入 value 中供鼠标悬浮显示
        display_value = f"<span style='color:#e74c3c; font-weight:bold;'>作者：{author}</span><br/>{formatted_content}"
        
        nodes.append({
            "name": str(node_id), 
            "value": display_value,
            # 节点大小由连线数量（被致敬的次数）决定
            "symbolSize": 15 + G.degree(node_id) * 5, 
            "category": author,  # 类别设为作者，不同作者颜色不同
            "label": {"show": False}
        })
        
    for u, v, data in G.edges(data=True):
        links.append({
            "source": str(u), "target": str(v),
            "value": f"意境相似度: {data['weight']*100:.1f}%"
        })

    echarts_categories =[{"name": cat} for cat in categories_list]

    # 原生 JS 代码接管 Tooltip（无 // 注释版）
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
        Graph(init_opts=opts.InitOpts(width="100%", height="850px", page_title=f"《{cipai_name}》大宋星系图"))
        .add(
            "", nodes, links,
            categories=echarts_categories,
            layout="force", repulsion=1200, gravity=0.1,
            edge_symbol=["none", "none"],
            linestyle_opts=opts.LineStyleOpts(width=3, curve=0.2, opacity=0.7, color="source"),
            tooltip_opts=opts.TooltipOpts(
                is_show=True, 
                formatter=JsCode(js_formatter),
                background_color="rgba(255, 255, 255, 0.95)",
                border_color="#ccc",
                border_width=1,
                textstyle_opts=opts.TextStyleOpts(color="#333", font_size=13),
            )
        )
        .set_global_opts(
            title_opts=opts.TitleOpts(
                title=f"《{cipai_name}》历史名家高维语义网络", 
                subtitle=f"连线条件：意境相似度 > {SEMANTIC_THRESHOLD} (提取 Top {GRAPH_MAX_EDGES})\n节点大小代表被“次韵/致敬”的关联次数"
            ),
            # 图例配置为 type_="scroll"（滚动条），防止古代作者太多撑爆屏幕
            legend_opts=opts.LegendOpts(
                type_="scroll", orient="vertical", 
                pos_left="1%", pos_top="15%", pos_bottom="10%"
            )
        )
    )
    c.render(GRAPH_HTML_FILE)
    print(f"📊 图表已生成: {GRAPH_HTML_FILE} (节点数:{G.number_of_nodes()}, 连线数:{G.number_of_edges()})")

# ==========================================
# 3. 主程序
# ==========================================
def main():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print("="*60)
    print(f"🖥️ 设备: {device.upper()} | 正在加载古诗词专家模型: {EMBEDDING_MODEL_NAME} ...")
    
    try:
        # 1. 加载底层的基础 BERT 模型
        word_embedding_model = models.Transformer(EMBEDDING_MODEL_NAME)
        
        # 2. 组装 Mean Pooling 层 (将所有单字/词的理解平均化，提取全句/全篇意境)
        pooling_model = models.Pooling(
            word_embedding_model.get_word_embedding_dimension(),
            pooling_mode_mean_tokens=True,
            pooling_mode_cls_token=False,
            pooling_mode_max_tokens=False
        )
        
        # 3. 缝合为一个 SentenceTransformer 句向量引擎
        model = SentenceTransformer(modules=[word_embedding_model, pooling_model], device=device)
        print("✅ BERT-CCPoem 模型与 Pooling 层组装加载完成！")
        
    except Exception as e:
        print(f"❌ 模型加载失败，请检查 ./BERT-CCPoem-Model 目录下是否有 pytorch_model.bin 等文件。详细报错: {e}")
        return

    # 1. 读取真实宋词数据库
    print(f"\n⏳ 正在读取《{TARGET_CIPAI}》的历史词作数据...")
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT id, author, full_rhythmic, content FROM real_ci_data WHERE cipai = ? AND content != ''", (TARGET_CIPAI,))
    records = [dict(r) for r in cursor.fetchall()]
    conn.close()

    if not records:
        print(f"⚠️ 数据库中未找到词牌为《{TARGET_CIPAI}》的记录，请检查数据库。")
        return

    print(f"📦 共提取到 {len(records)} 首古人真实作品。开始计算关系网...")

    # 2. 计算高维语义相似度
    texts = [r["content"] for r in records]
    embeddings = model.encode(texts, convert_to_tensor=True)
    cos_matrix = util.cos_sim(embeddings, embeddings)

    all_potential_edges =[]
    
    # 提取所有达标的边
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            sem_sim = cos_matrix[i][j].item()
            if sem_sim >= SEMANTIC_THRESHOLD:
                all_potential_edges.append((records[i], records[j], sem_sim))

    # 3. 修剪网络结构 (Top-K 提取)
    all_potential_edges.sort(key=lambda x: x[2], reverse=True)
    representative_edges = all_potential_edges[:GRAPH_MAX_EDGES]
    
    # 4. 构建精简后的图
    G = nx.Graph()
    authors_in_graph = set()

    for p1, p2, sem_sim in representative_edges:
        # 节点标题形如：晏殊《浣溪沙》
        title1 = f"{p1['author']}《{p1['full_rhythmic']}》"
        title2 = f"{p2['author']}《{p2['full_rhythmic']}》"
        
        if not G.has_node(title1):
            G.add_node(title1, content=p1['content'], author=p1['author'])
            authors_in_graph.add(p1['author'])
            
        if not G.has_node(title2):
            G.add_node(title2, content=p2['content'], author=p2['author'])
            authors_in_graph.add(p2['author'])
            
        G.add_edge(title1, title2, weight=sem_sim)

    if G.number_of_nodes() == 0:
        print("⚠️ 没有发现满足阈值的关联词作，建议将 SEMANTIC_THRESHOLD 调低再试。")
        return

    # 5. 生成网络图
    print("\n" + "="*50)
    render_historical_graph(G, list(authors_in_graph), TARGET_CIPAI)

if __name__ == "__main__":
    main()