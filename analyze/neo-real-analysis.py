import argparse
import csv
import difflib
import json
import math
import multiprocessing as mp
import os
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path


AI_DATABASES = {
    "a1": "database/a1.db",
    "b1": "database/b1.db",
    "b2": "database/b2.db",
    "b3": "database/b3.db",
    "c1": "database/c1.db",
    "c2": "database/c2.db",
}

DEFAULT_HUMAN_DB = "database/real_song_ci_dataset.db"
DEFAULT_MODEL_PATH = "analyze/BERT-CCPoem-Model"
DEFAULT_RESULT_DIR = Path("result/neo-real-analysis")
DEFAULT_CACHE_DIR = Path("analyze/neo_real_cache")

ST_MODULES = None
GLOBAL_LEXICAL_CORPUS = []


def load_st_modules():
    global ST_MODULES
    if ST_MODULES is None:
        try:
            import torch  # pylint: disable=import-outside-toplevel
            from sentence_transformers import (  # pylint: disable=import-outside-toplevel
                SentenceTransformer,
                models,
                util,
            )
        except ImportError as exc:
            raise RuntimeError(
                "neo-real-analysis 需要 torch 和 sentence-transformers。"
                " 请在具备这些依赖的 Python 环境中运行。"
            ) from exc

        ST_MODULES = {
            "torch": torch,
            "SentenceTransformer": SentenceTransformer,
            "models": models,
            "util": util,
        }
    return ST_MODULES


def parse_args():
    parser = argparse.ArgumentParser(
        description="AI 宋词真实来源三层分析：历史基线、整首溯源、句级溯源。"
    )
    parser.add_argument(
        "--ai-dbs",
        nargs="+",
        default=list(AI_DATABASES.keys()),
        choices=list(AI_DATABASES.keys()),
        help="要纳入分析的 AI 数据库代号。",
    )
    parser.add_argument(
        "--human-db",
        default=DEFAULT_HUMAN_DB,
        help="真实宋词数据库路径。",
    )
    parser.add_argument(
        "--model-path",
        default=DEFAULT_MODEL_PATH,
        help="BERT-CCPoem 模型目录。",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_RESULT_DIR),
        help="输出目录。",
    )
    parser.add_argument(
        "--cache-dir",
        default=str(DEFAULT_CACHE_DIR),
        help="嵌入缓存目录。",
    )
    parser.add_argument(
        "--min-rhythm",
        type=float,
        default=0.0,
        help="AI 样本最低格律分阈值；0 表示不过滤。",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=256,
        help="文本编码 batch size。",
    )
    parser.add_argument(
        "--query-batch-size",
        type=int,
        default=512,
        help="向量检索时的 query batch size。",
    )
    parser.add_argument(
        "--sentence-cache-chunk-size",
        type=int,
        default=50000,
        help="句级嵌入缓存切块大小。",
    )
    parser.add_argument(
        "--whole-topk",
        type=int,
        default=10,
        help="整首级语义与字面保留的 TopK。",
    )
    parser.add_argument(
        "--whole-semantic-candidates",
        type=int,
        default=64,
        help="整首级字面精排前保留的语义候选数。",
    )
    parser.add_argument(
        "--whole-lexical-candidates",
        type=int,
        default=160,
        help="整首级字面检索的候选数量上限。",
    )
    parser.add_argument(
        "--sentence-semantic-candidates",
        type=int,
        default=64,
        help="句级字面精排前保留的语义候选数。",
    )
    parser.add_argument(
        "--sentence-topk",
        type=int,
        default=5,
        help="句级语义与字面保留的 TopK。",
    )
    parser.add_argument(
        "--baseline-min-poems-per-cipai",
        type=int,
        default=8,
        help="纳入整首基线的词牌最少真实作品数。",
    )
    parser.add_argument(
        "--baseline-min-sentences-per-cipai",
        type=int,
        default=24,
        help="纳入句级基线的词牌最少真实句子数。",
    )
    parser.add_argument(
        "--lexical-workers",
        type=int,
        default=max(1, min(8, (os.cpu_count() or 2) - 1)),
        help="字面比对的并行进程数。",
    )
    return parser.parse_args()


def map_model_name(raw_name):
    if not raw_name:
        return "Unknown"
    mapping = {
        "doubao-seed-2-0-pro-260215": "doubao-seed-2.0-pro",
        "deepseek-reasoner": "deepseek-3.2-thinking",
        "deepseek-v3.2": "deepseek-3.2-thinking",
        "qwen3.6-plus": "qwen3.6-plus",
        "qwen3.5-plus-2026-02-15": "qwen3.5-plus",
        "gemini-3.1-pro-preview": "gemini-3.1-pro",
        "gemini-3-flash-preview": "gemini-3-flash",
    }
    return mapping.get(raw_name, raw_name)


def split_into_sentences(text):
    parts = re.split(r"[，。！？；\n]", text or "")
    return [part.strip() for part in parts if part and part.strip()]


def sentence_length_bucket(text):
    length = len(text or "")
    if length <= 5:
        return "<=5"
    if length <= 8:
        return "6-8"
    if length <= 11:
        return "9-11"
    if length <= 14:
        return "12-14"
    return "15+"


def compact_json(data):
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def percentile_rank(sorted_values, value):
    if not sorted_values:
        return None
    lo = 0
    hi = len(sorted_values)
    while lo < hi:
        mid = (lo + hi) // 2
        if sorted_values[mid] <= value:
            lo = mid + 1
        else:
            hi = mid
    return lo / len(sorted_values)


def summarize_values(values):
    if not values:
        return None
    ordered = sorted(float(v) for v in values)

    def pct(p):
        if len(ordered) == 1:
            return ordered[0]
        pos = (len(ordered) - 1) * p
        lower = math.floor(pos)
        upper = math.ceil(pos)
        if lower == upper:
            return ordered[lower]
        weight = pos - lower
        return ordered[lower] * (1 - weight) + ordered[upper] * weight

    return {
        "count": len(ordered),
        "mean": sum(ordered) / len(ordered),
        "p50": pct(0.50),
        "p90": pct(0.90),
        "p95": pct(0.95),
        "p99": pct(0.99),
        "max": ordered[-1],
    }


def init_lexical_worker(corpus_texts):
    global GLOBAL_LEXICAL_CORPUS
    GLOBAL_LEXICAL_CORPUS = corpus_texts


