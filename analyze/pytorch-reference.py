import sqlite3
import torch
import csv
import difflib
import time
import multiprocessing as mp
from sentence_transformers import SentenceTransformer, util, models

# ==========================================
# 1. 基础配置区
# ==========================================
AI_DB_NAME = "database/song_ci_research_B_1.db"
HUMAN_DB_NAME = "database/real_song_ci_dataset.db"

# 🌟 必须使用清华古诗词专家模型
EMBEDDING_MODEL_NAME = "analyze/BERT-CCPoem-Model"

# 输出文件配置
CSV_RESULT_FILE = "result/BERT-B-1-ai_full_reference_sources.csv"
TXT_REPORT_FILE = "result/BERT-B-1-ai_full_reference_report.txt"

# 提取疑似“抄袭/严重参考”的阈值底线（只输出超过这些底线的结果）
# 语义阈值 (BERT-CCPoem通常在 0.82 以上算高度致敬)
MIN_SEMANTIC_SCORE = 0.82
# 字面阈值 (传统字面相似度超过 0.35 往往意味着直接照抄了 2-3 个整句)
MIN_LEXICAL_SCORE = 0.35

# ==========================================
# 2. 多进程传统文本匹配工作区 (CPU 密集型)
# ==========================================
# 声明一个全局变量，供子进程共享全宋词数据，避免进程间传参导致内存爆炸
global_human_texts =[]

def init_worker(human_texts_arg):
    """初始化多进程 Worker，加载全宋词到该核心的内存中"""
    global global_human_texts
    global_human_texts = human_texts_arg

def compute_lexical_task(ai_item):
    """
    单个 AI 词与 2万+ 历史词作的字面比对任务
    ai_item: (ai_index, ai_text)
    """
    ai_idx, ai_text = ai_item
    best_score = 0.0
    best_h_idx = -1
    
    # 优化技巧：复用 SequenceMatcher 对象，极大提升计算速度
    matcher = difflib.SequenceMatcher(None, ai_text, "")
    
    for j, h_text in enumerate(global_human_texts):
        matcher.set_seq2(h_text)
        score = matcher.ratio()
        if score > best_score:
            best_score = score
            best_h_idx = j
            
    return ai_idx, best_h_idx, best_score

