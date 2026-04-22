import argparse
import csv
import difflib
import json
import math
import random
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

AI_DATABASES = {
    "a1": {
        "db_path": "database/a1.db",
        "label": "无限制生成",
        "mode": "free",
        "allowed_cipais": None,
        "prompt_type": "type_c",
    },
    "b1": {
        "db_path": "database/b1.db",
        "label": "五词牌-无主题",
        "mode": "fixed_pool",
        "allowed_cipais": ["菩萨蛮", "沁园春", "清平乐", "祝英台近", "浪淘沙"],
        "prompt_type": "type_b",
    },
    "b2": {
        "db_path": "database/b2.db",
        "label": "五词牌-改革主题",
        "mode": "fixed_pool",
        "allowed_cipais": ["菩萨蛮", "沁园春", "清平乐", "祝英台近", "浪淘沙"],
        "prompt_type": "type_d",
    },
    "b3": {
        "db_path": "database/b3.db",
        "label": "五词牌-玉兰主题",
        "mode": "fixed_pool",
        "allowed_cipais": ["菩萨蛮", "沁园春", "清平乐", "祝英台近", "浪淘沙"],
        "prompt_type": "type_d",
    },
    "c1": {
        "db_path": "database/c1.db",
        "label": "沁园春-玉兰主题",
        "mode": "single_cipai",
        "allowed_cipais": ["沁园春"],
        "prompt_type": "type_a",
    },
    "c2": {
        "db_path": "database/c2.db",
        "label": "沁园春-改革主题",
        "mode": "single_cipai",
        "allowed_cipais": ["沁园春"],
        "prompt_type": "type_e",
    },
}

DEFAULT_HUMAN_DB = "database/real_song_ci_dataset.db"
EMBEDDING_MODEL_NAME = "analyze/BERT-CCPoem-Model"
RESULT_DIR = Path("result/neo-analysis")

WHOLE_HIGH_SIM_THRESHOLD = 0.85
SENT_HIGH_SIM_THRESHOLD = 0.85
PSEUDO_DIFF_THRESHOLD = 0.30
SINGLE_CIPAI_FALLBACK_MIN_POEMS = 4

ST_MODULES = None

IMAGERY_SYNONYM_MAP = {
    "白玉兰": "玉兰",
    "玉兰花": "玉兰",
}


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
                "neo-analysis 需要安装 torch 和 sentence-transformers。"
                " 当前环境缺少相关依赖，请在具备这些依赖的 Python 环境中运行。"
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
        description="统一分析 AI 宋词的内部同质化程度。"
    )
    parser.add_argument(
        "--ai-dbs",
        nargs="+",
        default=list(AI_DATABASES.keys()),
        choices=list(AI_DATABASES.keys()),
        help="要分析的 AI 数据库代号。",
    )
    parser.add_argument(
        "--human-db",
        default=DEFAULT_HUMAN_DB,
        help="人类宋词基线数据库。默认使用 real_song_ci_dataset.db。",
    )
    parser.add_argument(
        "--output-dir",
        default=str(RESULT_DIR),
        help="输出目录。",
    )
    parser.add_argument(
        "--min-rhythm",
        type=float,
        default=60.0,
        help="AI 样本的最低格律分数阈值。",
    )
    parser.add_argument(
        "--min-model-poems",
        type=int,
        default=30,
        help="纳入主排名的模型最低样本数。",
    )
    parser.add_argument(
        "--min-poems-per-cipai",
        type=int,
        default=8,
        help="纳入词牌分析的最低样本数。",
    )
    parser.add_argument(
        "--max-poems-per-cipai",
        type=int,
        default=20,
        help="每个词牌每轮抽样的最大作品数。",
    )
    parser.add_argument(
        "--resample-rounds",
        type=int,
        default=5,
        help="每个词牌的重复抽样轮数。",
    )
    parser.add_argument(
        "--sentence-topk",
        type=int,
        default=3,
        help="句级匹配时每个词对取前 k 个最强句对。",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="随机种子。",
    )
    return parser.parse_args()


def map_model_name(raw_name):
    if not raw_name:
        return "Unknown"
    mapping = {
        "doubao-seed-2-0-pro-260215": "doubao-seed-2.0-pro",
        "deepseek-reasoner": "deepseek-3.2-thinking",
        "deepseek-v3.2": "deepseek-3.2-thinking",
        "qwen3.5-plus-2026-02-15": "qwen3.5-plus",
        "qwen3.6-plus": "qwen3.6-plus",
        "gemini-3.1-pro-preview": "gemini-3.1-pro",
        "gemini-3-flash-preview": "gemini-3-flash",
    }
    return mapping.get(raw_name, raw_name)


