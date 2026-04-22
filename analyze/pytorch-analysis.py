import sqlite3
import torch
import csv
from sentence_transformers import SentenceTransformer, util , models

# ==========================================
# 1. 基础配置区
# ==========================================
DB_NAME = "database/song_ci_research_C_1.db"
COSINE_THRESHOLD = 0.75  
EMBEDDING_MODEL_NAME = "analyze/BERT-CCPoem-Model"

TXT_REPORT_FILE = "result/BERT-semantic_similarity_report.txt"
CSV_RESULT_FILE = "result/BERT-semantic_similarity_results.csv"

def main():
    # ==========================================
    # 🌟 新增：显卡 (GPU) 检测与调用逻辑
    # ==========================================
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

    # ==========================================
    # 2. 从数据库读取数据
    # ==========================================
    try:
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT id, cipai, title, content, model_name FROM ci_data WHERE content IS NOT NULL AND content != ''")
        records = cursor.fetchall()
        conn.close()
    except Exception as e:
        print(f"❌ 数据库读取失败: {e}")
        return

    if not records:
        print("数据库中没有有效数据。")
        return

    cipai_groups = {}
    for r in records:
        cipai = r["cipai"]
        if cipai not in cipai_groups:
            cipai_groups[cipai] = []
        cipai_groups[cipai].append(dict(r))

    print(f"\n📦 开始进行意境与语义高维向量计算...")
    print(f"⚠️ 余弦相似度筛选阈值: {COSINE_THRESHOLD}\n" + "="*60)

    # ==========================================
    # 3. 计算并准备写入文件
    # ==========================================
    total_found = 0
    all_highly_similar_pairs =[]

    for cipai, subset in cipai_groups.items():
        if len(subset) < 2:
            continue
            
        print(f"正在分析词牌: 《{cipai}》 (共 {len(subset)} 首)...")
        texts = [row["content"] for row in subset]
        
        embeddings = model.encode(texts, convert_to_tensor=True)
        cosine_scores = util.cos_sim(embeddings, embeddings)
        
        for i in range(len(texts)):
            for j in range(i + 1, len(texts)):
                score = cosine_scores[i][j].item() 
                if score >= COSINE_THRESHOLD:
                    all_highly_similar_pairs.append({
                        "cipai": cipai,
                        "score": score,
                        "p1": subset[i],
                        "p2": subset[j]
                    })
    
    all_highly_similar_pairs.sort(key=lambda x: x["score"], reverse=True)
    total_found = len(all_highly_similar_pairs)

    # ==========================================
    # 4. 写入 TXT 报告 和 CSV 表格
    # ==========================================
    print("\n💾 正在将结果写入文件...")
    
    # 🌟 修复 CSV 乱码：使用 utf-8-sig
    with open(TXT_REPORT_FILE, "w", encoding="utf-8") as txt_file, \
         open(CSV_RESULT_FILE, "w", encoding="utf-8-sig", newline="") as csv_file:
        
        txt_file.write(f"=== AI 宋词生成：高维语义相似度分析报告 ===\n")
        txt_file.write(f"分析模型: {EMBEDDING_MODEL_NAME}\n")
        txt_file.write(f"计算设备: {device.upper()}\n")
        txt_file.write(f"余弦相似度阈值: {COSINE_THRESHOLD}\n")
        txt_file.write(f"共发现高度雷同词作: {total_found} 对\n")
        txt_file.write("="*60 + "\n\n")

        csv_writer = csv.writer(csv_file)
        csv_writer.writerow([
            "词牌名", "余弦相似度", "是否跨模型", 
            "模型A", "词A_ID", "词A_题目", "词A_正文", 
            "模型B", "词B_ID", "词B_题目", "词B_正文"
        ])

        for idx, pair in enumerate(all_highly_similar_pairs, 1):
            p1, p2 = pair["p1"], pair["p2"]
            sim_score = pair["score"]
            cipai = pair["cipai"]
            
            is_cross_model = p1["model_name"] != p2["model_name"]
            cross_model_flag = "⚠️[跨模型撞车]" if is_cross_model else "🔄 [单模型套路]"
            
            # 🌟 修复 TXT 疯狂重复漏洞：使用 f"{'-'*60}" 防止隐式合并乘法
            display_text = (
                f"[{idx}] {cross_model_flag} 词牌:《{cipai}》 | 意境相似度: {sim_score:.4f} (余弦值)\n"
                f"   [模型A: {p1['model_name']}] (ID:{p1['id']})《{p1['title']}》: {p1['content']}\n"
                f"   [模型B: {p2['model_name']}] (ID:{p2['id']})《{p2['title']}》: {p2['content']}\n"
                f"{'-'*60}\n"
            )
            
            print(display_text, end="")
            txt_file.write(display_text)
            
            csv_writer.writerow([
                cipai, 
                round(sim_score, 4), 
                "是" if is_cross_model else "否",
                p1["model_name"], p1["id"], p1["title"], p1["content"],
                p2["model_name"], p2["id"], p2["title"], p2["content"]
            ])

    print("="*60)
    print(f"🎉 分析完毕！共找出 {total_found} 对意境高度雷同的词作。")
    print(f"📄 文本分析报告已保存至: {TXT_REPORT_FILE}")
    print(f"📊 结构化数据表已保存至: {CSV_RESULT_FILE} ")

if __name__ == "__main__":
    main()