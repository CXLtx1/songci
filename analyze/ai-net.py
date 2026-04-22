import pandas as pd
import numpy as np
import networkx as nx
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from pyecharts import options as opts
from pyecharts.charts import Graph
import networkx.algorithms.community as nx_comm

# ==========================================
# 1. 准备数据 (模拟 AI 批量生成的词作)
# ==========================================
# 为了演示，我们模拟了3个隐藏的“模板流派”，看看算法能否自动把它们连成网络并分类
mock_data =[
    # 模板A：类似《水调歌头·明月几时有》的缝合怪
    {"id": 1, "content": "明月几时有，把酒问青天。不知天上宫阙，今夕是何年。我欲乘风归去，又恐琼楼玉宇，高处不胜寒。"},
    {"id": 2, "content": "皎月几时有，举杯问青天。不知云中宫阙，今夕是何年。我欲乘风飞去，又恐琼楼玉宇，孤影不胜寒。"},
    {"id": 3, "content": "明月何时有，携酒问苍天。遥望天上宫阙，今夕是何年。我欲凌风归去，却恐琼楼玉宇，清冷不胜寒。"},
    {"id": 4, "content": "孤月几时有，对酒问青天。莫叹天上宫阙，今夕是何年。我欲随风归去，又怕琼楼玉宇，独自不胜寒。"},
    
    # 模板B：类似《如梦令》的缝合怪
    {"id": 5, "content": "昨夜雨疏风骤，浓睡不消残酒。试问卷帘人，却道海棠依旧。知否，知否？应是绿肥红瘦。"},
    {"id": 6, "content": "昨夜风疏雨骤，惊醒不消愁酒。欲问卷帘人，却道落花依旧。知否，知否？应是绿暗红透。"},
    {"id": 7, "content": "半夜雨狂风骤，独坐不消残酒。笑问卷帘人，却道繁花依旧。知否，知否？总是惹人烦瘦。"},
    
    # 模板C：类似《雨霖铃》的羁旅离别风
    {"id": 8, "content": "寒蝉凄切，对长亭晚，骤雨初歇。都门帐饮无绪，留恋处，兰舟催发。"},
    {"id": 9, "content": "秋蝉悲切，对古亭晚，阵雨初歇。城门举杯无绪，伤心处，孤舟催发。"},
    {"id": 10, "content": "暮蝉凄切，望长亭晚，暴雨初歇。都门送别无绪，回头处，客舟催发。"},
    
    # 游离节点：一首完全不同的原创词（相似度低，不会与上面的成簇）
    {"id": 11, "content": "大江东去，浪淘尽，千古风流人物。故垒西边，人道是，三国周郎赤壁。"}
]

df = pd.DataFrame(mock_data)
contents = df['content'].tolist()

# ==========================================
# 2. 计算文本相似度矩阵 (TF-IDF + Cosine)
# ==========================================
print("正在计算词作相似度...")
vectorizer = TfidfVectorizer(analyzer='char', ngram_range=(1, 2))
tfidf_matrix = vectorizer.fit_transform(contents)
sim_matrix = cosine_similarity(tfidf_matrix)

# 设定相似度阈值：超过此值才在图上连线
SIMILARITY_THRESHOLD = 0.55 

# ==========================================
# 3. 构建 NetworkX 网络图
# ==========================================
print("正在构建网络关系图...")
G = nx.Graph()

# 添加节点
for i in range(len(df)):
    G.add_node(
        str(df.iloc[i]['id']), # 节点ID必须是字符串，方便 pyecharts
        content=df.iloc[i]['content']
    )

# 添加边（连线）
for i in range(len(df)):
    for j in range(i + 1, len(df)):
        sim_score = sim_matrix[i][j]
        if sim_score >= SIMILARITY_THRESHOLD:
            # 添加连线，权重为相似度
            G.add_edge(str(df.iloc[i]['id']), str(df.iloc[j]['id']), weight=sim_score)

# ==========================================
# 4. 社区发现 (自动找出 AI 的“模板流派”)
# ==========================================
print("正在进行社区聚类分析...")
# 使用贪婪模块度最大化算法进行聚类
communities = list(nx_comm.greedy_modularity_communities(G))

# 为每个节点打上“类别”标签
node_category = {}
for idx, comm in enumerate(communities):
    for node in comm:
        node_category[node] = idx

# 补充没有连线的孤立节点类别
for node in G.nodes():
    if node not in node_category:
        node_category[node] = len(communities)

# ==========================================
# 5. 使用 Pyecharts 生成可交互的可视化网页
# ==========================================
print("正在生成 Pyecharts 可视化网页...")
nodes =[]
links = []
categories =[]

# 构建 Pyecharts 的分类（图例）
num_categories = len(set(node_category.values()))
for i in range(num_categories):
    categories.append({"name": f"AI模板簇 {i+1}"})

# 构建 Pyecharts 节点
for node_id in G.nodes():
    content = G.nodes[node_id]['content']
    # 截取前10个字作为标签展示
    short_label = f"ID:{node_id} {content[:10]}..." 
    
    nodes.append({
        "name": node_id,
        "symbolSize": 30 + G.degree(node_id) * 5, # 节点大小：连接的边越多，节点越大（说明它是核心模板）
        "category": node_category[node_id],
        "value": content, # 悬浮提示显示完整词作
        "label": {"show": True, "formatter": "{b}"}
    })

# 构建 Pyecharts 边
for u, v, data in G.edges(data=True):
    links.append({
        "source": u,
        "target": v,
        "value": round(data['weight'], 2)
    })

# 初始化图表
graph = (
    Graph(init_opts=opts.InitOpts(width="1200px", height="800px", page_title="AI宋词生成相似度网络"))
    .add(
        "",
        nodes=nodes,
        links=links,
        categories=categories,
        layout="force", # 力引导布局，能自动把有连接的节点拉在一起
        repulsion=4000, # 节点之间的斥力，值越大节点越分散
        is_roam=True,   # 允许鼠标缩放和平移
        is_draggable=True, # 允许拖拽节点
        edge_symbol=["none", "none"], 
        edge_label=opts.LabelOpts(
            is_show=True, position="middle", formatter="{c}" # 在连线上显示相似度数值
        ),
        label_opts=opts.LabelOpts(is_show=True),
        tooltip_opts=opts.TooltipOpts(
            is_show=True, 
            # 鼠标悬浮在节点上时，显示完整诗词内容
            formatter="<b>节点 ID: {b}</b><br/>完整内容: {c}" 
        )
    )
    .set_global_opts(
        title_opts=opts.TitleOpts(
            title="AI宋词相似度网络图 (模式崩溃检测)",
            subtitle="连线代表两首词高度相似(>55%)，节点越大说明被AI'抄袭'的次数越多"
        ),
        legend_opts=opts.LegendOpts(orient="vertical", pos_left="2%", pos_top="20%")
    )
)

# 保存为 HTML 文件
output_file = "result/ai_songci_network_graph.html"
graph.render(output_file)

print(f"🎉 成功！网络图已生成，请在浏览器中打开文件: {output_file}")