def split_into_sentences(text):
    parts = re.split(r"[，。！？；\n]", text or "")
    return [part.strip() for part in parts if part and part.strip()]


def calc_lexical_similarity(text1, text2):
    return difflib.SequenceMatcher(None, text1 or "", text2 or "").ratio()


def calc_jaccard(set_a, set_b):
    if not set_a and not set_b:
        return 0.0
    union = set_a | set_b
    if not union:
        return 0.0
    return len(set_a & set_b) / len(union)


def normalize_imagery_token(token):
    token = re.sub(r"[，。！？；、\s]", "", str(token or ""))
    token = IMAGERY_SYNONYM_MAP.get(token, token)
    return token.strip()


def calc_token_overlap_score(token_a, token_b):
    if not token_a or not token_b:
        return 0.0
    if token_a == token_b:
        return 1.0
    if token_a in token_b or token_b in token_a:
        return 0.85
    char_a = set(token_a)
    char_b = set(token_b)
    char_union = char_a | char_b
    char_jaccard = len(char_a & char_b) / len(char_union) if char_union else 0.0
    seq_ratio = difflib.SequenceMatcher(None, token_a, token_b).ratio()
    return max(char_jaccard, seq_ratio)


def calc_soft_jaccard(set_a, set_b):
    if not set_a and not set_b:
        return 0.0
    if not set_a or not set_b:
        return 0.0

    remaining_b = list(set_b)
    matched = 0
    for token_a in sorted(set_a):
        best_idx = None
        best_score = 0.0
        for idx, token_b in enumerate(remaining_b):
            score = calc_token_overlap_score(token_a, token_b)
            if score > best_score:
                best_score = score
                best_idx = idx
        if best_idx is not None and best_score >= 0.67:
            matched += 1
            remaining_b.pop(best_idx)

    denom = len(set_a) + len(set_b) - matched
    return matched / denom if denom > 0 else 0.0


def safe_percentile(values, percentile):
    if not values:
        return 0.0
    sorted_values = sorted(float(value) for value in values)
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = (len(sorted_values) - 1) * (percentile / 100.0)
    lower_index = int(math.floor(position))
    upper_index = int(math.ceil(position))
    if lower_index == upper_index:
        return sorted_values[lower_index]
    lower_value = sorted_values[lower_index]
    upper_value = sorted_values[upper_index]
    weight = position - lower_index
    return lower_value + (upper_value - lower_value) * weight


def safe_mean(values):
    values = list(values)
    if not values:
        return 0.0
    return sum(float(value) for value in values) / len(values)


def calc_normalized_entropy(counter):
    total = sum(counter.values())
    if total <= 0 or len(counter) <= 1:
        return 0.0
    entropy = 0.0
    for count in counter.values():
        if count <= 0:
            continue
        p = count / total
        entropy -= p * math.log2(p)
    max_entropy = math.log2(len(counter))
    return entropy / max_entropy if max_entropy > 0 else 0.0


def parse_json_list(raw_value):
    if not raw_value:
        return []
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
        return []
    if isinstance(parsed, list):
        normalized = []
        for item in parsed:
            token = normalize_imagery_token(item)
            if token:
                normalized.append(token)
        return normalized
    return []


def load_ai_records(db_path, min_rhythm):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    rows = cursor.execute(
        """
        SELECT id, cipai, title, content, imagery, category, model_name, rhythm_score
        FROM ci_data
        WHERE content IS NOT NULL
          AND TRIM(content) != ''
          AND (rhythm_score IS NULL OR rhythm_score >= ?)
        """,
        (min_rhythm,),
    ).fetchall()
    conn.close()

    records = []
    for row in rows:
        records.append(
            {
                "id": row["id"],
                "cipai": row["cipai"] or "",
                "title": row["title"] or "",
                "content": row["content"] or "",
                "imagery": parse_json_list(row["imagery"]),
                "category": (row["category"] or "").strip(),
                "model_name": map_model_name(row["model_name"]),
                "rhythm_score": row["rhythm_score"],
            }
        )
    return records


