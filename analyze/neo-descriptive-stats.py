import csv
import json
import math
import re
import sqlite3
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path


AI_DATABASES = {
    "a1": {
        "db_path": "database/a1.db",
        "label": "无限制生成",
        "prompt_type": "type_c",
    },
    "b1": {
        "db_path": "database/b1.db",
        "label": "五词牌-无主题",
        "prompt_type": "type_b",
    },
    "b2": {
        "db_path": "database/b2.db",
        "label": "五词牌-改革主题",
        "prompt_type": "type_d",
    },
    "b3": {
        "db_path": "database/b3.db",
        "label": "五词牌-玉兰主题",
        "prompt_type": "type_d",
    },
    "c1": {
        "db_path": "database/c1.db",
        "label": "沁园春-玉兰主题",
        "prompt_type": "type_a",
    },
    "c2": {
        "db_path": "database/c2.db",
        "label": "沁园春-改革主题",
        "prompt_type": "type_e",
    },
}

OUTPUT_DIR = Path("result/descriptive-stats")

IMAGERY_SYNONYM_MAP = {
    "白玉兰": "玉兰",
    "玉兰花": "玉兰",
}


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


def normalize_imagery_token(token):
    token = re.sub(r"[，。！？；、\s]", "", str(token or ""))
    token = IMAGERY_SYNONYM_MAP.get(token, token)
    return token.strip()


def parse_json_list(raw_value):
    if not raw_value:
        return []
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    tokens = []
    for item in parsed:
        token = normalize_imagery_token(item)
        if token:
            tokens.append(token)
    return tokens


def calc_entropy(counter):
    total = sum(counter.values())
    if total <= 0:
        return 0.0
    entropy = 0.0
    for count in counter.values():
        if count <= 0:
            continue
        p = count / total
        entropy -= p * math.log2(p)
    return entropy


def calc_hhi(counter):
    total = sum(counter.values())
    if total <= 0:
        return 0.0
    return sum((count / total) ** 2 for count in counter.values())


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
            formatted = {}
            for key in fieldnames:
                value = row.get(key, "")
                if isinstance(value, float):
                    formatted[key] = f"{value:.6f}"
                else:
                    formatted[key] = value
            writer.writerow(formatted)


def load_records(db_key, metadata):
    conn = sqlite3.connect(metadata["db_path"])
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    rows = cursor.execute(
        """
        SELECT id, cipai, title, content, imagery, category, model_name, rhythm_score
        FROM ci_data
        WHERE content IS NOT NULL AND TRIM(content) != ''
        """
    ).fetchall()
    conn.close()

    records = []
    for row in rows:
        records.append(
            {
                "db": db_key,
                "db_label": metadata["label"],
                "prompt_type": metadata["prompt_type"],
                "id": row["id"],
                "cipai": (row["cipai"] or "").strip(),
                "title": (row["title"] or "").strip(),
                "content": row["content"] or "",
                "imagery": parse_json_list(row["imagery"]),
                "category": (row["category"] or "").strip(),
                "model": map_model_name(row["model_name"]),
                "rhythm_score": row["rhythm_score"],
            }
        )
    return records


def build_a1_cipai_distribution(records):
    rows = []
    grouped = defaultdict(list)
    for record in records:
        grouped[record["model"]].append(record)

    for model, model_records in sorted(grouped.items()):
        counter = Counter(record["cipai"] for record in model_records if record["cipai"])
        total = sum(counter.values())
        for rank, (cipai, count) in enumerate(counter.most_common(), start=1):
            rows.append(
                {
                    "db": "a1",
                    "db_label": AI_DATABASES["a1"]["label"],
                    "prompt_type": AI_DATABASES["a1"]["prompt_type"],
                    "model": model,
                    "cipai": cipai,
                    "count": count,
                    "proportion": count / total if total else 0.0,
                    "rank": rank,
                    "total_poems": len(model_records),
                }
            )
    return rows


