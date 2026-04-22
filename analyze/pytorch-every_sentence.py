import sqlite3
import torch
import csv
import re
import os
import time
import math
import heapq
import difflib
import gc
import multiprocessing as mp
from sentence_transformers import SentenceTransformer, util, models

# ==========================================
# 1. 基础配置区
# ==========================================
AI_DB_NAME = "database/song_ci_research_B_3.db"
HUMAN_DB_NAME = "database/real_poetry_dataset.db"
EMBEDDING_MODEL_NAME = "analyze/BERT-CCPoem-Model"

CACHE_DIR = "analyze/historical_cache_v2"

CSV_SENTENCE_DETAIL = "result/BERT-B-3-sentence_level_details.csv" 
CSV_POEM_SUMMARY = "result/BERT-B-3-poem_level_summary.csv"        
TXT_REPORT = "result/BERT-B-3-sentence_level_report.txt"           

# ==========================================
# 2. 文本处理与【真·多进程】辅助函数
# ==========================================
def split_into_sentences(text):
    parts = re.split(r'[，。！？；\n]', text)
    return[p.strip() for p in parts if p.strip()]

# 全局变量：供子进程共享几百万条历史句子，避免内存翻倍爆炸
global_hum_sentences =[]

def init_worker(hum_sents_arg):
    global global_hum_sentences
    global_hum_sentences = hum_sents_arg

def compute_lexical_top5_v2(item):
    """
    真·多核处理函数：只在传入的 Top 2000 候选名单中找字面最相似的 Top 5
    """
    ai_idx, ai_text, candidate_indices = item
    lex_heap =[]
    matcher = difflib.SequenceMatcher(None, ai_text, "")
    
    for h_idx in candidate_indices:
        matcher.set_seq2(global_hum_sentences[h_idx])
        l_score = matcher.ratio()
        
        if len(lex_heap) < 5:
            heapq.heappush(lex_heap, (l_score, h_idx))
        elif l_score > lex_heap[0][0]:
            heapq.heapreplace(lex_heap, (l_score, h_idx))
            
    sorted_top5 = sorted(lex_heap, key=lambda x: -x[0])
    return ai_idx, sorted_top5