def load_human_records(db_path, allowed_cipais):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    placeholders = ",".join("?" for _ in allowed_cipais)
    rows = cursor.execute(
        f"""
        SELECT id, author, cipai, content, rhythm_score
        FROM real_ci_data
        WHERE content IS NOT NULL
          AND TRIM(content) != ''
          AND cipai IN ({placeholders})
        """,
        tuple(sorted(allowed_cipais)),
    ).fetchall()
    conn.close()

    grouped = defaultdict(list)
    for row in rows:
        grouped[row["cipai"]].append(
            {
                "id": row["id"],
                "title": row["author"] or "",
                "cipai": row["cipai"] or "",
                "content": row["content"] or "",
                "imagery": [],
                "category": "",
                "model_name": "human_baseline",
                "rhythm_score": row["rhythm_score"],
            }
        )
    return grouped


def build_sentence_model():
    st = load_st_modules()
    device = "cuda" if st["torch"].cuda.is_available() else "cpu"
    word_embedding_model = st["models"].Transformer(EMBEDDING_MODEL_NAME)
    pooling_model = st["models"].Pooling(
        word_embedding_model.get_word_embedding_dimension(),
        pooling_mode_mean_tokens=True,
        pooling_mode_cls_token=False,
        pooling_mode_max_tokens=False,
    )
    model = st["SentenceTransformer"](
        modules=[word_embedding_model, pooling_model],
        device=device,
    )
    return model


def choose_target_sizes(experiment_key, grouped_records, args):
    metadata = AI_DATABASES[experiment_key]
    if metadata["mode"] == "free":
        return None

    eligible_models = {
        model_name: rows
        for model_name, rows in grouped_records.items()
        if len(rows) >= args.min_model_poems
    }
    target_sizes = {}
    for cipai in metadata["allowed_cipais"] or []:
        counts = []
        for rows in eligible_models.values():
            count = sum(1 for row in rows if row["cipai"] == cipai)
            if count >= args.min_poems_per_cipai:
                counts.append(count)
        if counts:
            target_sizes[cipai] = min(args.max_poems_per_cipai, min(counts))
    return target_sizes


def choose_free_mode_target_sizes(model_records, args):
    counter = Counter(row["cipai"] for row in model_records if row["cipai"])
    target_sizes = {}
    for cipai, count in counter.items():
        if count >= args.min_poems_per_cipai:
            target_sizes[cipai] = min(args.max_poems_per_cipai, count)
    return target_sizes


def compute_whole_metrics(poems, encoder):
    st = load_st_modules()
    texts = [poem["content"] for poem in poems]
    embeddings = encoder.encode(
        texts,
        batch_size=64,
        convert_to_tensor=True,
        show_progress_bar=False,
    )
    cos_np = st["util"].cos_sim(embeddings, embeddings).cpu().numpy()

    sem_sims = []
    lex_sims = []
    for i in range(len(poems)):
        for j in range(i + 1, len(poems)):
            sem = float(cos_np[i, j])
            lex = calc_lexical_similarity(texts[i], texts[j])
            sem_sims.append(sem)
            lex_sims.append(lex)

    diffs = [s - l for s, l in zip(sem_sims, lex_sims)]
    whole_highsim_ratio = (
        sum(1 for value in sem_sims if value >= WHOLE_HIGH_SIM_THRESHOLD) / len(sem_sims)
        if sem_sims
        else 0.0
    )
    whole_pseudo_ratio = (
        sum(1 for value in diffs if value > PSEUDO_DIFF_THRESHOLD) / len(diffs)
        if diffs
        else 0.0
    )

    return {
        "whole_sem_p50": safe_percentile(sem_sims, 50),
        "whole_sem_p90": safe_percentile(sem_sims, 90),
        "whole_lex_p50": safe_percentile(lex_sims, 50),
        "whole_lex_p90": safe_percentile(lex_sims, 90),
        "whole_highsim_ratio": whole_highsim_ratio,
        "whole_pseudo_ratio": whole_pseudo_ratio,
        "whole_pair_count": len(sem_sims),
    }