def build_a1_cipai_summary(records):
    rows = []
    grouped = defaultdict(list)
    for record in records:
        grouped[record["model"]].append(record)

    for model, model_records in sorted(grouped.items()):
        counter = Counter(record["cipai"] for record in model_records if record["cipai"])
        total = sum(counter.values())
        top5 = counter.most_common(5)
        top1_cipai, top1_count = top5[0] if top5 else ("", 0)
        rows.append(
            {
                "db": "a1",
                "db_label": AI_DATABASES["a1"]["label"],
                "prompt_type": AI_DATABASES["a1"]["prompt_type"],
                "model": model,
                "total_poems": len(model_records),
                "distinct_cipai_count": len(counter),
                "top1_cipai": top1_cipai,
                "top1_count": top1_count,
                "top1_ratio": top1_count / total if total else 0.0,
                "top5_cipais": "|".join(f"{cipai}:{count}" for cipai, count in top5),
                "cipai_entropy": calc_entropy(counter),
                "cipai_hhi": calc_hhi(counter),
            }
        )
    return rows


def build_category_distribution_by_db(records):
    rows = []
    grouped = defaultdict(list)
    for record in records:
        grouped[record["db"]].append(record)

    for db_key, db_records in sorted(grouped.items()):
        metadata = AI_DATABASES[db_key]
        filtered = [record for record in db_records if record["category"]]
        counter = Counter(record["category"] for record in filtered)
        total = sum(counter.values())
        for rank, (category, count) in enumerate(counter.most_common(), start=1):
            rows.append(
                {
                    "db": db_key,
                    "db_label": metadata["label"],
                    "prompt_type": metadata["prompt_type"],
                    "category": category,
                    "count": count,
                    "proportion": count / total if total else 0.0,
                    "rank": rank,
                    "total_poems": len(db_records),
                    "categorized_poems": len(filtered),
                    "category_coverage": len(filtered) / len(db_records) if db_records else 0.0,
                }
            )
    return rows


def build_category_distribution_by_db_model(records):
    rows = []
    grouped = defaultdict(list)
    for record in records:
        grouped[(record["db"], record["model"])].append(record)

    for (db_key, model), model_records in sorted(grouped.items()):
        metadata = AI_DATABASES[db_key]
        filtered = [record for record in model_records if record["category"]]
        counter = Counter(record["category"] for record in filtered)
        total = sum(counter.values())
        for rank, (category, count) in enumerate(counter.most_common(), start=1):
            rows.append(
                {
                    "db": db_key,
                    "db_label": metadata["label"],
                    "prompt_type": metadata["prompt_type"],
                    "model": model,
                    "category": category,
                    "count": count,
                    "proportion": count / total if total else 0.0,
                    "rank": rank,
                    "total_poems": len(model_records),
                    "categorized_poems": len(filtered),
                    "category_coverage": len(filtered) / len(model_records) if model_records else 0.0,
                }
            )
    return rows


def build_category_summary_by_db_model(records):
    rows = []
    grouped = defaultdict(list)
    for record in records:
        grouped[(record["db"], record["model"])].append(record)

    for (db_key, model), model_records in sorted(grouped.items()):
        metadata = AI_DATABASES[db_key]
        filtered = [record for record in model_records if record["category"]]
        counter = Counter(record["category"] for record in filtered)
        total = sum(counter.values())
        top1_category, top1_count = counter.most_common(1)[0] if counter else ("", 0)
        rows.append(
            {
                "db": db_key,
                "db_label": metadata["label"],
                "prompt_type": metadata["prompt_type"],
                "model": model,
                "total_poems": len(model_records),
                "categorized_poems": len(filtered),
                "category_coverage": len(filtered) / len(model_records) if model_records else 0.0,
                "distinct_category_count": len(counter),
                "top1_category": top1_category,
                "top1_count": top1_count,
                "top1_ratio": top1_count / total if total else 0.0,
                "top3_categories": "|".join(f"{cat}:{cnt}" for cat, cnt in counter.most_common(3)),
                "category_entropy": calc_entropy(counter),
                "category_hhi": calc_hhi(counter),
            }
        )
    return rows


def build_imagery_top_by_db(records):
    rows = []
    grouped = defaultdict(list)
    for record in records:
        grouped[record["db"]].append(record)

    for db_key, db_records in sorted(grouped.items()):
        metadata = AI_DATABASES[db_key]
        token_counter = Counter()
        poem_counter = Counter()
        imagery_covered_poems = 0
        for record in db_records:
            if record["imagery"]:
                imagery_covered_poems += 1
                token_counter.update(record["imagery"])
                poem_counter.update(set(record["imagery"]))
        total_tokens = sum(token_counter.values())
        for rank, (imagery, count) in enumerate(token_counter.most_common(20), start=1):
            rows.append(
                {
                    "db": db_key,
                    "db_label": metadata["label"],
                    "prompt_type": metadata["prompt_type"],
                    "imagery": imagery,
                    "count": count,
                    "proportion": count / total_tokens if total_tokens else 0.0,
                    "poem_coverage_count": poem_counter[imagery],
                    "poem_coverage_ratio": poem_counter[imagery] / imagery_covered_poems if imagery_covered_poems else 0.0,
                    "rank": rank,
                    "total_poems": len(db_records),
                    "imagery_covered_poems": imagery_covered_poems,
                    "total_imagery_tokens": total_tokens,
                }
            )
    return rows


