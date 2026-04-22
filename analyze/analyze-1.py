import sqlite3
import difflib
from itertools import combinations

# ==========================================
# 参数配置
# ==========================================
DB_NAME = "database/song_ci_research.db"
# 相似度阈值：设置为 0.50 (50%)。你可以根据需要调高或调低
# > 0.5 已经意味着大量字词和句式重复
SIMILARITY_THRESHOLD = 0.50  

def calculate_similarity(text1, text2):
    """
    计算两个文本的字符级相似度
    返回 0.0 到 1.0 之间的浮点数
    """
    # SequenceMatcher 会寻找两段文本中最长的连续匹配块
    return difflib.SequenceMatcher(None, text1, text2).ratio()

def main():
    # 1. 连接数据库并读取数据
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT id, cipai, title, content FROM ci_data WHERE content != ''")
        records = cursor.fetchall()
        conn.close()
    except sqlite3.OperationalError:
        print(f"❌ 找不到数据库 {DB_NAME}，请确认生成脚本是否成功运行。")
        return

    # 2. 按词牌名分组 (只有相同词牌比较才有意义)
    cipai_groups = {}
    for row in records:
        ci_id, cipai, title, content = row
        if cipai not in cipai_groups:
            cipai_groups[cipai] = []
        cipai_groups[cipai].append({
            "id": ci_id,
            "title": title,
            "content": content
        })

    print(f"🧐 开始分析宋词相似度 (总计 {len(records)} 首)...")
    print(f"⚠️ 筛选阈值: {SIMILARITY_THRESHOLD * 100}%\n" + "="*50)
    
    high_similarity_pairs =[]

    # 3. 遍历每个词牌，进行两两组合比较
    for cipai, poems in cipai_groups.items():
        if len(poems) < 2:
            continue
        
        # itertools.combinations 帮你把该词牌下的词两两配对
        for p1, p2 in combinations(poems, 2):
            sim_score = calculate_similarity(p1["content"], p2["content"])
            
            # 如果相似度达到设定的阈值，则记录下来
            if sim_score >= SIMILARITY_THRESHOLD:
                high_similarity_pairs.append({
                    "cipai": cipai,
                    "score": sim_score,
                    "p1": p1,
                    "p2": p2
                })

    # 4. 按相似度从高到低排序
    high_similarity_pairs.sort(key=lambda x: x["score"], reverse=True)

    # 5. 输出结果
    if not high_similarity_pairs:
        print("🎉 恭喜！没有发现相似度超过阈值的词对，模型生成的多样性很好！")
        return

    print(f"🚨 共发现 {len(high_similarity_pairs)} 对高度相似的词：\n")
    for idx, pair in enumerate(high_similarity_pairs, 1):
        score_pct = pair["score"] * 100
        print(f"[{idx}] 词牌: 《{pair['cipai']}》 | 相似度: {score_pct:.2f}%")
        print(f"   👉 词A (ID:{pair['p1']['id']})《{pair['p1']['title']}》: {pair['p1']['content']}")
        print(f"   👉 词B (ID:{pair['p2']['id']})《{pair['p2']['title']}》: {pair['p2']['content']}")
        print("-" * 60)

if __name__ == "__main__":
    main()