def lexical_topk_worker(task):
    query_idx, query_text, candidate_indices, topk = task
    heap = []
    matcher = difflib.SequenceMatcher(None, query_text or "", "")

    for corpus_idx in candidate_indices:
        if corpus_idx < 0:
            continue
        matcher.set_seq2(GLOBAL_LEXICAL_CORPUS[corpus_idx] or "")
        score = matcher.ratio()
        if len(heap) < topk:
            heap.append((score, corpus_idx))
            if len(heap) == topk:
                heap.sort(key=lambda item: item[0])
        elif score > heap[0][0]:
            heap[0] = (score, corpus_idx)
            heap.sort(key=lambda item: item[0])

    heap.sort(key=lambda item: item[0], reverse=True)
    return query_idx, heap


def run_lexical_topk(query_texts, corpus_texts, candidate_lists, topk, num_workers):
    tasks = [
        (idx, query_texts[idx], candidate_lists[idx], topk)
        for idx in range(len(query_texts))
    ]
    results = [None] * len(tasks)
    if not tasks:
        return results

    if num_workers <= 1:
        init_lexical_worker(corpus_texts)
        for task in tasks:
            idx, payload = lexical_topk_worker(task)
            results[idx] = payload
        return results

    with mp.Pool(
        processes=num_workers,
        initializer=init_lexical_worker,
        initargs=(corpus_texts,),
    ) as pool:
        for idx, payload in pool.imap_unordered(lexical_topk_worker, tasks, chunksize=32):
            results[idx] = payload

    return results


def build_char_ngram_index(texts, ngram_size=2):
    index = defaultdict(list)
    for idx, text in enumerate(texts):
        grams = extract_char_ngrams(text, ngram_size)
        for gram in grams:
            index[gram].append(idx)
    return index


def extract_char_ngrams(text, ngram_size=2):
    normalized = "".join((text or "").split())
    if not normalized:
        return set()
    if len(normalized) < ngram_size:
        return {normalized}
    return {
        normalized[pos : pos + ngram_size]
        for pos in range(len(normalized) - ngram_size + 1)
    }


def ngram_candidates_for_text(text, ngram_index, exclude=None, limit=128):
    counts = Counter()
    for gram in extract_char_ngrams(text):
        for idx in ngram_index.get(gram, []):
            if exclude is not None and idx == exclude:
                continue
            counts[idx] += 1
    if not counts:
        return []
    return [idx for idx, _ in counts.most_common(limit)]


def build_model(model_path, device):
    modules = load_st_modules()
    word_embedding_model = modules["models"].Transformer(model_path)
    pooling_model = modules["models"].Pooling(
        word_embedding_model.get_word_embedding_dimension(),
        pooling_mode_mean_tokens=True,
        pooling_mode_cls_token=False,
        pooling_mode_max_tokens=False,
    )
    return modules["SentenceTransformer"](
        modules=[word_embedding_model, pooling_model],
        device=device,
    )


def load_rows(path, query):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    rows = [dict(row) for row in conn.execute(query).fetchall()]
    conn.close()
    return rows


def load_ai_poems(ai_db_keys, min_rhythm):
    poems = []
    for db_key in ai_db_keys:
        db_path = AI_DATABASES[db_key]
        rows = load_rows(
            db_path,
            """
            SELECT id, cipai, title, content, category, imagery, model_name, rhythm_score
            FROM ci_data
            WHERE content != ''
            """,
        )
        for row in rows:
            rhythm_score = row.get("rhythm_score")
            if (
                min_rhythm > 0
                and rhythm_score is not None
                and float(rhythm_score) < min_rhythm
            ):
                continue
            poems.append(
                {
                    "ai_uid": f"{db_key}:{row['id']}",
                    "db_key": db_key,
                    "db_path": db_path,
                    "id": row["id"],
                    "cipai": row.get("cipai") or "",
                    "title": row.get("title") or "",
                    "content": row.get("content") or "",
                    "category": row.get("category") or "",
                    "imagery": row.get("imagery") or "",
                    "model_name": map_model_name(row.get("model_name")),
                    "rhythm_score": row.get("rhythm_score"),
                }
            )
    return poems


def load_human_poems(human_db_path):
    rows = load_rows(
        human_db_path,
        """
        SELECT id, author, full_rhythmic, cipai, content
        FROM real_ci_data
        WHERE content != ''
        """,
    )
    poems = []
    for row in rows:
        poems.append(
            {
                "id": row["id"],
                "author": row.get("author") or "",
                "full_rhythmic": row.get("full_rhythmic") or "",
                "cipai": row.get("cipai") or "",
                "content": row.get("content") or "",
            }
        )
    return poems


def build_human_sentences(human_poems):
    sentences = []
    for poem in human_poems:
        for sent_idx, sentence in enumerate(split_into_sentences(poem["content"])):
            sentences.append(
                {
                    "sentence_uid": f"{poem['id']}:{sent_idx}",
                    "poem_id": poem["id"],
                    "cipai": poem["cipai"],
                    "author": poem["author"],
                    "full_rhythmic": poem["full_rhythmic"],
                    "text": sentence,
                    "sentence_index": sent_idx,
                    "length_bucket": sentence_length_bucket(sentence),
                }
            )
    return sentences


def ensure_dir(path):
    Path(path).mkdir(parents=True, exist_ok=True)


def cache_namespace(cache_dir, db_path):
    db_file = Path(db_path)
    namespace = db_file.stem
    db_mtime = db_file.stat().st_mtime_ns
    target_dir = Path(cache_dir) / namespace
    ensure_dir(target_dir)
    return target_dir, db_mtime


def encode_texts(model, texts, batch_size):
    modules = load_st_modules()
    torch = modules["torch"]
    with torch.no_grad():
        embeddings = model.encode(
            texts,
            batch_size=batch_size,
            convert_to_tensor=True,
            show_progress_bar=True,
        )
    return embeddings.cpu().float()


