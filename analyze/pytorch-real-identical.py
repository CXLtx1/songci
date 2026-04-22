import sqlite3
import torch
import json
import csv
from sentence_transformers import SentenceTransformer, util , models

# ==========================================
# 1. 配置区
# ==========================================
DB_NAME = "database/real_song_ci_dataset.db"
EMBEDDING_MODEL_NAME = "analyze/BERT-CCPoem-Model"

# 想要计算同质化指数的目标词牌
TARGET_CIPAIS = ["浣溪沙", "念奴娇", "水调歌头", "满江红", "蝶恋花", "菩萨蛮", "西江月", "鹧鸪天"]

# 结果保存文件
STATS_CSV_FILE = "result/BERT-historical_homogeneity_stats.csv"

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

    # 1. 读取数据
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    placeholders = ",".join(["?"] * len(TARGET_CIPAIS))
    query = f"SELECT cipai, content FROM real_ci_data WHERE content != '' AND cipai IN ({placeholders})"
    
    print(f"⏳ 正在读取数据库记录...")
    cursor.execute(query, TARGET_CIPAIS)
    records = [dict(r) for r in cursor.fetchall()]
    conn.close()

    # 按词牌分组
    groups = {}
    for r in records:
        groups.setdefault(r["cipai"], []).append(r["content"])

    print(f"📦 准备分析 {len(groups)} 个词牌，共 {len(records)} 首词。")
    print("="*60)

    # 2. 计算同质化指数 (平均相似度)
    stats_results = []

    for cipai in TARGET_CIPAIS:
        texts = groups.get(cipai, [])
        count = len(texts)
        
        if count < 2:
            print(f"⏭️ 词牌 《{cipai}》 样本不足，跳过。")
            continue

        print(f"🔍 正在计算 《{cipai}》 的同质化指数 (样本数: {count})...")

        # 将所有文本转为向量
        # 注意：如果某个词牌样本量极大（如超过5000首），请考虑增加 batch_size 或采样
        embeddings = model.encode(texts, convert_to_tensor=True, show_progress_bar=False)
        
        # 计算相似度矩阵 (N x N)
        cos_sim_matrix = util.cos_sim(embeddings, embeddings)
        
        # 提取上三角矩阵（不含对角线）的所有值
        # 也就是计算所有两两组合的相似度，但不计算自己和自己的相似度
        upper_tri_indices = torch.triu_indices(count, count, offset=1)
        sim_values = cos_sim_matrix[upper_tri_indices[0], upper_tri_indices[1]]
        
        # 计算平均值
        avg_sim = torch.mean(sim_values).item()
        max_sim = torch.max(sim_values).item()
        min_sim = torch.min(sim_values).item()

        stats_results.append({
            "cipai": cipai,
            "count": count,
            "avg_homogeneity": avg_sim,
            "max_similarity": max_sim,
            "min_similarity": min_sim
        })
        
        print(f"   📊 平均相似度: {avg_sim:.4f} | 最高相似度: {max_sim:.4f}")

    # 3. 保存并输出结果
    stats_results.sort(key=lambda x: x["avg_homogeneity"], reverse=True)

    with open(STATS_CSV_FILE, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["cipai", "count", "avg_homogeneity", "max_similarity", "min_similarity"])
        writer.writeheader()
        writer.writerows(stats_results)

    print("\n" + "="*60)
    print(f"🎉 统计完成！结果已保存至: {STATS_CSV_FILE}")
    print("\n[最终排名 - 历史同质化指数]:")
    for r in stats_results:
        print(f"《{r['cipai']:<5}》: 平均相似度 {r['avg_homogeneity']:.4f} (样本量: {r['count']})")

if __name__ == "__main__":
    main()