def build_imagery_top_by_db_model(records):
    rows = []
    grouped = defaultdict(list)
    for record in records:
        grouped[(record["db"], record["model"])].append(record)

    for (db_key, model), model_records in sorted(grouped.items()):
        metadata = AI_DATABASES[db_key]
        token_counter = Counter()
        poem_counter = Counter()
        imagery_covered_poems = 0
        for record in model_records:
            if record["imagery"]:
                imagery_covered_poems += 1
                token_counter.update(record["imagery"])
                poem_counter.update(set(record["imagery"]))
        total_tokens = sum(token_counter.values())
        for rank, (imagery, count) in enumerate(token_counter.most_common(20), start=1):
            rows.append(
                {
                    "db": db_key,
                    "db_label": metadata["label"],
                    "prompt_type": metadata["prompt_type"],
                    "model": model,
                    "imagery": imagery,
                    "count": count,
                    "proportion": count / total_tokens if total_tokens else 0.0,
                    "poem_coverage_count": poem_counter[imagery],
                    "poem_coverage_ratio": poem_counter[imagery] / imagery_covered_poems if imagery_covered_poems else 0.0,
                    "rank": rank,
                    "total_poems": len(model_records),
                    "imagery_covered_poems": imagery_covered_poems,
                    "total_imagery_tokens": total_tokens,
                }
            )
    return rows


def build_imagery_summary_by_db_model(records):
    rows = []
    grouped = defaultdict(list)
    for record in records:
        grouped[(record["db"], record["model"])].append(record)

    for (db_key, model), model_records in sorted(grouped.items()):
        metadata = AI_DATABASES[db_key]
        token_counter = Counter()
        imagery_covered_poems = 0
        imagery_lengths = []
        for record in model_records:
            if record["imagery"]:
                imagery_covered_poems += 1
                imagery_lengths.append(len(record["imagery"]))
                token_counter.update(record["imagery"])
        total_tokens = sum(token_counter.values())
        top10_count = sum(count for _, count in token_counter.most_common(10))
        rows.append(
            {
                "db": db_key,
                "db_label": metadata["label"],
                "prompt_type": metadata["prompt_type"],
                "model": model,
                "total_poems": len(model_records),
                "imagery_covered_poems": imagery_covered_poems,
                "imagery_coverage": imagery_covered_poems / len(model_records) if model_records else 0.0,
                "total_imagery_tokens": total_tokens,
                "distinct_imagery_count": len(token_counter),
                "avg_imagery_per_poem": (sum(imagery_lengths) / len(imagery_lengths)) if imagery_lengths else 0.0,
                "imagery_entropy": calc_entropy(token_counter),
                "imagery_hhi": calc_hhi(token_counter),
                "top10_imagery_ratio": top10_count / total_tokens if total_tokens else 0.0,
                "top10_imageries": "|".join(f"{img}:{cnt}" for img, cnt in token_counter.most_common(10)),
            }
        )
    return rows