def load_or_build_whole_cache(model, human_poems, args, device):
    modules = load_st_modules()
    torch = modules["torch"]
    cache_dir, db_mtime = cache_namespace(args.cache_dir, args.human_db)
    metadata_path = cache_dir / "whole_metadata.json"
    tensor_path = cache_dir / "whole_embeddings.pt"

    metadata = None
    if metadata_path.exists() and tensor_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if (
            metadata.get("db_path") == str(Path(args.human_db).resolve())
            and metadata.get("db_mtime_ns") == db_mtime
            and metadata.get("model_path") == str(Path(args.model_path).resolve())
            and metadata.get("count") == len(human_poems)
        ):
            embeddings = torch.load(tensor_path, map_location="cpu")
            return embeddings

    texts = [poem["content"] for poem in human_poems]
    embeddings = encode_texts(model, texts, args.batch_size)
    torch.save(embeddings, tensor_path)
    metadata = {
        "db_path": str(Path(args.human_db).resolve()),
        "db_mtime_ns": db_mtime,
        "model_path": str(Path(args.model_path).resolve()),
        "count": len(human_poems),
        "dimension": int(embeddings.shape[1]) if len(embeddings.shape) == 2 else 0,
    }
    metadata_path.write_text(compact_json(metadata), encoding="utf-8")
    return embeddings


def load_or_build_sentence_cache(model, human_sentences, args, device):
    modules = load_st_modules()
    torch = modules["torch"]
    cache_dir, db_mtime = cache_namespace(args.cache_dir, args.human_db)
    metadata_path = cache_dir / "sentence_metadata.json"

    metadata = None
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if (
            metadata.get("db_path") == str(Path(args.human_db).resolve())
            and metadata.get("db_mtime_ns") == db_mtime
            and metadata.get("model_path") == str(Path(args.model_path).resolve())
            and metadata.get("count") == len(human_sentences)
            and metadata.get("chunk_size") == args.sentence_cache_chunk_size
        ):
            chunk_paths = [
                cache_dir / chunk_name for chunk_name in metadata.get("chunks", [])
            ]
            if all(path.exists() for path in chunk_paths):
                return chunk_paths, metadata

    texts = [sentence["text"] for sentence in human_sentences]
    embeddings = encode_texts(model, texts, args.batch_size)
    chunk_paths = []
    chunk_names = []
    for chunk_idx, start in enumerate(
        range(0, embeddings.shape[0], args.sentence_cache_chunk_size)
    ):
        stop = min(start + args.sentence_cache_chunk_size, embeddings.shape[0])
        chunk_name = f"sentence_embeddings_{chunk_idx}.pt"
        chunk_path = cache_dir / chunk_name
        torch.save(embeddings[start:stop].contiguous(), chunk_path)
        chunk_paths.append(chunk_path)
        chunk_names.append(chunk_name)

    metadata = {
        "db_path": str(Path(args.human_db).resolve()),
        "db_mtime_ns": db_mtime,
        "model_path": str(Path(args.model_path).resolve()),
        "count": len(human_sentences),
        "chunk_size": args.sentence_cache_chunk_size,
        "chunks": chunk_names,
        "dimension": int(embeddings.shape[1]) if len(embeddings.shape) == 2 else 0,
    }
    metadata_path.write_text(compact_json(metadata), encoding="utf-8")
    return chunk_paths, metadata


def combine_topk(existing_scores, existing_indices, new_scores, new_indices, topk, torch):
    if existing_scores is None:
        return new_scores, new_indices
    merged_scores = torch.cat([existing_scores, new_scores], dim=1)
    merged_indices = torch.cat([existing_indices, new_indices], dim=1)
    sorted_scores, sort_idx = torch.sort(merged_scores, descending=True, dim=1)
    sorted_indices = torch.gather(merged_indices, 1, sort_idx[:, :topk])
    return sorted_scores[:, :topk], sorted_indices


def search_topk_against_tensor(
    query_embeddings,
    corpus_embeddings,
    topk,
    query_batch_size,
    device,
    util,
    exclude_self=False,
):
    modules = load_st_modules()
    torch = modules["torch"]
    query_embeddings = query_embeddings.cpu().float()
    corpus_embeddings = corpus_embeddings.cpu().float()
    results_scores = []
    results_indices = []

    corpus_gpu = corpus_embeddings.to(device)
    for start in range(0, query_embeddings.shape[0], query_batch_size):
        stop = min(start + query_batch_size, query_embeddings.shape[0])
        batch = query_embeddings[start:stop].to(device)
        sim = util.cos_sim(batch, corpus_gpu)
        if exclude_self:
            offset = start
            for local_row in range(stop - start):
                global_row = offset + local_row
                if global_row < corpus_embeddings.shape[0]:
                    sim[local_row, global_row] = -1.0
        curr_topk = min(topk, sim.shape[1])
        scores, indices = torch.topk(sim, k=curr_topk, dim=1)
        results_scores.append(scores.cpu())
        results_indices.append(indices.cpu())
    del corpus_gpu
    if device == "cuda":
        torch.cuda.empty_cache()
    return torch.cat(results_scores, dim=0), torch.cat(results_indices, dim=0)


def search_topk_against_chunks(
    query_embeddings,
    chunk_paths,
    topk,
    query_batch_size,
    device,
    util,
):
    modules = load_st_modules()
    torch = modules["torch"]
    query_embeddings = query_embeddings.cpu().float()
    global_scores = None
    global_indices = None
    offset = 0

    for chunk_path in chunk_paths:
        chunk = torch.load(chunk_path, map_location="cpu").float()
        chunk_gpu = chunk.to(device)

        chunk_result_scores = []
        chunk_result_indices = []
        for start in range(0, query_embeddings.shape[0], query_batch_size):
            stop = min(start + query_batch_size, query_embeddings.shape[0])
            batch = query_embeddings[start:stop].to(device)
            sim = util.cos_sim(batch, chunk_gpu)
            curr_topk = min(topk, sim.shape[1])
            scores, indices = torch.topk(sim, k=curr_topk, dim=1)
            chunk_result_scores.append(scores.cpu())
            chunk_result_indices.append((indices.cpu() + offset))

        chunk_scores = torch.cat(chunk_result_scores, dim=0)
        chunk_indices = torch.cat(chunk_result_indices, dim=0)
        global_scores, global_indices = combine_topk(
            global_scores,
            global_indices,
            chunk_scores,
            chunk_indices,
            topk,
            torch,
        )
        offset += chunk.shape[0]
        del chunk
        del chunk_gpu
        if device == "cuda":
            torch.cuda.empty_cache()

    return global_scores, global_indices