# ==========================================
# 3. 主程序
# ==========================================
def main():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print("="*60)
    print(f"🔍 [AI 句级溯源引擎] (真·多核防爆满血版) 启动！")
    print(f"🖥️ 计算设备: {device.upper()} | CPU 核心数: {mp.cpu_count()}")
    print("="*60)

    # ---------------------------------------------------------
    # 第一步：轻量化读取 AI 数据
    # ---------------------------------------------------------
    conn_ai = sqlite3.connect(AI_DB_NAME)
    conn_ai.row_factory = sqlite3.Row
    ai_records =[dict(r) for r in conn_ai.execute("SELECT id, model_name, cipai, title, content FROM ci_data WHERE content != ''").fetchall()]
    conn_ai.close()

    ai_sentences =[]
    for poem in ai_records:
        for s in split_into_sentences(poem["content"]):
            ai_sentences.append({
                "poem_id": poem["id"], "model": poem["model_name"],
                "poem_cipai": poem["cipai"], "poem_title": poem["title"], "text": s
            })
    num_ai = len(ai_sentences)
    print(f"   🤖 提取出 AI 单句: {num_ai:,} 句")

    # ---------------------------------------------------------
    # 第二步：轻量化读取历史诗词
    # ---------------------------------------------------------
    conn_hum = sqlite3.connect(HUMAN_DB_NAME)
    conn_hum.row_factory = sqlite3.Row
    hum_records =[dict(r) for r in conn_hum.execute("SELECT id, author, full_rhythmic, cipai FROM real_ci_data WHERE content != ''").fetchall()]
    
    poem_info_dict = {r["id"]: {"author": r["author"], "title": r["full_rhythmic"], "cipai": r["cipai"]} for r in hum_records}
    
    hum_sentences = []
    hum_poem_ids =[]  
    
    cursor = conn_hum.execute("SELECT id, content FROM real_ci_data WHERE content != ''")
    for r in cursor.fetchall():
        for s in split_into_sentences(r["content"]):
            hum_sentences.append(s)
            hum_poem_ids.append(r["id"])
    conn_hum.close()
    
    num_hum = len(hum_sentences)
    print(f"   📜 提取出历史单句: {num_hum:,} 句")

    # ---------------------------------------------------------
    # 第三步：跳过全量缓存与编码
    # ---------------------------------------------------------
    META_FILE = os.path.join(CACHE_DIR, "metadata.pt")
    CHUNK_SIZE = 200000  

    if os.path.exists(META_FILE):
        print(f"\n📦 发现本地缓存 [{CACHE_DIR}]，完美跳过全量历史编码！")
        cache_meta = torch.load(META_FILE)
        num_chunks = cache_meta["num_chunks"]
    else:
        print(f"\n❌ 缓存不存在，请检查 {CACHE_DIR} 文件夹。")
        return

    # ---------------------------------------------------------
    # 第四步：向量矩阵分块对撞 (双向切块防爆算法)
    # ---------------------------------------------------------
    print(f"\n🚀 阶段一：高维语义矩阵对撞 (分块执行，确保显存 < 2GB)...")
    start_time = time.time()
    
    word_emb = models.Transformer(EMBEDDING_MODEL_NAME)
    pooling = models.Pooling(word_emb.get_word_embedding_dimension(), pooling_mode_mean_tokens=True)
    model = SentenceTransformer(modules=[word_emb, pooling], device=device)
    
    ai_texts = [s["text"] for s in ai_sentences]
    ai_embeddings = model.encode(ai_texts, batch_size=256, convert_to_tensor=True, show_progress_bar=False).to(device)

    TOP_K = min(2000, num_hum)
    global_topk_scores = torch.full((num_ai, TOP_K), -1.0, device='cpu')
    global_topk_indices = torch.full((num_ai, TOP_K), -1, dtype=torch.long, device='cpu')

    QUERY_CHUNK_SIZE = 2000

    for i in range(num_chunks):
        print(f"   ⚔️ 正在与硬盘区块 {i+1}/{num_chunks} 进行张量碰撞...")
        corpus_chunk = torch.load(os.path.join(CACHE_DIR, f"emb_chunk_{i}.pt")).to(device)
        
        for q_start in range(0, num_ai, QUERY_CHUNK_SIZE):
            q_end = min(q_start + QUERY_CHUNK_SIZE, num_ai)
            query_batch = ai_embeddings[q_start:q_end]
            
            sim = util.cos_sim(query_batch, corpus_chunk)
            
            curr_k = min(TOP_K, sim.shape[1])
            chunk_scores, chunk_idx = torch.topk(sim, k=curr_k, dim=1)
            chunk_idx += (i * CHUNK_SIZE)
            
            combined_scores = torch.cat([global_topk_scores[q_start:q_end], chunk_scores.cpu()], dim=1)
            combined_indices = torch.cat([global_topk_indices[q_start:q_end], chunk_idx.cpu()], dim=1)
            
            sorted_scores, sort_idx = torch.sort(combined_scores, descending=True, dim=1)
            
            global_topk_scores[q_start:q_end] = sorted_scores[:, :TOP_K]
            global_topk_indices[q_start:q_end] = torch.gather(combined_indices, 1, sort_idx[:, :TOP_K])
            
            del sim, chunk_scores, chunk_idx, combined_scores, combined_indices, sorted_scores, sort_idx
            
        del corpus_chunk
        if device == "cuda": torch.cuda.empty_cache()
        gc.collect()

    del ai_embeddings
    if device == "cuda": torch.cuda.empty_cache()

    global_topk_scores = global_topk_scores.numpy()
    global_topk_indices = global_topk_indices.numpy()
    print(f"✅ 阶段一完成！耗时: {time.time() - start_time:.2f} 秒")

    # ---------------------------------------------------------
    # 第五步：【已修复】真·多核降维字面比对
    # ---------------------------------------------------------
    print(f"\n🚀 阶段二：字面相似度降维追踪 (启动真·多核 CPU 引擎)...")
    start_time = time.time()
    num_cores = mp.cpu_count()
    print(f"   ⚙️ 发现 {num_cores} 个 CPU 核心，已使用4核调度！")

    # 准备多进程任务包：(AI句子索引, AI文本, 该句子的Top2000候选人名单)
    tasks =[]
    for i, ai_sent in enumerate(ai_sentences):
        tasks.append((i, ai_sent["text"], global_topk_indices[i].tolist()))

    lex_results =[]
    
    # 🌟 重新激活多进程池
    with mp.Pool(processes=4, initializer=init_worker, initargs=(hum_sentences,)) as pool:
        completed = 0
        # 将任务分发到所有核心，每个核心每次拿 50 个任务去跑
        for res in pool.imap_unordered(compute_lexical_top5_v2, tasks, chunksize=50):
            lex_results.append(res)
            completed += 1
            if completed % max(1, (len(tasks) // 10)) == 0:
                print(f"   进度: {completed}/{len(tasks)} 句字面扫描完成...")

    # 按原始 AI 句子顺序还原结果
    lex_results.sort(key=lambda x: x[0])
    lex_top5_data =[res[1] for res in lex_results]
    print(f"✅ 阶段二完成！耗时: {time.time() - start_time:.2f} 秒")

    # ---------------------------------------------------------
    # 第六步：生成多维报表
    # ---------------------------------------------------------
    print("\n💾 阶段三：正在整合数据并生成多维报表...")
    sentence_details =[]
    poem_agg = {}

    for i, ai_sent in enumerate(ai_sentences):
        poem_id = ai_sent["poem_id"]
        if poem_id not in poem_agg:
            poem_agg[poem_id] = {
                "model": ai_sent["model"], "cipai": ai_sent["poem_cipai"], 
                "title": ai_sent["poem_title"], "sem_scores": [], "lex_scores": []
            }

        candidate_indices = global_topk_indices[i].tolist()
        candidate_scores = global_topk_scores[i].tolist()
        
        sem_top5_info =[]
        for rank in range(5):
            idx = candidate_indices[rank]
            score = candidate_scores[rank]
            src_poem = poem_info_dict[hum_poem_ids[idx]]
            sem_top5_info.append({
                "score": score, "text": hum_sentences[idx],
                "source": f"[{src_poem['author']}]《{src_poem['title']}》"
            })
            
        l_data = lex_top5_data[i]
        lex_top5_info =[]
        for rank in range(5):
            score, idx = l_data[rank]
            src_poem = poem_info_dict[hum_poem_ids[idx]]
            lex_top5_info.append({
                "score": score, "text": hum_sentences[idx],
                "source": f"[{src_poem['author']}]《{src_poem['title']}》"
            })

        poem_agg[poem_id]["sem_scores"].append(sem_top5_info[0]["score"])
        poem_agg[poem_id]["lex_scores"].append(lex_top5_info[0]["score"])

        sentence_details.append({
            "poem_id": poem_id, "ai_text": ai_sent["text"],
            "sem_top5": sem_top5_info, "lex_top5": lex_top5_info
        })

    poem_summaries =[]
    for pid, data in poem_agg.items():
        avg_sem = sum(data["sem_scores"]) / len(data["sem_scores"])
        avg_lex = sum(data["lex_scores"]) / len(data["lex_scores"])
        poem_summaries.append({
            "poem_id": pid, "model": data["model"], "cipai": data["cipai"], "title": data["title"],
            "avg_sem_score": avg_sem, "avg_lex_score": avg_lex
        })
        
    poem_summaries.sort(key=lambda x: (x["avg_sem_score"] + x["avg_lex_score"]), reverse=True)

    with open(CSV_POEM_SUMMARY, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["AI词ID", "模型", "词牌", "题目", "单句平均语义相似度", "单句平均字面重合度"])
        for p in poem_summaries:
            writer.writerow([p["poem_id"], p["model"], p["cipai"], p["title"], f"{p['avg_sem_score']:.4f}", f"{p['avg_lex_score']:.4f}"])

    with open(TXT_REPORT, "w", encoding="utf-8") as f:
        f.write("=== AI 宋词单句溯源 (Top 5) 深度报告 ===\n\n")
        for pid, data in poem_agg.items():
            f.write(f"【词作 ID: {pid}】 | 模型: {data['model']} | 词牌:《{data['cipai']}》- {data['title']}\n")
            sents = [s for s in sentence_details if s["poem_id"] == pid]
            for s_idx, s in enumerate(sents, 1):
                f.write(f"\n   🔴 第 {s_idx} 句： {s['ai_text']}\n")
                f.write("      💭[意境追踪 Top 5]:\n")
                for rank, info in enumerate(s['sem_top5'], 1):
                    f.write(f"         {rank}. ({info['score']:.4f}) {info['text']}  --- {info['source']}\n")
                f.write("      🔤 [字面追踪 Top 5]:\n")
                for rank, info in enumerate(s['lex_top5'], 1):
                    f.write(f"         {rank}. ({info['score']:.4f}) {info['text']}  --- {info['source']}\n")
            f.write("\n" + "="*80 + "\n\n")

    print(f"🎉 全部计算与报表生成完毕！多核引擎已完美调度！")

if __name__ == "__main__":
    main()