def build_imagery_overlap_between_dbs(records):
    rows = []
    grouped = defaultdict(list)
    for record in records:
        grouped[record["db"]].append(record)

    db_profiles = {}
    for db_key, db_records in grouped.items():
        token_counter = Counter()
        poem_counter = Counter()
        for record in db_records:
            if not record["imagery"]:
                continue
            token_counter.update(record["imagery"])
            poem_counter.update(set(record["imagery"]))
        db_profiles[db_key] = {
            "token_counter": token_counter,
            "poem_counter": poem_counter,
            "distinct_set": set(token_counter.keys()),
            "top20_set": {img for img, _ in token_counter.most_common(20)},
            "total_tokens": sum(token_counter.values()),
        }

    for db_a, db_b in combinations(sorted(db_profiles.keys()), 2):
        meta_a = AI_DATABASES[db_a]
        meta_b = AI_DATABASES[db_b]
        profile_a = db_profiles[db_a]
        profile_b = db_profiles[db_b]

        distinct_a = profile_a["distinct_set"]
        distinct_b = profile_b["distinct_set"]
        inter_all = distinct_a & distinct_b
        union_all = distinct_a | distinct_b

        top20_a = profile_a["top20_set"]
        top20_b = profile_b["top20_set"]
        inter_top20 = top20_a & top20_b
        union_top20 = top20_a | top20_b

        shared_poem_coverage = sorted(
            (
                (
                    img,
                    profile_a["poem_counter"][img] + profile_b["poem_counter"][img],
                )
                for img in inter_all
            ),
            key=lambda item: (-item[1], item[0]),
        )

        rows.append(
            {
                "group_a": db_a,
                "group_a_label": meta_a["label"],
                "prompt_type_a": meta_a["prompt_type"],
                "group_b": db_b,
                "group_b_label": meta_b["label"],
                "prompt_type_b": meta_b["prompt_type"],
                "distinct_imagery_count_a": len(distinct_a),
                "distinct_imagery_count_b": len(distinct_b),
                "shared_distinct_imagery_count": len(inter_all),
                "distinct_imagery_jaccard": len(inter_all) / len(union_all) if union_all else 0.0,
                "top20_overlap_count": len(inter_top20),
                "top20_overlap_jaccard": len(inter_top20) / len(union_top20) if union_top20 else 0.0,
                "top20_overlap_ratio_a": len(inter_top20) / len(top20_a) if top20_a else 0.0,
                "top20_overlap_ratio_b": len(inter_top20) / len(top20_b) if top20_b else 0.0,
                "shared_top20_imageries": "|".join(sorted(inter_top20)),
                "shared_distinct_top10": "|".join(img for img, _ in shared_poem_coverage[:10]),
                "total_imagery_tokens_a": profile_a["total_tokens"],
                "total_imagery_tokens_b": profile_b["total_tokens"],
            }
        )

    return rows


def summarize_imagery_group(group_records, scope_records, scope_poem_counter):
    token_counter = Counter()
    group_poem_counter = Counter()
    imagery_lengths = []
    imagery_covered_poems = 0
    for record in group_records:
        if not record["imagery"]:
            continue
        imagery_covered_poems += 1
        imagery_lengths.append(len(record["imagery"]))
        token_counter.update(record["imagery"])
        group_poem_counter.update(set(record["imagery"]))

    total_tokens = sum(token_counter.values())
    top10_count = sum(count for _, count in token_counter.most_common(10))
    scope_poem_count = len(scope_records)

    signature_items = []
    for imagery, count in token_counter.items():
        group_poems = group_poem_counter[imagery]
        group_coverage = group_poems / len(group_records) if group_records else 0.0
        scope_coverage = scope_poem_counter[imagery] / scope_poem_count if scope_poem_count else 0.0
        lift = group_coverage / scope_coverage if scope_coverage else 0.0
        signature_items.append(
            {
                "imagery": imagery,
                "count": count,
                "group_poem_count": group_poems,
                "group_coverage": group_coverage,
                "scope_coverage": scope_coverage,
                "lift_vs_scope": lift,
            }
        )

    signature_items.sort(
        key=lambda item: (
            -item["lift_vs_scope"],
            -item["group_poem_count"],
            -item["count"],
            item["imagery"],
        )
    )

    return {
        "imagery_covered_poems": imagery_covered_poems,
        "imagery_coverage": imagery_covered_poems / len(group_records) if group_records else 0.0,
        "total_imagery_tokens": total_tokens,
        "distinct_imagery_count": len(token_counter),
        "avg_imagery_per_poem": (sum(imagery_lengths) / len(imagery_lengths)) if imagery_lengths else 0.0,
        "imagery_entropy": calc_entropy(token_counter),
        "imagery_hhi": calc_hhi(token_counter),
        "top10_imagery_ratio": top10_count / total_tokens if total_tokens else 0.0,
        "top5_imageries": "|".join(f"{img}:{cnt}" for img, cnt in token_counter.most_common(5)),
        "signature_top5_imageries": "|".join(
            f"{item['imagery']}:{item['lift_vs_scope']:.2f}x"
            for item in signature_items[:5]
        ),
        "top1_signature_imagery": signature_items[0]["imagery"] if signature_items else "",
        "top1_signature_lift": signature_items[0]["lift_vs_scope"] if signature_items else 0.0,
        "token_counter": token_counter,
        "group_poem_counter": group_poem_counter,
    }