def compute_sentence_metrics(poems, encoder, topk):
    st = load_st_modules()
    sentence_items = []
    poem_to_sent_idx = defaultdict(list)
    for poem_index, poem in enumerate(poems):
        for sentence in split_into_sentences(poem["content"]):
            sent_idx = len(sentence_items)
            sentence_items.append((poem_index, sentence))
            poem_to_sent_idx[poem_index].append(sent_idx)

    if len(sentence_items) < 2:
        return {
            "sent_highsim_ratio": 0.0,
            "sent_pseudo_ratio": 0.0,
            "top1_sent_mean": 0.0,
            "topk_sent_mean": 0.0,
            "sentence_pair_count": 0,
            "sentence_count": len(sentence_items),
        }

    sent_texts = [item[1] for item in sentence_items]
    sent_embeddings = encoder.encode(
        sent_texts,
        batch_size=128,
        convert_to_tensor=True,
        show_progress_bar=False,
    )
    cos_np = st["util"].cos_sim(sent_embeddings, sent_embeddings).cpu().numpy()

    poem_pair_count = 0
    raw_sentence_comparison_count = 0
    top1_scores = []
    topk_scores = []
    pair_high_coverages = []
    pair_pseudo_coverages = []

    for poem_i in range(len(poems)):
        indices_i = poem_to_sent_idx.get(poem_i, [])
        if not indices_i:
            continue
        for poem_j in range(poem_i + 1, len(poems)):
            indices_j = poem_to_sent_idx.get(poem_j, [])
            if not indices_j:
                continue

            local_scores = []
            for sent_i in indices_i:
                for sent_j in indices_j:
                    sem = float(cos_np[sent_i, sent_j])
                    lex = calc_lexical_similarity(sent_texts[sent_i], sent_texts[sent_j])
                    diff = sem - lex
                    raw_sentence_comparison_count += 1
                    local_scores.append((sem, diff))

            if local_scores:
                poem_pair_count += 1
                local_scores.sort(key=lambda item: item[0], reverse=True)
                top_local = local_scores[: min(topk, len(local_scores))]
                top1_scores.append(top_local[0][0])
                topk_scores.append(safe_mean(score for score, _ in top_local))
                pair_high_coverages.append(
                    sum(1 for score, _ in top_local if score >= SENT_HIGH_SIM_THRESHOLD) / len(top_local)
                )
                pair_pseudo_coverages.append(
                    sum(1 for _, diff in top_local if diff > PSEUDO_DIFF_THRESHOLD) / len(top_local)
                )

    return {
        "sent_highsim_ratio": safe_mean(pair_high_coverages),
        "sent_pseudo_ratio": safe_mean(pair_pseudo_coverages),
        "top1_sent_mean": safe_mean(top1_scores),
        "topk_sent_mean": safe_mean(topk_scores),
        "sentence_pair_count": poem_pair_count,
        "raw_sentence_comparison_count": raw_sentence_comparison_count,
        "sentence_count": len(sentence_items),
    }


def compute_imagery_metrics(poems):
    imagery_sets = [set(poem["imagery"]) for poem in poems]
    imagery_counter = Counter()
    category_counter = Counter()

    for poem in poems:
        imagery_counter.update(poem["imagery"])
        if poem["category"]:
            category_counter.update([poem["category"]])

    jaccards = []
    for i in range(len(imagery_sets)):
        for j in range(i + 1, len(imagery_sets)):
            jaccards.append(calc_soft_jaccard(imagery_sets[i], imagery_sets[j]))

    total_imagery = sum(imagery_counter.values())
    top10_imagery = sum(count for _, count in imagery_counter.most_common(10))
    top10_concentration = top10_imagery / total_imagery if total_imagery else 0.0

    return {
        "imagery_jaccard_p50": safe_percentile(jaccards, 50),
        "imagery_jaccard_p90": safe_percentile(jaccards, 90),
        "imagery_entropy": calc_normalized_entropy(imagery_counter),
        "top10_imagery_concentration": top10_concentration,
        "category_entropy": calc_normalized_entropy(category_counter),
        "distinct_imagery_count": len(imagery_counter),
        "distinct_category_count": len(category_counter),
    }


def calc_scores(metric_map):
    whole_score = (
        0.50 * metric_map["whole_sem_p50"]
        + 0.30 * metric_map["whole_sem_p90"]
        + 0.20 * metric_map["whole_highsim_ratio"]
    )
    sent_score = (
        0.40 * metric_map["sent_highsim_ratio"]
        + 0.30 * metric_map["sent_pseudo_ratio"]
        + 0.30 * metric_map["top1_sent_mean"]
    )
    imagery_score = (
        0.35 * metric_map["imagery_jaccard_p50"]
        + 0.25 * metric_map["imagery_jaccard_p90"]
        + 0.20 * metric_map["top10_imagery_concentration"]
        + 0.10 * (1 - metric_map["imagery_entropy"])
        + 0.10 * (1 - metric_map["category_entropy"])
    )
    core_mihi = 0.55 * whole_score + 0.45 * sent_score
    full_mihi = 0.45 * whole_score + 0.35 * sent_score + 0.20 * imagery_score
    return {
        "whole_score": whole_score,
        "sent_score": sent_score,
        "imagery_score": imagery_score,
        "core_mihi": core_mihi,
        "mihi_full": full_mihi,
    }