def compute_whole_baseline(
    human_poems,
    whole_embeddings,
    target_cipais,
    args,
    device,
    util,
):
    by_cipai = defaultdict(list)
    for idx, poem in enumerate(human_poems):
        by_cipai[poem["cipai"]].append(idx)

    lexical_scores_by_cipai = {}
    semantic_scores_by_cipai = {}

    for cipai in sorted(target_cipais):
        indices = by_cipai.get(cipai, [])
        if len(indices) < args.baseline_min_poems_per_cipai:
            continue

        group_embeddings = whole_embeddings[indices]
        sem_scores, _ = search_topk_against_tensor(
            group_embeddings,
            group_embeddings,
            topk=1,
            query_batch_size=args.query_batch_size,
            device=device,
            util=util,
            exclude_self=True,
        )
        semantic_scores_by_cipai[cipai] = [float(value) for value in sem_scores[:, 0]]

        group_texts = [human_poems[idx]["content"] for idx in indices]
        candidate_lists = []
        for local_idx in range(len(indices)):
            candidate_lists.append([idx for idx in range(len(indices)) if idx != local_idx])
        lex_results = run_lexical_topk(
            group_texts,
            group_texts,
            candidate_lists,
            topk=1,
            num_workers=args.lexical_workers,
        )
        lexical_scores_by_cipai[cipai] = [
            float(result[0][0]) if result else 0.0 for result in lex_results
        ]

    whole_rows = []
    for cipai in sorted(semantic_scores_by_cipai):
        sem_summary = summarize_values(semantic_scores_by_cipai[cipai])
        lex_summary = summarize_values(lexical_scores_by_cipai.get(cipai, []))
        if sem_summary:
            whole_rows.append(
                {
                    "scope": "whole_poem",
                    "cipai": cipai,
                    "length_bucket": "",
                    "metric_type": "semantic",
                    **sem_summary,
                }
            )
        if lex_summary:
            whole_rows.append(
                {
                    "scope": "whole_poem",
                    "cipai": cipai,
                    "length_bucket": "",
                    "metric_type": "lexical",
                    **lex_summary,
                }
            )

    overall_semantic = [
        score
        for cipai_scores in semantic_scores_by_cipai.values()
        for score in cipai_scores
    ]
    overall_lexical = [
        score
        for cipai_scores in lexical_scores_by_cipai.values()
        for score in cipai_scores
    ]
    if overall_semantic:
        whole_rows.append(
            {
                "scope": "whole_poem",
                "cipai": "__overall__",
                "length_bucket": "",
                "metric_type": "semantic",
                **summarize_values(overall_semantic),
            }
        )
    if overall_lexical:
        whole_rows.append(
            {
                "scope": "whole_poem",
                "cipai": "__overall__",
                "length_bucket": "",
                "metric_type": "lexical",
                **summarize_values(overall_lexical),
            }
        )

    baseline_lookup = {
        "semantic": {
            cipai: sorted(scores) for cipai, scores in semantic_scores_by_cipai.items()
        },
        "lexical": {
            cipai: sorted(scores) for cipai, scores in lexical_scores_by_cipai.items()
        },
    }
    baseline_lookup["semantic"]["__overall__"] = sorted(overall_semantic)
    baseline_lookup["lexical"]["__overall__"] = sorted(overall_lexical)

    return whole_rows, baseline_lookup


def compute_sentence_baseline(
    human_sentences,
    sentence_chunk_paths,
    target_cipais,
    args,
    device,
    util,
):
    modules = load_st_modules()
    torch = modules["torch"]
    by_cipai = defaultdict(list)
    for idx, sentence in enumerate(human_sentences):
        by_cipai[sentence["cipai"]].append(idx)

    semantic_by_bucket = defaultdict(list)
    lexical_by_bucket = defaultdict(list)
    sentence_texts = [item["text"] for item in human_sentences]

    for cipai in sorted(target_cipais):
        indices = by_cipai.get(cipai, [])
        if len(indices) < args.baseline_min_sentences_per_cipai:
            continue

        sentence_vectors = []
        chunk_offset = 0
        remaining = set(indices)
        for chunk_path in sentence_chunk_paths:
            chunk = torch.load(chunk_path, map_location="cpu").float()
            local_indices = [
                idx - chunk_offset
                for idx in indices
                if chunk_offset <= idx < chunk_offset + chunk.shape[0]
            ]
            if local_indices:
                sentence_vectors.append(chunk[local_indices])
            chunk_offset += chunk.shape[0]
            if chunk_offset > indices[-1]:
                break
        group_embeddings = torch.cat(sentence_vectors, dim=0)
        sem_scores, sem_indices = search_topk_against_tensor(
            group_embeddings,
            group_embeddings,
            topk=min(args.sentence_semantic_candidates, max(1, len(indices) - 1)),
            query_batch_size=args.query_batch_size,
            device=device,
            util=util,
            exclude_self=True,
        )

        candidate_lists = []
        for local_idx in range(len(indices)):
            candidates = []
            for candidate_local in sem_indices[local_idx].tolist():
                if candidate_local < 0 or candidate_local == local_idx:
                    continue
                candidates.append(candidate_local)
            if not candidates:
                candidates = [idx for idx in range(len(indices)) if idx != local_idx][:1]
            candidate_lists.append(candidates)

        group_texts = [sentence_texts[idx] for idx in indices]
        lex_results = run_lexical_topk(
            group_texts,
            group_texts,
            candidate_lists,
            topk=1,
            num_workers=args.lexical_workers,
        )

        for local_idx, global_idx in enumerate(indices):
            bucket = human_sentences[global_idx]["length_bucket"]
            semantic_by_bucket[(cipai, bucket)].append(float(sem_scores[local_idx, 0]))
            lexical_score = float(lex_results[local_idx][0][0]) if lex_results[local_idx] else 0.0
            lexical_by_bucket[(cipai, bucket)].append(lexical_score)

    rows = []
    for key in sorted(set(semantic_by_bucket) | set(lexical_by_bucket)):
        cipai, bucket = key
        sem_summary = summarize_values(semantic_by_bucket.get(key, []))
        lex_summary = summarize_values(lexical_by_bucket.get(key, []))
        if sem_summary:
            rows.append(
                {
                    "scope": "sentence",
                    "cipai": cipai,
                    "length_bucket": bucket,
                    "metric_type": "semantic",
                    **sem_summary,
                }
            )
        if lex_summary:
            rows.append(
                {
                    "scope": "sentence",
                    "cipai": cipai,
                    "length_bucket": bucket,
                    "metric_type": "lexical",
                    **lex_summary,
                }
            )

    overall_semantic = defaultdict(list)
    overall_lexical = defaultdict(list)
    for (_, bucket), values in semantic_by_bucket.items():
        overall_semantic[bucket].extend(values)
    for (_, bucket), values in lexical_by_bucket.items():
        overall_lexical[bucket].extend(values)

    for bucket, values in sorted(overall_semantic.items()):
        rows.append(
            {
                "scope": "sentence",
                "cipai": "__overall__",
                "length_bucket": bucket,
                "metric_type": "semantic",
                **summarize_values(values),
            }
        )
    for bucket, values in sorted(overall_lexical.items()):
        rows.append(
            {
                "scope": "sentence",
                "cipai": "__overall__",
                "length_bucket": bucket,
                "metric_type": "lexical",
                **summarize_values(values),
            }
        )

    all_semantic_values = [score for values in overall_semantic.values() for score in values]
    all_lexical_values = [score for values in overall_lexical.values() for score in values]
    if all_semantic_values:
        rows.append(
            {
                "scope": "sentence",
                "cipai": "__overall__",
                "length_bucket": "__overall__",
                "metric_type": "semantic",
                **summarize_values(all_semantic_values),
            }
        )
    if all_lexical_values:
        rows.append(
            {
                "scope": "sentence",
                "cipai": "__overall__",
                "length_bucket": "__overall__",
                "metric_type": "lexical",
                **summarize_values(all_lexical_values),
            }
        )

    lookup = {
        "semantic": {key: sorted(values) for key, values in semantic_by_bucket.items()},
        "lexical": {key: sorted(values) for key, values in lexical_by_bucket.items()},
    }
    lookup["semantic"].update(
        {
            ("__overall__", bucket): sorted(values)
            for bucket, values in overall_semantic.items()
        }
    )
    lookup["lexical"].update(
        {
            ("__overall__", bucket): sorted(values)
            for bucket, values in overall_lexical.items()
        }
    )
    lookup["semantic"][("__overall__", "__overall__")] = sorted(all_semantic_values)
    lookup["lexical"][("__overall__", "__overall__")] = sorted(all_lexical_values)
    return rows, lookup