def build_imagery_top_by_db_category(records):
    rows = []
    grouped = defaultdict(list)
    db_scope_records = defaultdict(list)
    for record in records:
        db_scope_records[record["db"]].append(record)
        if record["category"] and record["imagery"]:
            grouped[(record["db"], record["category"])].append(record)

    db_scope_poem_counter = {}
    for db_key, scope_records in db_scope_records.items():
        counter = Counter()
        for record in scope_records:
            counter.update(set(record["imagery"]))
        db_scope_poem_counter[db_key] = counter

    for (db_key, category), group_records in sorted(grouped.items()):
        metadata = AI_DATABASES[db_key]
        summary = summarize_imagery_group(
            group_records,
            db_scope_records[db_key],
            db_scope_poem_counter[db_key],
        )
        token_counter = summary["token_counter"]
        group_poem_counter = summary["group_poem_counter"]
        scope_poem_count = len(db_scope_records[db_key])
        for rank, (imagery, count) in enumerate(token_counter.most_common(20), start=1):
            scope_coverage = (
                db_scope_poem_counter[db_key][imagery] / scope_poem_count
                if scope_poem_count
                else 0.0
            )
            group_coverage = (
                group_poem_counter[imagery] / len(group_records)
                if group_records
                else 0.0
            )
            rows.append(
                {
                    "db": db_key,
                    "db_label": metadata["label"],
                    "prompt_type": metadata["prompt_type"],
                    "category": category,
                    "imagery": imagery,
                    "count": count,
                    "proportion": count / summary["total_imagery_tokens"] if summary["total_imagery_tokens"] else 0.0,
                    "poem_coverage_count": group_poem_counter[imagery],
                    "poem_coverage_ratio": group_coverage,
                    "db_poem_coverage_ratio": scope_coverage,
                    "lift_vs_db": group_coverage / scope_coverage if scope_coverage else 0.0,
                    "rank": rank,
                    "category_poem_count": len(group_records),
                    "total_imagery_tokens": summary["total_imagery_tokens"],
                }
            )
    return rows


def build_imagery_top_by_category(records):
    rows = []
    grouped = defaultdict(list)
    for record in records:
        if record["category"] and record["imagery"]:
            grouped[record["category"]].append(record)

    for category, group_records in sorted(grouped.items()):
        token_counter = Counter()
        poem_counter = Counter()
        db_counter = Counter()
        for record in group_records:
            token_counter.update(record["imagery"])
            poem_counter.update(set(record["imagery"]))
            db_counter[record["db"]] += 1
        total_tokens = sum(token_counter.values())
        for rank, (imagery, count) in enumerate(token_counter.most_common(20), start=1):
            rows.append(
                {
                    "category": category,
                    "imagery": imagery,
                    "count": count,
                    "proportion": count / total_tokens if total_tokens else 0.0,
                    "poem_coverage_count": poem_counter[imagery],
                    "poem_coverage_ratio": poem_counter[imagery] / len(group_records) if group_records else 0.0,
                    "rank": rank,
                    "category_poem_count": len(group_records),
                    "total_imagery_tokens": total_tokens,
                    "db_distribution": "|".join(f"{db}:{cnt}" for db, cnt in sorted(db_counter.items())),
                }
            )
    return rows


def build_category_imagery_profile(records):
    rows = []
    grouped = defaultdict(list)
    db_scope_records = defaultdict(list)
    for record in records:
        db_scope_records[record["db"]].append(record)
        if record["category"]:
            grouped[(record["db"], record["category"])].append(record)

    db_scope_poem_counter = {}
    for db_key, scope_records in db_scope_records.items():
        counter = Counter()
        for record in scope_records:
            counter.update(set(record["imagery"]))
        db_scope_poem_counter[db_key] = counter

    for (db_key, category), group_records in sorted(grouped.items()):
        metadata = AI_DATABASES[db_key]
        scope_records = db_scope_records[db_key]
        summary = summarize_imagery_group(
            group_records,
            scope_records,
            db_scope_poem_counter[db_key],
        )
        rows.append(
            {
                "db": db_key,
                "db_label": metadata["label"],
                "prompt_type": metadata["prompt_type"],
                "category": category,
                "category_poem_count": len(group_records),
                "category_ratio_in_db": len(group_records) / len(scope_records) if scope_records else 0.0,
                "imagery_covered_poems": summary["imagery_covered_poems"],
                "imagery_coverage": summary["imagery_coverage"],
                "total_imagery_tokens": summary["total_imagery_tokens"],
                "distinct_imagery_count": summary["distinct_imagery_count"],
                "avg_imagery_per_poem": summary["avg_imagery_per_poem"],
                "imagery_entropy": summary["imagery_entropy"],
                "imagery_hhi": summary["imagery_hhi"],
                "top10_imagery_ratio": summary["top10_imagery_ratio"],
                "top5_imageries": summary["top5_imageries"],
                "signature_top5_imageries": summary["signature_top5_imageries"],
                "top1_signature_imagery": summary["top1_signature_imagery"],
                "top1_signature_lift": summary["top1_signature_lift"],
            }
        )
    return rows