def merge_metric_maps(metric_maps):
    merged = {}
    keys = set()
    for metric_map in metric_maps:
        keys.update(metric_map.keys())
    for key in keys:
        values = [metric_map[key] for metric_map in metric_maps if key in metric_map]
        if values:
            merged[key] = safe_mean(values)
    return merged


def aggregate_weighted_metrics(rows, weighted_keys):
    if not rows:
        return {}
    total_weight = sum(row["weight"] for row in rows)
    aggregate = {}
    for key in weighted_keys:
        if total_weight > 0:
            aggregate[key] = sum(row.get(key, 0.0) * row["weight"] for row in rows) / total_weight
        else:
            aggregate[key] = 0.0
    return aggregate


def analyze_sampled_poems(poems, encoder, topk):
    whole = compute_whole_metrics(poems, encoder)
    sentence = compute_sentence_metrics(poems, encoder, topk=topk)
    imagery = compute_imagery_metrics(poems)
    combined = {}
    combined.update(whole)
    combined.update(sentence)
    combined.update(imagery)
    combined.update(calc_scores(combined))
    return combined


def build_rng(seed, *parts):
    text = "|".join(str(part) for part in parts)
    return random.Random(f"{seed}|{text}")


def sample_records(records, sample_size, rng):
    if len(records) <= sample_size:
        return list(records)
    return rng.sample(records, sample_size)


def build_human_baseline_cache(human_records_by_cipai, encoder, args):
    cache = {}

    def get(cipai, sample_size):
        key = (cipai, sample_size)
        if key in cache:
            return cache[key]

        source_records = human_records_by_cipai.get(cipai, [])
        if len(source_records) < max(sample_size, args.min_poems_per_cipai):
            cache[key] = None
            return None

        round_metrics = []
        for round_idx in range(args.resample_rounds):
            rng = build_rng(args.seed, "human", cipai, sample_size, round_idx)
            sampled = sample_records(source_records, sample_size, rng)
            metrics = analyze_sampled_poems(sampled, encoder, args.sentence_topk)
            round_metrics.append(metrics)

        averaged = merge_metric_maps(round_metrics)
        cache[key] = averaged
        return averaged

    return get


