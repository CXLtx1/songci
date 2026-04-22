import sqlite3
import difflib
import networkx as nx
from itertools import combinations
from pyecharts import options as opts
from pyecharts.charts import Graph

# ==========================================
# 1. 基础配置区
# ==========================================
DB_NAME = "database/song_ci_research_C_1.db"  # 你的数据库文件路径
SIMILARITY_THRESHOLD = 0.50         # 相似度阈值 (70%)
TARGET_CIPAIS =["浣溪沙", "念奴娇"]  # 需要分析的词牌

# ==========================================
# 2. 数据清洗与映射逻辑
# ==========================================
def map_model_name(raw_name):
    """
    根据规则将数据库中的原始模型名称清洗为标准名称
    """
    if not raw_name:
        return "Unknown"
    
    if raw_name == "doubao-seed-2-0-pro-260215":
        return "doubao-seed-2.0-pro"
    elif raw_name in ["deepseek-reasoner"]:
        return "deepseek-3.2-thinking"
    elif raw_name == "qwen3.5-plus-2026-02-15":
        return "qwen3.5-plus"
    
    return raw_name

def calculate_similarity(text1, text2):
    """计算两个文本的字符级相似度 (0.0 ~ 1.0)"""
    return difflib.SequenceMatcher(None, text1, text2).ratio()

# ==========================================
# 3. pyecharts 绘图核心函数
# ==========================================
def render_graph(G, title, output_filename, categories_list):
    """
    将 networkx 图对象转换为 pyecharts 交互图并保存为 HTML
    """
    nodes = []
    links =[]
    
    # 提取节点信息
    for node_id, data in G.nodes(data=True):
        nodes.append({
            "name": f"ID:{node_id}",            # 节点唯一标识
            "value": data.get("content", ""),   # 鼠标悬浮显示文本
            "symbolSize": 15 + G.degree(node_id) * 2, # 节点大小：连线越多的节点越大（中心节点）
            "category": data.get("category", ""),
            "label": {"show": False}            # 默认不显示文字，以免重叠，鼠标放上去才显示
        })
        
    # 提取边信息
    for u, v, data in G.edges(data=True):
        links.append({
            "source": f"ID:{u}",
            "target": f"ID:{v}",
            "value": f"相似度: {data['weight']*100:.1f}%"
        })

    # 配置类别 (用于图例和颜色区分)
    echarts_categories = [{"name": cat} for cat in categories_list]

    # 构建并渲染 Graph
    c = (
        Graph(init_opts=opts.InitOpts(width="1200px", height="800px", page_title=title))
        .add(
            "",
            nodes,
            links,
            categories=echarts_categories,
            layout="force",                 # 强制引导布局，聚集相似节点
            is_roam=True,                   # 允许缩放和拖拽
            is_draggable=True,              # 节点可拖拽
            repulsion=800,                  # 节点之间的斥力（越大越分散）
            edge_symbol=["none", "none"],   # 无向图无箭头
            edge_symbol_size=10,
            linestyle_opts=opts.LineStyleOpts(width=2, curve=0.2, opacity=0.7, color="source"),
            label_opts=opts.LabelOpts(is_show=False),
            tooltip_opts=opts.TooltipOpts(
                is_show=True,
                # 格式化鼠标悬停的提示框，显示词的正文
                formatter="{b}<br/>{c}"
            )
        )
        .set_global_opts(
            title_opts=opts.TitleOpts(title=title),
            legend_opts=opts.LegendOpts(orient="vertical", pos_left="2%", pos_top="20%")
        )
    )
    
    c.render(f"result/{output_filename}")
    print(f"✅ 图表已生成: result/{output_filename} (节点数: {G.number_of_nodes()}, 连线数: {G.number_of_edges()})")