def build_whole_candidate_lists(
    ai_poems,
    human_poems,
    whole_semantic_indices,
    ngram_index,
    candidate_limit,
):
    candidate_lists = []
    for row_idx, poem in enumerate(ai_poems):
        seen = set()
        merged = []

        for idx in whole_semantic_indices[row_idx].tolist():
            if idx < 0:
                continue
            if idx not in seen:
                seen.add(idx)
                merged.append(idx)

        for idx in ngram_candidates_for_text(
            poem["content"],
            ngram_index,
            exclude=None,
            limit=candidate_limit,
        ):
            if idx not in seen:
                seen.add(idx)
                merged.append(idx)

        if not merged:
            merged = list(range(min(candidate_limit, len(human_poems))))

        candidate_lists.append(merged[:candidate_limit])
    return candidate_lists


def encode_ai_poems(model, ai_poems, args):
    texts = [poem["content"] for poem in ai_poems]
    return encode_texts(model, texts, args.batch_size)


def build_ai_sentences(ai_poems):
    sentences = []
    for poem in ai_poems:
        for sent_idx, sentence in enumerate(split_into_sentences(poem["content"])):
            sentences.append(
                {
                    "ai_uid": poem["ai_uid"],
                    "db_key": poem["db_key"],
                    "poem_id": poem["id"],
                    "cipai": poem["cipai"],
                    "title": poem["title"],
                    "model_name": poem["model_name"],
                    "sentence_index": sent_idx,
                    "text": sentence,
                    "length_bucket": sentence_length_bucket(sentence),
                }
            )
    return sentences


def aggregate_sentence_profiles(ai_sentences, sentence_rows, whole_top1_by_ai, human_poems_by_id):
    grouped = defaultdict(list)
    for row in sentence_rows:
        grouped[row["ai_uid"]].append(row)

    profiles = []
    for ai_uid, rows in grouped.items():
        rows.sort(key=lambda item: item["sentence_index"])
        total_sentences = len(rows)
        sem_counter = Counter()
        lex_counter = Counter()
        sem_sequence = []
        lex_sequence = []
        same_source_sentence_count = 0
        max_sentence_sem = 0.0
        max_sentence_lex = 0.0

        for row in rows:
            sem_source = row["sem_top1_source_poem_id"]
            lex_source = row["lex_top1_source_poem_id"]
            if sem_source:
                sem_counter[sem_source] += 1
            if lex_source:
                lex_counter[lex_source] += 1
            sem_sequence.append(sem_source)
            lex_sequence.append(lex_source)
            if sem_source and lex_source and sem_source == lex_source:
                same_source_sentence_count += 1
            max_sentence_sem = max(max_sentence_sem, row["sem_top1_score"])
            max_sentence_lex = max(max_sentence_lex, row["lex_top1_score"])

        sem_dominant_id, sem_dominant_count = sem_counter.most_common(1)[0] if sem_counter else ("", 0)
        lex_dominant_id, lex_dominant_count = lex_counter.most_common(1)[0] if lex_counter else ("", 0)
        sem_dominant_poem = human_poems_by_id.get(sem_dominant_id, {})
        lex_dominant_poem = human_poems_by_id.get(lex_dominant_id, {})
        whole_top1 = whole_top1_by_ai.get(ai_uid, {})

        profiles.append(
            {
                "ai_uid": ai_uid,
                "db_key": rows[0]["db_key"],
                "ai_poem_id": rows[0]["ai_poem_id"],
                "model_name": rows[0]["model_name"],
                "cipai": rows[0]["cipai"],
                "title": rows[0]["title"],
                "sentence_count": total_sentences,
                "whole_sem_top1_score": whole_top1.get("whole_sem_top1_score"),
                "whole_sem_top1_source_poem_id": whole_top1.get("whole_sem_top1_source_poem_id"),
                "whole_sem_top1_source_title": whole_top1.get("whole_sem_top1_source_title"),
                "whole_sem_top1_source_author": whole_top1.get("whole_sem_top1_source_author"),
                "whole_sem_percentile": whole_top1.get("whole_sem_percentile"),
                "whole_lex_top1_score": whole_top1.get("whole_lex_top1_score"),
                "whole_lex_top1_source_poem_id": whole_top1.get("whole_lex_top1_source_poem_id"),
                "whole_lex_top1_source_title": whole_top1.get("whole_lex_top1_source_title"),
                "whole_lex_top1_source_author": whole_top1.get("whole_lex_top1_source_author"),
                "whole_lex_percentile": whole_top1.get("whole_lex_percentile"),
                "sem_dominant_source_poem_id": sem_dominant_id,
                "sem_dominant_source_title": sem_dominant_poem.get("full_rhythmic", ""),
                "sem_dominant_source_author": sem_dominant_poem.get("author", ""),
                "sem_dominant_source_coverage": (
                    sem_dominant_count / total_sentences if total_sentences else 0.0
                ),
                "lex_dominant_source_poem_id": lex_dominant_id,
                "lex_dominant_source_title": lex_dominant_poem.get("full_rhythmic", ""),
                "lex_dominant_source_author": lex_dominant_poem.get("author", ""),
                "lex_dominant_source_coverage": (
                    lex_dominant_count / total_sentences if total_sentences else 0.0
                ),
                "distinct_sem_source_poems": len(sem_counter),
                "distinct_lex_source_poems": len(lex_counter),
                "max_consecutive_sem_same_source": max_consecutive_same_source(sem_sequence),
                "max_consecutive_lex_same_source": max_consecutive_same_source(lex_sequence),
                "same_source_sentence_count": same_source_sentence_count,
                "max_sentence_sem_score": max_sentence_sem,
                "max_sentence_lex_score": max_sentence_lex,
            }
        )

    profiles.sort(
        key=lambda row: (
            row["whole_sem_top1_score"] or 0.0,
            row["sem_dominant_source_coverage"],
            row["whole_lex_top1_score"] or 0.0,
        ),
        reverse=True,
    )
    return profiles