def analyze_model(
    experiment_key,
    experiment_rows,
    model_name,
    encoder,
    args,
    human_baseline_getter,
    target_sizes,
):
    cipai_rows = []
    for cipai, sample_size in sorted(target_sizes.items()):
        poems = [row for row in experiment_rows if row["cipai"] == cipai]
        if len(poems) < sample_size or sample_size < args.min_poems_per_cipai:
            continue

        sampled_metric_rounds = []
        for round_idx in range(args.resample_rounds):
            rng = build_rng(args.seed, experiment_key, model_name, cipai, round_idx)
            sampled_poems = sample_records(poems, sample_size, rng)
            sampled_metric_rounds.append(
                analyze_sampled_poems(sampled_poems, encoder, args.sentence_topk)
            )

        averaged_metrics = merge_metric_maps(sampled_metric_rounds)
        human_metrics = human_baseline_getter(cipai, sample_size) if human_baseline_getter else None

        cipai_row = {
            "db": experiment_key,
            "db_label": AI_DATABASES[experiment_key]["label"],
            "prompt_type": AI_DATABASES[experiment_key]["prompt_type"],
            "model": model_name,
            "cipai": cipai,
            "poem_count_total": len(poems),
            "poem_count_used": sample_size,
            "resample_rounds": args.resample_rounds,
            "weight": sample_size,
        }
        cipai_row.update(averaged_metrics)
        if human_metrics:
            cipai_row["human_whole_score"] = human_metrics["whole_score"]
            cipai_row["human_sent_score"] = human_metrics["sent_score"]
            cipai_row["human_core_mihi"] = human_metrics["core_mihi"]
            cipai_row["excess_core_homogeneity"] = (
                cipai_row["core_mihi"] - human_metrics["core_mihi"]
            )
        else:
            cipai_row["human_whole_score"] = ""
            cipai_row["human_sent_score"] = ""
            cipai_row["human_core_mihi"] = ""
            cipai_row["excess_core_homogeneity"] = ""
        cipai_rows.append(cipai_row)

    if not cipai_rows:
        return None, []

    weighted_keys = {
        "whole_sem_p50",
        "whole_sem_p90",
        "whole_lex_p50",
        "whole_lex_p90",
        "whole_highsim_ratio",
        "whole_pseudo_ratio",
        "whole_pair_count",
        "sent_highsim_ratio",
        "sent_pseudo_ratio",
        "top1_sent_mean",
        "topk_sent_mean",
        "sentence_pair_count",
        "raw_sentence_comparison_count",
        "sentence_count",
        "imagery_jaccard_p50",
        "imagery_jaccard_p90",
        "imagery_entropy",
        "top10_imagery_concentration",
        "category_entropy",
        "distinct_imagery_count",
        "distinct_category_count",
        "whole_score",
        "sent_score",
        "imagery_score",
        "core_mihi",
        "mihi_full",
    }
    summary_metrics = aggregate_weighted_metrics(cipai_rows, weighted_keys)

    cipai_counter = Counter(row["cipai"] for row in experiment_rows if row["cipai"])
    cipai_entropy = calc_normalized_entropy(cipai_counter)

    human_rows = [row for row in cipai_rows if row["human_core_mihi"] != ""]
    if human_rows:
        human_total_weight = sum(row["weight"] for row in human_rows)
        human_core_mihi = (
            sum(row["human_core_mihi"] * row["weight"] for row in human_rows) / human_total_weight
            if human_total_weight
            else 0.0
        )
        excess_core = summary_metrics["core_mihi"] - human_core_mihi
    else:
        human_core_mihi = ""
        excess_core = ""

    used_poems = int(sum(row["weight"] for row in cipai_rows))
    used_cipai_count = len(cipai_rows)

    if AI_DATABASES[experiment_key]["mode"] == "single_cipai":
        status = "main" if len(experiment_rows) >= args.min_model_poems and used_cipai_count >= 1 else "low_sample"
    elif AI_DATABASES[experiment_key]["mode"] == "free":
        status = "exploratory"
    else:
        enough_cipai = used_cipai_count >= 3
        enough_used_poems = used_poems >= args.min_poems_per_cipai * 3
        enough_total_poems = len(experiment_rows) >= args.min_model_poems
        status = "main" if (enough_cipai and enough_used_poems and enough_total_poems) else "low_sample"

    summary_row = {
        "db": experiment_key,
        "db_label": AI_DATABASES[experiment_key]["label"],
        "prompt_type": AI_DATABASES[experiment_key]["prompt_type"],
        "model": model_name,
        "total_poems": len(experiment_rows),
        "used_poems": used_poems,
        "used_cipai_count": used_cipai_count,
        "used_cipais": "|".join(row["cipai"] for row in cipai_rows),
        "cipai_entropy": cipai_entropy,
        "status": status,
    }
    summary_row.update(summary_metrics)
    if human_rows:
        summary_row["human_whole_score"] = (
            sum(row["human_whole_score"] * row["weight"] for row in human_rows) / human_total_weight
            if human_total_weight
            else 0.0
        )
        summary_row["human_sent_score"] = (
            sum(row["human_sent_score"] * row["weight"] for row in human_rows) / human_total_weight
            if human_total_weight
            else 0.0
        )
    else:
        summary_row["human_whole_score"] = ""
        summary_row["human_sent_score"] = ""
    summary_row["human_core_mihi"] = human_core_mihi
    summary_row["excess_core_homogeneity"] = excess_core
    return summary_row, cipai_rows


def format_value(value):
    if value == "":
        return ""
    if isinstance(value, float):
        return f"{value:.6f}"
    return value


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8-sig")
        return
    fieldnames = []
    for row in rows:
        for key in row.keys():
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: format_value(row.get(key, "")) for key in fieldnames})