# ==========================================
# 4. 构建网络与处理数据的主函数
# ==========================================
def build_network_for_subset(records, title, filename_prefix, category_func):
    """
    针对给定的记录子集，计算相似度，建立网络并渲染
    category_func: 是一个函数，传入一行记录字典，返回该节点的所属类别名称
    """
    G = nx.Graph()
    
    # 记录分类去重列表
    categories_set = set()

    # 1. 添加所有节点
    for row in records:
        cat = category_func(row)
        categories_set.add(cat)
        G.add_node(
            row["id"], 
            title=row["title"], 
            content=row["content"], 
            category=cat
        )
        
    # 2. 计算两两相似度并添加边 (如果 > 70%)
    if len(records) > 1:
        for r1, r2 in combinations(records, 2):
            sim = calculate_similarity(r1["content"], r2["content"])
            if sim >= SIMILARITY_THRESHOLD:
                G.add_edge(r1["id"], r2["id"], weight=sim)

    # 3. 渲染出图
    render_graph(G, title, f"{filename_prefix}.html", list(categories_set))

def main():
    print("⏳ 正在从数据库读取并清洗数据...")
    try:
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row  # 允许使用字典方式访问列
        cursor = conn.cursor()
        cursor.execute("SELECT id, cipai, title, content, model_name FROM ci_data WHERE content IS NOT NULL AND content != ''")
        raw_data = cursor.fetchall()
        conn.close()
    except Exception as e:
        print(f"❌ 数据库读取失败: {e}")
        return

    # 1. 过滤并清洗数据
    valid_models =["doubao-seed-2.0-pro", "deepseek-3.2-thinking", "qwen3.5-plus"]
    
    cleaned_records =[]
    for row in raw_data:
        record = dict(row)
        # 映射模型名称
        record["model_name"] = map_model_name(record["model_name"])
        
        # 只保留目标词牌和目标模型
        if record["cipai"] in TARGET_CIPAIS and record["model_name"] in valid_models:
            cleaned_records.append(record)

    print(f"📦 共提取到 {len(cleaned_records)} 条有效清洗数据，开始构建关系网...")

    # ==========================================
    # 任务 1：不同模型生成的不同词牌的图（3个模型 * 2个词牌 = 6张图）
    # ==========================================
    print("\n" + "="*40 + "\n[阶段 1/3] 生成单模型单词牌图 (6张)\n" + "="*40)
    for model in valid_models:
        for cipai in TARGET_CIPAIS:
            # 筛选子集
            subset = [r for r in cleaned_records if r["model_name"] == model and r["cipai"] == cipai]
            if not subset:
                continue
            
            title = f"{model} 生成的《{cipai}》相似度网络 (阈值 {SIMILARITY_THRESHOLD})"
            filename = f"graph_1_{model}_{cipai}"
            
            # 单模型的图中，所有节点都属于同一个分类（模型名称）
            build_network_for_subset(subset, title, filename, lambda x: x["model_name"])

    # ==========================================
    # 任务 2：不同模型生成的同一词牌的图（2个词牌 = 2张图）
    # ==========================================
    print("\n" + "="*40 + "\n[阶段 2/3] 生成跨模型同词牌图 (2张)\n" + "="*40)
    for cipai in TARGET_CIPAIS:
        subset = [r for r in cleaned_records if r["cipai"] == cipai]
        if not subset:
            continue
            
        title = f"各模型《{cipai}》生成对比网络 (阈值 {SIMILARITY_THRESHOLD})"
        filename = f"graph_2_AllModels_{cipai}"
        
        # 对比图中，节点的分类以“模型名称”划分，这样会自动呈现不同颜色
        build_network_for_subset(subset, title, filename, lambda x: x["model_name"])

    # ==========================================
    # 任务 3：全部混在一起的全局宇宙图（1张）
    # ==========================================
    print("\n" + "="*40 + "\n[阶段 3/3] 生成全局汇总大图 (1张)\n" + "="*40)
    if cleaned_records:
        title = f"AI宋词生成全局相似度宇宙网 (阈值 {SIMILARITY_THRESHOLD})"
        filename = f"graph_3_Global_Universe"
        
        # 全局图中，用 "模型名 - 词牌名" 组合作为分类，例如 "qwen3.5-plus - 念奴娇"，一共会生成 6 种颜色
        build_network_for_subset(
            cleaned_records, 
            title, 
            filename, 
            lambda x: f"{x['model_name']} - {x['cipai']}"
        )

    print("\n🎉 全部 9 张交互式网络图已生成完毕！请在当前目录下双击打开对应的 .html 文件在浏览器中查看。")

if __name__ == "__main__":
    main()