def build_category_imagery_profile_by_model(records):
    rows = []
    grouped = defaultdict(list)
    scope_records_by_db_model = defaultdict(list)
    for record in records:
        scope_records_by_db_model[(record["db"], record["model"])].append(record)
        if record["category"]:
            grouped[(record["db"], record["model"], record["category"])].append(record)

    scope_poem_counters = {}
    for key, scope_records in scope_records_by_db_model.items():
        counter = Counter()
        for record in scope_records:
            counter.update(set(record["imagery"]))
        scope_poem_counters[key] = counter

    for (db_key, model, category), group_records in sorted(grouped.items()):
        metadata = AI_DATABASES[db_key]
        scope_records = scope_records_by_db_model[(db_key, model)]
        summary = summarize_imagery_group(
            group_records,
            scope_records,
            scope_poem_counters[(db_key, model)],
        )
        rows.append(
            {
                "db": db_key,
                "db_label": metadata["label"],
                "prompt_type": metadata["prompt_type"],
                "model": model,
                "category": category,
                "category_poem_count": len(group_records),
                "category_ratio_in_model": len(group_records) / len(scope_records) if scope_records else 0.0,
                "imagery_covered_poems": summary["imagery_covered_poems"],
                "imagery_coverage": summary["imagery_coverage"],
                "total_imagery_tokens": summary["total_imagery_tokens"],
                "distinct_imagery_count": summary["distinct_imagery_count"],
                "avg_imagery_per_poem": summary["avg_imagery_per_poem"],
                "imagery_entropy": summary["imagery_entropy"],
                "imagery_hhi": summary["imagery_hhi"],
                "top10_imagery_ratio": summary["top10_imagery_ratio"],
                "top5_imageries": summary["top5_imageries"],
                "signature_top5_imageries": summary["signature_top5_imageries"],
                "top1_signature_imagery": summary["top1_signature_imagery"],
                "top1_signature_lift": summary["top1_signature_lift"],
            }
        )
    return rows


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    all_records = []
    for db_key, metadata in AI_DATABASES.items():
        records = load_records(db_key, metadata)
        print(
            f"[{db_key}] {metadata['label']} | prompt={metadata['prompt_type']} | "
            f"records={len(records)}"
        )
        all_records.extend(records)

    a1_records = [record for record in all_records if record["db"] == "a1"]

    outputs = {
        "a1_model_cipai_distribution.csv": build_a1_cipai_distribution(a1_records),
        "a1_model_cipai_summary.csv": build_a1_cipai_summary(a1_records),
        "category_distribution_by_db.csv": build_category_distribution_by_db(all_records),
        "category_distribution_by_db_model.csv": build_category_distribution_by_db_model(all_records),
        "category_summary_by_db_model.csv": build_category_summary_by_db_model(all_records),
        "imagery_top_by_db.csv": build_imagery_top_by_db(all_records),
        "imagery_top_by_db_model.csv": build_imagery_top_by_db_model(all_records),
        "imagery_summary_by_db_model.csv": build_imagery_summary_by_db_model(all_records),
        "imagery_overlap_between_dbs.csv": build_imagery_overlap_between_dbs(all_records),
        "imagery_top_by_db_category.csv": build_imagery_top_by_db_category(all_records),
        "imagery_top_by_category.csv": build_imagery_top_by_category(all_records),
        "category_imagery_profile.csv": build_category_imagery_profile(all_records),
        "category_imagery_profile_by_model.csv": build_category_imagery_profile_by_model(all_records),
    }

    for filename, rows in outputs.items():
        path = OUTPUT_DIR / filename
        write_csv(path, rows)
        print(f"输出: {path} | rows={len(rows)}")


if __name__ == "__main__":
    main()