def build_delta_rows(summary_rows, cipai_rows):
    summary_index = {(row["db"], row["model"]): row for row in summary_rows}
    cipai_index = {(row["db"], row["model"], row["cipai"]): row for row in cipai_rows}
    delta_specs = [
        ("a1", "b1", None, "词牌约束效应"),
        ("b1", "b2", None, "改革主题效应"),
        ("b1", "b3", None, "玉兰主题效应"),
        ("b2", "c2", "沁园春", "改革-沁园春强约束与prompt精简效应"),
        ("b3", "c1", "沁园春", "玉兰-沁园春强约束与prompt精简效应"),
    ]

    delta_rows = []
    all_models = sorted(set(row["model"] for row in summary_rows))
    for from_db, to_db, cipai, label in delta_specs:
        for model_name in all_models:
            if cipai:
                left = cipai_index.get((from_db, model_name, cipai))
                right = cipai_index.get((to_db, model_name, cipai))
            else:
                left = summary_index.get((from_db, model_name))
                right = summary_index.get((to_db, model_name))
            if not left or not right:
                continue

            delta_rows.append(
                {
                    "contrast": label,
                    "scope": cipai or "model_level",
                    "model": model_name,
                    "from_db": from_db,
                    "to_db": to_db,
                    "delta_mihi_full": right["mihi_full"] - left["mihi_full"],
                    "delta_core_mihi": right["core_mihi"] - left["core_mihi"],
                    "delta_whole_score": right["whole_score"] - left["whole_score"],
                    "delta_sent_score": right["sent_score"] - left["sent_score"],
                    "delta_imagery_score": right.get("imagery_score", 0.0) - left.get("imagery_score", 0.0),
                }
            )
    return delta_rows