# ==========================================
# 3. 主程序
# ==========================================
def main():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print("="*60)
    print("🔍 [AI 宋词全量溯源引擎] 启动！")
    print("="*60)

    # ---------------------------------------------------------
    # 第一步：加载全部数据库 (不再限制词牌)
    # ---------------------------------------------------------
    print("⏳ 正在读取数据库...")
    conn_ai = sqlite3.connect(AI_DB_NAME)
    conn_ai.row_factory = sqlite3.Row
    ai_records =[dict(r) for r in conn_ai.execute("SELECT id, model_name, cipai, title, content FROM ci_data WHERE content != ''").fetchall()]
    conn_ai.close()

    conn_hum = sqlite3.connect(HUMAN_DB_NAME)
    conn_hum.row_factory = sqlite3.Row
    hum_records =[dict(r) for r in conn_hum.execute("SELECT id, author, full_rhythmic, cipai, content FROM real_ci_data WHERE content != ''").fetchall()]
    conn_hum.close()

    if not ai_records or not hum_records:
        print("❌ 数据库为空！")
        return

    ai_texts =[r["content"] for r in ai_records]
    hum_texts = [r["content"] for r in hum_records]

    num_ai = len(ai_records)
    num_hum = len(hum_records)
    print(f"📦 载入完毕！AI 词作: {num_ai} 首 | 历史词作: {num_hum} 首")
    print(f"🧮 预计将进行 {num_ai * num_hum:,} 次交叉比对！")

    # ---------------------------------------------------------
    # 第二步：高维语义比对 (GPU 密集型)
    # ---------------------------------------------------------
    print(f"\n🚀 阶段一：高维意境追踪 (计算设备: {device.upper()})")
    try:
        word_emb = models.Transformer(EMBEDDING_MODEL_NAME)
        pooling = models.Pooling(word_emb.get_word_embedding_dimension(), pooling_mode_mean_tokens=True)
        model = SentenceTransformer(modules=[word_emb, pooling], device=device)
    except Exception as e:
        print(f"❌ BERT-CCPoem 模型加载失败: {e}")
        return

    start_time = time.time()
    # 使用 batch_size 防止全宋词太多撑爆显存
    print("   1. 正在将 2万+ 历史词作编码为高维矩阵 (请稍候)...")
    hum_embeddings = model.encode(hum_texts, batch_size=256, convert_to_tensor=True, show_progress_bar=True)
    
    print("   2. 正在编码 AI 词作...")
    ai_embeddings = model.encode(ai_texts, batch_size=256, convert_to_tensor=True)

    print("   3. 矩阵相乘，计算全局余弦相似度...")
    # 计算 N x M 矩阵 (极为迅速)
    cos_sim_matrix = util.cos_sim(ai_embeddings, hum_embeddings)
    
    # 获取每个 AI 词在全宋词中“语义最接近”的一首
    max_sem_scores, max_sem_indices = torch.max(cos_sim_matrix, dim=1)
    
    print(f"✅ 阶段一完成！耗时: {time.time() - start_time:.2f} 秒")
    
    # 释放显存
    del model, hum_embeddings, ai_embeddings, cos_sim_matrix
    if device == "cuda": torch.cuda.empty_cache()

    # ---------------------------------------------------------
    # 第三步：传统语句比对 (多进程 CPU 密集型)
    # ---------------------------------------------------------
    print(f"\n🚀 阶段二：传统字面追踪 (启动多进程并发)")
    start_time = time.time()
    
    # 获取系统所有 CPU 核心数
    num_cores = mp.cpu_count()
    print(f"   ⚙️ 发现 {num_cores} 个 CPU 核心，火力全开中...")

    # 构造任务列表
    tasks =[(i, text) for i, text in enumerate(ai_texts)]
    lexical_results =[]

    # 启动进程池
    with mp.Pool(processes=num_cores, initializer=init_worker, initargs=(hum_texts,)) as pool:
        # 使用 imap_unordered 提升效率，并每完成 10% 打印一次进度
        completed = 0
        for result in pool.imap_unordered(compute_lexical_task, tasks, chunksize=10):
            lexical_results.append(result)
            completed += 1
            if completed % max(1, (num_ai // 10)) == 0:
                print(f"   进度: {completed}/{num_ai} 首 AI 词完成字面扫描...")

    # 按原始 AI 索引排序还原
    lexical_results.sort(key=lambda x: x[0])
    print(f"✅ 阶段二完成！耗时: {time.time() - start_time:.2f} 秒")

    # ---------------------------------------------------------
    # 第四步：数据整合与报告生成
    # ---------------------------------------------------------
    print("\n💾 阶段三：正在分析结果并生成报告...")
    
    final_reports =[]

    for i in range(num_ai):
        ai = ai_records[i]
        
        # 语义溯源结果
        sem_score = max_sem_scores[i].item()
        sem_hum_idx = max_sem_indices[i].item()
        sem_hum = hum_records[sem_hum_idx]
        
        # 字面溯源结果
        _, lex_hum_idx, lex_score = lexical_results[i]
        lex_hum = hum_records[lex_hum_idx]
        
        # 只保留达到“疑似抄袭”阈值的记录
        if sem_score >= MIN_SEMANTIC_SCORE or lex_score >= MIN_LEXICAL_SCORE:
            # 判断是否是“跨词牌抄袭”
            cross_cipai = "是" if ai["cipai"] != sem_hum["cipai"] and ai["cipai"] != lex_hum["cipai"] else "否"
            
            final_reports.append({
                "ai_id": ai["id"], "model": ai["model_name"], "ai_cipai": ai["cipai"], "ai_content": ai["content"],
                "sem_score": sem_score, "sem_author": sem_hum["author"], "sem_cipai": sem_hum["full_rhythmic"], "sem_content": sem_hum["content"],
                "lex_score": lex_score, "lex_author": lex_hum["author"], "lex_cipai": lex_hum["full_rhythmic"], "lex_content": lex_hum["content"],
                "cross_cipai": cross_cipai,
                # 按照最高威胁度排序
                "max_threat": max(sem_score, lex_score * 2) # 字面重合度权重大一些
            })

    # 按威胁程度排序
    final_reports.sort(key=lambda x: x["max_threat"], reverse=True)

    # 写入 CSV
    with open(CSV_RESULT_FILE, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "AI_ID", "生成模型", "AI词牌", "是否跨词牌化用", "AI正文",
            "最强语义参考(意境)", "意境相似度", "参考作者(意)", "参考词牌(意)", "参考原文(意)",
            "最强字面参考(原句)", "字面重合率", "参考作者(字)", "参考词牌(字)", "参考原文(字)"
        ])
        for r in final_reports:
            writer.writerow([
                r["ai_id"], r["model"], r["ai_cipai"], r["cross_cipai"], r["ai_content"],
                "👉", f"{r['sem_score']:.4f}", r["sem_author"], r["sem_cipai"], r["sem_content"],
                "👉", f"{r['lex_score']:.4f}", r["lex_author"], r["lex_cipai"], r["lex_content"]
            ])

    # 写入并打印 TXT (前 5 个最炸裂的案例)
    with open(TXT_REPORT_FILE, "w", encoding="utf-8") as f:
        f.write("=== AI 全量溯源深度分析报告 ===\n\n")
        
        for idx, r in enumerate(final_reports):
            is_cross = "🚨【跨词牌化用】" if r["cross_cipai"] == "是" else "🔄【同词牌模仿】"
            report_str = (
                f"[{idx+1}] {is_cross} | AI 模型: {r['model']} | 词牌:《{r['ai_cipai']}》\n"
                f"   📝 AI 创作原文: {r['ai_content']}\n\n"
                f"   🌟 【灵魂相似】最强意境参考 (相似度: {r['sem_score']:.4f}):\n"
                f"[{r['sem_author']}] 《{r['sem_cipai']}》: {r['sem_content']}\n\n"
                f"   🔤 【原句照抄】最强字面参考 (重合率: {r['lex_score']:.4f}):\n"
                f"[{r['lex_author']}] 《{r['lex_cipai']}》: {r['lex_content']}\n"
                f"{'-'*80}\n"
            )
            f.write(report_str)
            if idx < 5:
                print(report_str, end="")
                
    print(f"🎉 溯源大扫除完毕！揪出 {len(final_reports)} 份高度疑似化用的作品。")
    print(f"📄 详细溯源清单见: {CSV_RESULT_FILE}")

if __name__ == "__main__":
    main()