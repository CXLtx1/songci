import sqlite3
import torch
import csv
from sentence_transformers import SentenceTransformer, util

# ==========================================
# 1. 基础配置区
# ==========================================
AI_DB_NAME = "database/song_ci_research_C_1.db"
HUMAN_DB_NAME = "database/real_song_ci_dataset.db"

# 目标分析的词牌名
TARGET_CIPAIS =["浣溪沙", "念奴娇"]

# 语义相似度阈值 (BGE 模型余弦值普遍偏高，跨源对比建议设在 0.85 ~ 0.90)
SEMANTIC_THRESHOLD = 0.86

EMBEDDING_MODEL_NAME = "BAAI/bge-large-zh-v1.5"

# 输出报告文件
TXT_REPORT_FILE = "result/ai_vs_human_report.txt"
CSV_RESULT_FILE = "result/ai_vs_human_results.csv"

# ==========================================
# 2. 数据库读取函数
# ==========================================
def load_ai_data():
    conn = sqlite3.connect(AI_DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 动态生成 SQL 的 IN 语句占位符
    placeholders = ",".join(["?"] * len(TARGET_CIPAIS))
    query = f"SELECT id, cipai, title, content, model_name FROM ci_data WHERE content != '' AND cipai IN ({placeholders})"
    
    cursor.execute(query, TARGET_CIPAIS)
    records = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return records

def load_human_data():
    conn = sqlite3.connect(HUMAN_DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    placeholders = ",".join(["?"] * len(TARGET_CIPAIS))
    query = f"SELECT id, cipai, full_rhythmic, author, content FROM real_ci_data WHERE content != '' AND cipai IN ({placeholders})"
    
    cursor.execute(query, TARGET_CIPAIS)
    records = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return records

# ==========================================
# 3. 主程序
# ==========================================
def main():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print("="*60)
    print(f"🖥️ 设备: {device.upper()} | 正在加载模型: {EMBEDDING_MODEL_NAME} ...")
    model = SentenceTransformer(EMBEDDING_MODEL_NAME, device=device)
    print("✅ 模型加载完成！")

    print("\n⏳ 正在从两个数据库读取数据...")
    try:
        ai_records = load_ai_data()
        human_records = load_human_data()
    except Exception as e:
        print(f"❌ 数据库读取失败: {e}")
        return

    print(f"📦 成功加载 AI 词作: {len(ai_records)} 首")
    print(f"📦 成功加载 历史真实词作: {len(human_records)} 首")
    if not ai_records or not human_records:
        print("⚠️ 数据不足，无法进行对比。请检查数据库或目标词牌名。")
        return

    # 按词牌将数据分组
    ai_groups = {cipai:[] for cipai in TARGET_CIPAIS}
    for r in ai_records: ai_groups[r["cipai"]].append(r)
        
    human_groups = {cipai:[] for cipai in TARGET_CIPAIS}
    for r in human_records: human_groups[r["cipai"]].append(r)

    print(f"\n🚀 开始【跨时空】语义碰撞溯源分析...")
    print(f"⚠️ 相似度报警阈值: {SEMANTIC_THRESHOLD}")
    print("="*60)

    cross_similar_pairs =[]

    # ==========================================
    # 4. 核心对比逻辑
    # ==========================================
    for cipai in TARGET_CIPAIS:
        ai_subset = ai_groups[cipai]
        human_subset = human_groups[cipai]
        
        if not ai_subset or not human_subset:
            print(f"⏭️ 词牌《{cipai}》数据不足(AI:{len(ai_subset)}, 古人:{len(human_subset)})，跳过...")
            continue
            
        print(f"🔍 正在对比词牌: 《{cipai}》 (AI样本: {len(ai_subset)} vs 历史样本: {len(human_subset)})")
        
        # 提取文本内容
        ai_texts = [r["content"] for r in ai_subset]
        human_texts = [r["content"] for r in human_subset]
        
        # 批量转换为高维张量
        ai_embeddings = model.encode(ai_texts, convert_to_tensor=True)
        human_embeddings = model.encode(human_texts, convert_to_tensor=True)
        
        # 计算交叉余弦相似度矩阵
        # 结果是一个尺寸为 (len(ai_texts) x len(human_texts)) 的矩阵
        cosine_scores = util.cos_sim(ai_embeddings, human_embeddings)
        
        # 遍历矩阵，找出超过阈值的对子
        for i in range(len(ai_subset)):
            for j in range(len(human_subset)):
                score = cosine_scores[i][j].item()
                if score >= SEMANTIC_THRESHOLD:
                    cross_similar_pairs.append({
                        "cipai": cipai,
                        "score": score,
                        "ai": ai_subset[i],
                        "human": human_subset[j]
                    })

    # 按相似度从高到低排序
    cross_similar_pairs.sort(key=lambda x: x["score"], reverse=True)
    total_found = len(cross_similar_pairs)

    # ==========================================
    # 5. 输出报告与图表
    # ==========================================
    print("\n💾 正在将“抄袭/模仿”溯源结果写入文件...")
    
    with open(TXT_REPORT_FILE, "w", encoding="utf-8") as txt_file, \
         open(CSV_RESULT_FILE, "w", encoding="utf-8-sig", newline="") as csv_file:
        
        txt_file.write(f"=== AI 宋词生成：历史真实溯源分析报告 ===\n")
        txt_file.write(f"溯源分析模型: {EMBEDDING_MODEL_NAME}\n")
        txt_file.write(f"疑似模仿阈值: {SEMANTIC_THRESHOLD}\n")
        txt_file.write(f"共发现 AI 高度模仿古人作品: {total_found} 对\n")
        txt_file.write("="*60 + "\n\n")

        csv_writer = csv.writer(csv_file)
        csv_writer.writerow([
            "词牌名", "意境相似度", 
            "AI模型", "AI_ID", "AI_题目", "AI_正文", 
            "古代作者", "真实_ID", "古词题目", "古词正文"
        ])

        for idx, pair in enumerate(cross_similar_pairs, 1):
            score = pair["score"]
            cipai = pair["cipai"]
            ai = pair["ai"]
            human = pair["human"]
            
            display_text = (
                f"[{idx}] 🚨 溯源成功！词牌:《{cipai}》 | 意境相似度: {score:.4f}\n"
                f"   🤖 [AI生成: {ai['model_name']}] (ID:{ai['id']})《{ai['title']}》:\n"
                f"      {ai['content']}\n"
                f"   📜 [古人原版: {human['author']}] (ID:{human['id']})《{human['full_rhythmic']}》:\n"
                f"      {human['content']}\n"
                f"{'-'*60}\n"
            )
            
            # 终端打印前 5 个最典型的案例
            if idx <= 5:
                print(display_text, end="")
            elif idx == 6:
                print(f"... 更多结果已折叠，请查看 {TXT_REPORT_FILE} ...\n")

            txt_file.write(display_text)
            
            csv_writer.writerow([
                cipai, round(score, 4), 
                ai["model_name"], ai["id"], ai["title"], ai["content"],
                human["author"], human["id"], human["full_rhythmic"], human["content"]
            ])

    print("="*60)
    print(f"🎉 跨时空溯源分析完毕！找出 {total_found} 对 AI 疑似模仿的词作。")
    print(f"📄 文本分析报告已保存至: {TXT_REPORT_FILE}")
    print(f"📊 结构化数据表已保存至: {CSV_RESULT_FILE}")

if __name__ == "__main__":
    main()