def max_consecutive_same_source(sequence):
    best = 0
    current = 0
    prev = None
    for item in sequence:
        if item and item == prev:
            current += 1
        elif item:
            current = 1
        else:
            current = 0
        prev = item
        best = max(best, current)
    return best


def write_csv(path, rows, fieldnames):
    ensure_dir(Path(path).parent)
    with open(path, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main():
    args = parse_args()
    ensure_dir(args.output_dir)
    ensure_dir(args.cache_dir)

    modules = load_st_modules()
    torch = modules["torch"]
    util = modules["util"]
    device = "cuda" if torch.cuda.is_available() else "cpu"

    print("=" * 72)
    print("neo-real-analysis: 历史基线 + 整首溯源 + 句级溯源")
    print(f"device={device} | ai_dbs={','.join(args.ai_dbs)}")
    print("=" * 72)

    ai_poems = load_ai_poems(args.ai_dbs, args.min_rhythm)
    if not ai_poems:
        raise RuntimeError("未加载到任何 AI 宋词样本。")
    target_cipais = {poem["cipai"] for poem in ai_poems if poem["cipai"]}
    print(f"AI poems: {len(ai_poems)} | target cipais: {len(target_cipais)}")

    human_poems = load_human_poems(args.human_db)
    human_poems_by_id = {poem["id"]: poem for poem in human_poems}
    human_sentences = build_human_sentences(human_poems)
    print(f"Human poems: {len(human_poems)} | human sentences: {len(human_sentences)}")

    print("\n[1/5] Loading embedding model and caches ...")
    model = build_model(args.model_path, device)
    whole_embeddings = load_or_build_whole_cache(model, human_poems, args, device)
    sentence_chunk_paths, sentence_cache_meta = load_or_build_sentence_cache(
        model, human_sentences, args, device
    )

    print("\n[2/5] Computing historical baselines ...")
    whole_baseline_rows, whole_baseline_lookup = compute_whole_baseline(
        human_poems,
        whole_embeddings,
        target_cipais,
        args,
        device,
        util,
    )
    sentence_baseline_rows, sentence_baseline_lookup = compute_sentence_baseline(
        human_sentences,
        sentence_chunk_paths,
        target_cipais,
        args,
        device,
        util,
    )

    print("\n[3/5] Running whole-poem retrieval ...")
    ai_poem_embeddings = encode_ai_poems(model, ai_poems, args)
    whole_semantic_candidates = max(args.whole_topk, args.whole_semantic_candidates)
    whole_sem_scores, whole_sem_indices = search_topk_against_tensor(
        ai_poem_embeddings,
        whole_embeddings,
        topk=whole_semantic_candidates,
        query_batch_size=args.query_batch_size,
        device=device,
        util=util,
        exclude_self=False,
    )
    human_whole_ngram_index = build_char_ngram_index(
        [poem["content"] for poem in human_poems],
        ngram_size=2,
    )
    whole_candidate_lists = build_whole_candidate_lists(
        ai_poems,
        human_poems,
        whole_sem_indices,
        human_whole_ngram_index,
        args.whole_lexical_candidates,
    )
    whole_lex_results = run_lexical_topk(
        [poem["content"] for poem in ai_poems],
        [poem["content"] for poem in human_poems],
        whole_candidate_lists,
        topk=args.whole_topk,
        num_workers=args.lexical_workers,
    )

    whole_alignment_rows = []
    whole_top1_by_ai = {}
    for ai_idx, poem in enumerate(ai_poems):
        cipai = poem["cipai"] or "__overall__"
        sem_percentile = percentile_rank(
            whole_baseline_lookup["semantic"].get(cipai)
            or whole_baseline_lookup["semantic"].get("__overall__", []),
            float(whole_sem_scores[ai_idx, 0]),
        )
        lex_top1_score = (
            float(whole_lex_results[ai_idx][0][0]) if whole_lex_results[ai_idx] else 0.0
        )
        lex_percentile = percentile_rank(
            whole_baseline_lookup["lexical"].get(cipai)
            or whole_baseline_lookup["lexical"].get("__overall__", []),
            lex_top1_score,
        )

        sem_top1_idx = int(whole_sem_indices[ai_idx, 0])
        sem_top1_poem = human_poems[sem_top1_idx]
        lex_top1_idx = int(whole_lex_results[ai_idx][0][1]) if whole_lex_results[ai_idx] else -1
        lex_top1_poem = human_poems[lex_top1_idx] if lex_top1_idx >= 0 else {}

        whole_top1_by_ai[poem["ai_uid"]] = {
            "whole_sem_top1_score": float(whole_sem_scores[ai_idx, 0]),
            "whole_sem_top1_source_poem_id": sem_top1_poem["id"],
            "whole_sem_top1_source_title": sem_top1_poem["full_rhythmic"],
            "whole_sem_top1_source_author": sem_top1_poem["author"],
            "whole_sem_percentile": sem_percentile,
            "whole_lex_top1_score": lex_top1_score,
            "whole_lex_top1_source_poem_id": lex_top1_poem.get("id", ""),
            "whole_lex_top1_source_title": lex_top1_poem.get("full_rhythmic", ""),
            "whole_lex_top1_source_author": lex_top1_poem.get("author", ""),
            "whole_lex_percentile": lex_percentile,
        }

        semantic_output_topk = min(args.whole_topk, whole_sem_scores.shape[1])
        for rank in range(semantic_output_topk):
            sem_idx = int(whole_sem_indices[ai_idx, rank])
            sem_poem = human_poems[sem_idx]
            whole_alignment_rows.append(
                {
                    "ai_uid": poem["ai_uid"],
                    "db_key": poem["db_key"],
                    "ai_poem_id": poem["id"],
                    "model_name": poem["model_name"],
                    "ai_cipai": poem["cipai"],
                    "ai_title": poem["title"],
                    "metric_type": "semantic",
                    "rank": rank + 1,
                    "score": f"{float(whole_sem_scores[ai_idx, rank]):.6f}",
                    "source_poem_id": sem_poem["id"],
                    "source_author": sem_poem["author"],
                    "source_cipai": sem_poem["cipai"],
                    "source_title": sem_poem["full_rhythmic"],
                    "source_content": sem_poem["content"],
                }
            )
        for rank, (score, lex_idx) in enumerate(whole_lex_results[ai_idx], start=1):
            lex_poem = human_poems[lex_idx]
            whole_alignment_rows.append(
                {
                    "ai_uid": poem["ai_uid"],
                    "db_key": poem["db_key"],
                    "ai_poem_id": poem["id"],
                    "model_name": poem["model_name"],
                    "ai_cipai": poem["cipai"],
                    "ai_title": poem["title"],
                    "metric_type": "lexical",
                    "rank": rank,
                    "score": f"{float(score):.6f}",
                    "source_poem_id": lex_poem["id"],
                    "source_author": lex_poem["author"],
                    "source_cipai": lex_poem["cipai"],
                    "source_title": lex_poem["full_rhythmic"],
                    "source_content": lex_poem["content"],
                }
            )

    print("\n[4/5] Running sentence-level retrieval ...")
    ai_sentences = build_ai_sentences(ai_poems)
    ai_sentence_embeddings = encode_texts(
        model,
        [sentence["text"] for sentence in ai_sentences],
        args.batch_size,
    )
    sent_sem_scores, sent_sem_indices = search_topk_against_chunks(
        ai_sentence_embeddings,
        sentence_chunk_paths,
        topk=args.sentence_semantic_candidates,
        query_batch_size=args.query_batch_size,
        device=device,
        util=util,
    )
    sent_lex_results = run_lexical_topk(
        [sentence["text"] for sentence in ai_sentences],
        [sentence["text"] for sentence in human_sentences],
        [indices.tolist() for indices in sent_sem_indices],
        topk=args.sentence_topk,
        num_workers=args.lexical_workers,
    )

    sentence_alignment_rows = []
    for sent_idx, ai_sentence in enumerate(ai_sentences):
        sem_topk = []
        for rank in range(min(args.sentence_topk, sent_sem_scores.shape[1])):
            human_idx = int(sent_sem_indices[sent_idx, rank])
            source = human_sentences[human_idx]
            sem_topk.append(
                {
                    "rank": rank + 1,
                    "score": round(float(sent_sem_scores[sent_idx, rank]), 6),
                    "source_sentence_uid": source["sentence_uid"],
                    "source_poem_id": source["poem_id"],
                    "source_author": source["author"],
                    "source_title": source["full_rhythmic"],
                    "source_cipai": source["cipai"],
                    "source_sentence_index": source["sentence_index"],
                    "source_text": source["text"],
                }
            )

        lex_topk = []
        for rank, (score, human_idx) in enumerate(sent_lex_results[sent_idx], start=1):
            source = human_sentences[human_idx]
            lex_topk.append(
                {
                    "rank": rank,
                    "score": round(float(score), 6),
                    "source_sentence_uid": source["sentence_uid"],
                    "source_poem_id": source["poem_id"],
                    "source_author": source["author"],
                    "source_title": source["full_rhythmic"],
                    "source_cipai": source["cipai"],
                    "source_sentence_index": source["sentence_index"],
                    "source_text": source["text"],
                }
            )

        sem_top1 = sem_topk[0] if sem_topk else {}
        lex_top1 = lex_topk[0] if lex_topk else {}
        baseline_key = (
            ai_sentence["cipai"] if ai_sentence["cipai"] else "__overall__",
            ai_sentence["length_bucket"],
        )
        sem_percentile = percentile_rank(
            sentence_baseline_lookup["semantic"].get(baseline_key)
            or sentence_baseline_lookup["semantic"].get(
                ("__overall__", ai_sentence["length_bucket"]),
                [],
            ),
            sem_top1.get("score", 0.0),
        )
        if sem_percentile is None:
            sem_percentile = percentile_rank(
                sentence_baseline_lookup["semantic"].get(
                    ("__overall__", "__overall__"),
                    [],
                ),
                sem_top1.get("score", 0.0),
            )
        lex_percentile = percentile_rank(
            sentence_baseline_lookup["lexical"].get(baseline_key)
            or sentence_baseline_lookup["lexical"].get(
                ("__overall__", ai_sentence["length_bucket"]),
                [],
            ),
            lex_top1.get("score", 0.0),
        )
        if lex_percentile is None:
            lex_percentile = percentile_rank(
                sentence_baseline_lookup["lexical"].get(
                    ("__overall__", "__overall__"),
                    [],
                ),
                lex_top1.get("score", 0.0),
            )

        sentence_alignment_rows.append(
            {
                "ai_uid": ai_sentence["ai_uid"],
                "db_key": ai_sentence["db_key"],
                "ai_poem_id": ai_sentence["poem_id"],
                "model_name": ai_sentence["model_name"],
                "cipai": ai_sentence["cipai"],
                "title": ai_sentence["title"],
                "sentence_index": ai_sentence["sentence_index"],
                "sentence_length_bucket": ai_sentence["length_bucket"],
                "ai_sentence_text": ai_sentence["text"],
                "sem_top1_score": sem_top1.get("score", 0.0),
                "sem_top1_percentile": sem_percentile,
                "sem_top1_source_poem_id": sem_top1.get("source_poem_id", ""),
                "sem_top1_source_author": sem_top1.get("source_author", ""),
                "sem_top1_source_title": sem_top1.get("source_title", ""),
                "sem_top1_source_cipai": sem_top1.get("source_cipai", ""),
                "sem_top1_source_sentence_index": sem_top1.get("source_sentence_index", ""),
                "sem_top1_source_text": sem_top1.get("source_text", ""),
                "lex_top1_score": lex_top1.get("score", 0.0),
                "lex_top1_percentile": lex_percentile,
                "lex_top1_source_poem_id": lex_top1.get("source_poem_id", ""),
                "lex_top1_source_author": lex_top1.get("source_author", ""),
                "lex_top1_source_title": lex_top1.get("source_title", ""),
                "lex_top1_source_cipai": lex_top1.get("source_cipai", ""),
                "lex_top1_source_sentence_index": lex_top1.get("source_sentence_index", ""),
                "lex_top1_source_text": lex_top1.get("source_text", ""),
                "sem_topk_json": compact_json(sem_topk),
                "lex_topk_json": compact_json(lex_topk),
            }
        )

    print("\n[5/5] Aggregating source concentration and writing outputs ...")
    profile_rows = aggregate_sentence_profiles(
        ai_sentences,
        sentence_alignment_rows,
        whole_top1_by_ai,
        human_poems_by_id,
    )

    output_dir = Path(args.output_dir)
    write_csv(
        output_dir / "reference_baseline_whole.csv",
        whole_baseline_rows,
        [
            "scope",
            "cipai",
            "length_bucket",
            "metric_type",
            "count",
            "mean",
            "p50",
            "p90",
            "p95",
            "p99",
            "max",
        ],
    )
    write_csv(
        output_dir / "reference_baseline_sentence.csv",
        sentence_baseline_rows,
        [
            "scope",
            "cipai",
            "length_bucket",
            "metric_type",
            "count",
            "mean",
            "p50",
            "p90",
            "p95",
            "p99",
            "max",
        ],
    )
    write_csv(
        output_dir / "ai_whole_alignment_topk.csv",
        whole_alignment_rows,
        [
            "ai_uid",
            "db_key",
            "ai_poem_id",
            "model_name",
            "ai_cipai",
            "ai_title",
            "metric_type",
            "rank",
            "score",
            "source_poem_id",
            "source_author",
            "source_cipai",
            "source_title",
            "source_content",
        ],
    )
    write_csv(
        output_dir / "ai_sentence_alignment_details.csv",
        sentence_alignment_rows,
        [
            "ai_uid",
            "db_key",
            "ai_poem_id",
            "model_name",
            "cipai",
            "title",
            "sentence_index",
            "sentence_length_bucket",
            "ai_sentence_text",
            "sem_top1_score",
            "sem_top1_percentile",
            "sem_top1_source_poem_id",
            "sem_top1_source_author",
            "sem_top1_source_title",
            "sem_top1_source_cipai",
            "sem_top1_source_sentence_index",
            "sem_top1_source_text",
            "lex_top1_score",
            "lex_top1_percentile",
            "lex_top1_source_poem_id",
            "lex_top1_source_author",
            "lex_top1_source_title",
            "lex_top1_source_cipai",
            "lex_top1_source_sentence_index",
            "lex_top1_source_text",
            "sem_topk_json",
            "lex_topk_json",
        ],
    )
    write_csv(
        output_dir / "ai_poem_source_profile.csv",
        profile_rows,
        [
            "ai_uid",
            "db_key",
            "ai_poem_id",
            "model_name",
            "cipai",
            "title",
            "sentence_count",
            "whole_sem_top1_score",
            "whole_sem_top1_source_poem_id",
            "whole_sem_top1_source_title",
            "whole_sem_top1_source_author",
            "whole_sem_percentile",
            "whole_lex_top1_score",
            "whole_lex_top1_source_poem_id",
            "whole_lex_top1_source_title",
            "whole_lex_top1_source_author",
            "whole_lex_percentile",
            "sem_dominant_source_poem_id",
            "sem_dominant_source_title",
            "sem_dominant_source_author",
            "sem_dominant_source_coverage",
            "lex_dominant_source_poem_id",
            "lex_dominant_source_title",
            "lex_dominant_source_author",
            "lex_dominant_source_coverage",
            "distinct_sem_source_poems",
            "distinct_lex_source_poems",
            "max_consecutive_sem_same_source",
            "max_consecutive_lex_same_source",
            "same_source_sentence_count",
            "max_sentence_sem_score",
            "max_sentence_lex_score",
        ],
    )

    metadata = {
        "ai_db_keys": args.ai_dbs,
        "human_db": str(Path(args.human_db).resolve()),
        "model_path": str(Path(args.model_path).resolve()),
        "device": device,
        "ai_poem_count": len(ai_poems),
        "ai_sentence_count": len(ai_sentences),
        "human_poem_count": len(human_poems),
        "human_sentence_count": len(human_sentences),
        "target_cipai_count": len(target_cipais),
        "sentence_cache_chunks": len(sentence_chunk_paths),
        "sentence_cache_count": sentence_cache_meta.get("count"),
        "whole_topk": args.whole_topk,
        "whole_semantic_candidates": whole_semantic_candidates,
        "sentence_topk": args.sentence_topk,
        "sentence_semantic_candidates": args.sentence_semantic_candidates,
        "whole_lexical_candidates": args.whole_lexical_candidates,
    }
    (output_dir / "run_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("\nDone.")
    print(f"Outputs written to: {output_dir}")


if __name__ == "__main__":
    main()