def run_analysis_phase(args, encoder, phase_name, min_rhythm, output_suffix, write_legacy_names=False):
    output_dir = Path(args.output_dir)
    allowed_cipais = set()
    for metadata in AI_DATABASES.values():
        if metadata["allowed_cipais"]:
            allowed_cipais.update(metadata["allowed_cipais"])
    for experiment_key in args.ai_dbs:
        if AI_DATABASES[experiment_key]["mode"] == "free":
            ai_records = load_ai_records(AI_DATABASES[experiment_key]["db_path"], min_rhythm)
            allowed_cipais.update(
                row["cipai"] for row in ai_records if row["cipai"]
            )

    print("-" * 72)
    print(f"[{phase_name}] 载入人类基线数据...")
    human_records_by_cipai = load_human_records(args.human_db, allowed_cipais)
    print(f"[{phase_name}] 人类词牌基线数: {len(human_records_by_cipai)} 个词牌")
    human_baseline_getter = build_human_baseline_cache(human_records_by_cipai, encoder, args)

    summary_rows = []
    cipai_rows = []
    low_sample_rows = []

    for experiment_key in args.ai_dbs:
        metadata = AI_DATABASES[experiment_key]
        print("-" * 72)
        print(
            f"[{phase_name}][{experiment_key}] {metadata['label']} | "
            f"Prompt={metadata['prompt_type']} | 读取 {metadata['db_path']}"
        )
        records = load_ai_records(metadata["db_path"], min_rhythm)
        grouped_records = defaultdict(list)
        for row in records:
            grouped_records[row["model_name"]].append(row)

        print(
            "模型样本量: "
            + ", ".join(
                f"{model_name}={len(rows)}" for model_name, rows in sorted(grouped_records.items())
            )
        )

        common_target_sizes = choose_target_sizes(experiment_key, grouped_records, args)
        if common_target_sizes:
            print(f"公共抽样词牌: {common_target_sizes}")

        for model_name, model_rows in sorted(grouped_records.items()):
            if metadata["mode"] == "free":
                target_sizes = choose_free_mode_target_sizes(model_rows, args)
            else:
                target_sizes = dict(common_target_sizes or {})

            summary_row, model_cipai_rows = analyze_model(
                experiment_key=experiment_key,
                experiment_rows=model_rows,
                model_name=model_name,
                encoder=encoder,
                args=args,
                human_baseline_getter=human_baseline_getter,
                target_sizes=target_sizes,
            )

            if summary_row:
                summary_rows.append(summary_row)
                cipai_rows.extend(model_cipai_rows)
                if summary_row["status"] != "main":
                    low_sample_rows.append(summary_row)
                print(
                    f"  {model_name}: full={summary_row['mihi_full']:.4f}, "
                    f"core={summary_row['core_mihi']:.4f}, "
                    f"used_cipais={summary_row['used_cipais']}"
                )
            else:
                fallback_summary_row = None
                fallback_cipai_rows = []

                if metadata["mode"] == "single_cipai" and metadata["allowed_cipais"]:
                    cipai_name = metadata["allowed_cipais"][0]
                    available_count = sum(1 for row in model_rows if row["cipai"] == cipai_name)
                    if available_count >= SINGLE_CIPAI_FALLBACK_MIN_POEMS:
                        fallback_target_sizes = {
                            cipai_name: min(args.max_poems_per_cipai, available_count)
                        }
                        fallback_summary_row, fallback_cipai_rows = analyze_model(
                            experiment_key=experiment_key,
                            experiment_rows=model_rows,
                            model_name=model_name,
                            encoder=encoder,
                            args=args,
                            human_baseline_getter=human_baseline_getter,
                            target_sizes=fallback_target_sizes,
                        )

                if fallback_summary_row:
                    summary_rows.append(fallback_summary_row)
                    cipai_rows.extend(fallback_cipai_rows)
                    low_sample_rows.append(fallback_summary_row)
                    print(
                        f"  {model_name}: full={fallback_summary_row['mihi_full']:.4f}, "
                        f"core={fallback_summary_row['core_mihi']:.4f}, "
                        f"used_cipais={fallback_summary_row['used_cipais']} [low_sample]"
                    )
                else:
                    low_sample_rows.append(
                        {
                            "db": experiment_key,
                            "db_label": metadata["label"],
                            "prompt_type": metadata["prompt_type"],
                            "model": model_name,
                            "total_poems": len(model_rows),
                            "status": "insufficient_usable_cipai",
                        }
                    )
                    print(f"  {model_name}: 可用词牌不足，跳过")

    main_summary_rows = [row for row in summary_rows if row["status"] == "main"]
    delta_rows = build_delta_rows(main_summary_rows, cipai_rows)

    status_rank = {"main": 0, "exploratory": 1, "low_sample": 2, "insufficient_usable_cipai": 3}
    summary_rows.sort(key=lambda row: (row["db"], status_rank.get(row["status"], 9), -row["mihi_full"], row["model"]))
    cipai_rows.sort(key=lambda row: (row["db"], row["model"], row["cipai"]))
    low_sample_rows.sort(key=lambda row: (row["db"], row["model"]))
    delta_rows.sort(key=lambda row: (row["contrast"], row["model"]))

    model_summary_path = output_dir / f"neo_model_summary_{output_suffix}.csv"
    cipai_summary_path = output_dir / f"neo_cipai_summary_{output_suffix}.csv"
    low_sample_path = output_dir / f"neo_low_sample_models_{output_suffix}.csv"
    delta_path = output_dir / f"neo_condition_deltas_{output_suffix}.csv"

    write_csv(model_summary_path, summary_rows)
    write_csv(cipai_summary_path, cipai_rows)
    write_csv(low_sample_path, low_sample_rows)
    write_csv(delta_path, delta_rows)

    if write_legacy_names:
        write_csv(output_dir / "neo_model_summary.csv", summary_rows)
        write_csv(output_dir / "neo_cipai_summary.csv", cipai_rows)
        write_csv(output_dir / "neo_low_sample_models.csv", low_sample_rows)
        write_csv(output_dir / "neo_condition_deltas.csv", delta_rows)

    print("-" * 72)
    print(f"[{phase_name}] 结果已写入: {output_dir}")
    print(f"[{phase_name}] 模型汇总: {model_summary_path}")
    print(f"[{phase_name}] 词牌汇总: {cipai_summary_path}")
    print(f"[{phase_name}] 低样本列表: {low_sample_path}")
    print(f"[{phase_name}] 条件差分: {delta_path}")


def main():
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 72)
    print("neo-analysis: AI宋词内部同质化统一分析")
    print(f"AI数据库: {', '.join(args.ai_dbs)}")
    print(f"人类基线数据库: {args.human_db}")
    print(f"主分析格律阈值: {args.min_rhythm}")
    print("观察分析格律阈值: 0.0")
    print("=" * 72)

    print("加载句向量模型...")
    encoder = build_sentence_model()

    run_analysis_phase(
        args=args,
        encoder=encoder,
        phase_name="strict-main",
        min_rhythm=args.min_rhythm,
        output_suffix="strict",
        write_legacy_names=True,
    )
    run_analysis_phase(
        args=args,
        encoder=encoder,
        phase_name="observe-all-rhythm",
        min_rhythm=0.0,
        output_suffix="observe",
        write_legacy_names=False,
    )
    print("=" * 72)


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        raise SystemExit(1) from exc
