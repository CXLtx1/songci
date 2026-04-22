import csv
import json
import math
import sqlite3
from collections import Counter, defaultdict
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

OUTPUT_DIR = Path("result/rhythm-stats")

ISSUE_TYPES = [
    "length_mismatch",
    "tone_expected_flat",
    "tone_expected_oblique",
    "rhyme_mismatch",
    "unknown_char",
    "variant_autocorrect",
    "other",
]

ISSUE_LABELS = {
    "length_mismatch": "字数不符",
    "tone_expected_flat": "应平实仄",
    "tone_expected_oblique": "应仄实平",
    "rhyme_mismatch": "出韵/押韵问题",
    "unknown_char": "未收录字警告",
    "variant_autocorrect": "词牌变体智能纠偏",
    "other": "其他",
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


def safe_mean(values):
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def percentile(values, q):
    values = sorted(values)
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    idx = (len(values) - 1) * q
    lo = math.floor(idx)
    hi = math.ceil(idx)
    if lo == hi:
        return float(values[lo])
    frac = idx - lo
    return float(values[lo] * (1 - frac) + values[hi] * frac)


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


def parse_error_list(raw_value):
    if not raw_value:
        return []
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item).strip() for item in parsed if str(item).strip()]


def classify_issue(message):
    if "字数不符" in message:
        return "length_mismatch"
    if "智能纠偏" in message:
        return "variant_autocorrect"
    if "韵脚" in message:
        return "rhyme_mismatch"
    if "须填平声字" in message:
        return "tone_expected_flat"
    if "须填仄声字" in message:
        return "tone_expected_oblique"
    if "出韵" in message or "押" in message:
        return "rhyme_mismatch"
    if "未收录" in message:
        return "unknown_char"
    return "other"


def build_record(db_key, metadata, row):
    errors = parse_error_list(row["rhythm_errors"])
    issue_counts = Counter(classify_issue(msg) for msg in errors)
    substantive_issue_count = sum(
        count
        for issue_type, count in issue_counts.items()
        if issue_type != "variant_autocorrect"
    )
    score = float(row["rhythm_score"] or 0.0)
    return {
        "db": db_key,
        "db_label": metadata["label"],
        "prompt_type": metadata["prompt_type"],
        "id": row["id"],
        "cipai": (row["cipai"] or "").strip(),
        "title": (row["title"] or "").strip(),
        "model": map_model_name(row["model_name"]),
        "rhythm_score": score,
        "errors": errors,
        "issue_counts": issue_counts,
        "raw_issue_count": len(errors),
        "substantive_issue_count": substantive_issue_count,
        "is_perfect_100": score >= 99.999,
        "is_high_quality": score >= 80.0,
        "is_mid_quality": 60.0 <= score < 80.0,
        "is_low_quality": 0.0 < score < 60.0,
        "is_zero": score <= 0.0,
        "is_issue_free": substantive_issue_count == 0,
    }


def load_records():
    all_records = []
    for db_key, metadata in AI_DATABASES.items():
        conn = sqlite3.connect(metadata["db_path"])
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        rows = cursor.execute(
            """
            SELECT id, cipai, title, model_name, rhythm_score, rhythm_errors
            FROM ci_data
            WHERE content IS NOT NULL AND TRIM(content) != ''
            """
        ).fetchall()
        conn.close()

        db_records = [build_record(db_key, metadata, row) for row in rows]
        all_records.extend(db_records)
        print(f"[{db_key}] {metadata['label']} | prompt={metadata['prompt_type']} | records={len(db_records)}")
    return all_records


def aggregate_records(records):
    scores = [record["rhythm_score"] for record in records]
    total = len(records)
    issue_poem_counter = Counter()
    issue_count_counter = Counter()
    for record in records:
        for issue_type in ISSUE_TYPES:
            count = record["issue_counts"].get(issue_type, 0)
            issue_count_counter[issue_type] += count
            if count > 0:
                issue_poem_counter[issue_type] += 1

    row = {
        "total_poems": total,
        "avg_rhythm_score": safe_mean(scores),
        "median_rhythm_score": percentile(scores, 0.5),
        "p25_rhythm_score": percentile(scores, 0.25),
        "p75_rhythm_score": percentile(scores, 0.75),
        "perfect_100_ratio": safe_mean(record["is_perfect_100"] for record in records),
        "high_quality_ratio": safe_mean(record["is_high_quality"] for record in records),
        "mid_quality_ratio": safe_mean(record["is_mid_quality"] for record in records),
        "low_quality_ratio": safe_mean(record["is_low_quality"] for record in records),
        "zero_score_ratio": safe_mean(record["is_zero"] for record in records),
        "issue_free_ratio": safe_mean(record["is_issue_free"] for record in records),
        "avg_raw_issue_count": safe_mean(record["raw_issue_count"] for record in records),
        "avg_substantive_issue_count": safe_mean(
            record["substantive_issue_count"] for record in records
        ),
    }

    for issue_type in ISSUE_TYPES:
        row[f"{issue_type}_poem_ratio"] = issue_poem_counter[issue_type] / total if total else 0.0
        row[f"{issue_type}_avg_count"] = issue_count_counter[issue_type] / total if total else 0.0

    return row


def build_summary_by_db(records):
    rows = []
    grouped = defaultdict(list)
    for record in records:
        grouped[record["db"]].append(record)

    for db_key, group_records in sorted(grouped.items()):
        meta = AI_DATABASES[db_key]
        row = {
            "db": db_key,
            "db_label": meta["label"],
            "prompt_type": meta["prompt_type"],
        }
        row.update(aggregate_records(group_records))
        rows.append(row)
    return rows


def build_summary_by_db_model(records):
    rows = []
    grouped = defaultdict(list)
    for record in records:
        grouped[(record["db"], record["model"])].append(record)

    for (db_key, model), group_records in sorted(grouped.items()):
        meta = AI_DATABASES[db_key]
        row = {
            "db": db_key,
            "db_label": meta["label"],
            "prompt_type": meta["prompt_type"],
            "model": model,
        }
        row.update(aggregate_records(group_records))
        rows.append(row)
    return rows


def build_summary_by_db_model_cipai(records, min_poems=8):
    rows = []
    grouped = defaultdict(list)
    for record in records:
        grouped[(record["db"], record["model"], record["cipai"])].append(record)

    for (db_key, model, cipai), group_records in sorted(grouped.items()):
        if len(group_records) < min_poems:
            continue
        meta = AI_DATABASES[db_key]
        row = {
            "db": db_key,
            "db_label": meta["label"],
            "prompt_type": meta["prompt_type"],
            "model": model,
            "cipai": cipai,
        }
        row.update(aggregate_records(group_records))
        rows.append(row)
    return rows


def build_issue_breakdown_by_db(records):
    rows = []
    grouped = defaultdict(list)
    for record in records:
        grouped[record["db"]].append(record)

    for db_key, group_records in sorted(grouped.items()):
        meta = AI_DATABASES[db_key]
        total = len(group_records)
        issue_count_counter = Counter()
        issue_poem_counter = Counter()
        for record in group_records:
            for issue_type in ISSUE_TYPES:
                count = record["issue_counts"].get(issue_type, 0)
                issue_count_counter[issue_type] += count
                if count > 0:
                    issue_poem_counter[issue_type] += 1
        for issue_type in ISSUE_TYPES:
            rows.append(
                {
                    "db": db_key,
                    "db_label": meta["label"],
                    "prompt_type": meta["prompt_type"],
                    "issue_type": issue_type,
                    "issue_label": ISSUE_LABELS[issue_type],
                    "poem_count": issue_poem_counter[issue_type],
                    "poem_ratio": issue_poem_counter[issue_type] / total if total else 0.0,
                    "issue_count": issue_count_counter[issue_type],
                    "avg_count_per_poem": issue_count_counter[issue_type] / total if total else 0.0,
                }
            )
    return rows


def build_issue_breakdown_by_db_model(records):
    rows = []
    grouped = defaultdict(list)
    for record in records:
        grouped[(record["db"], record["model"])].append(record)

    for (db_key, model), group_records in sorted(grouped.items()):
        meta = AI_DATABASES[db_key]
        total = len(group_records)
        issue_count_counter = Counter()
        issue_poem_counter = Counter()
        for record in group_records:
            for issue_type in ISSUE_TYPES:
                count = record["issue_counts"].get(issue_type, 0)
                issue_count_counter[issue_type] += count
                if count > 0:
                    issue_poem_counter[issue_type] += 1
        for issue_type in ISSUE_TYPES:
            rows.append(
                {
                    "db": db_key,
                    "db_label": meta["label"],
                    "prompt_type": meta["prompt_type"],
                    "model": model,
                    "issue_type": issue_type,
                    "issue_label": ISSUE_LABELS[issue_type],
                    "poem_count": issue_poem_counter[issue_type],
                    "poem_ratio": issue_poem_counter[issue_type] / total if total else 0.0,
                    "issue_count": issue_count_counter[issue_type],
                    "avg_count_per_poem": issue_count_counter[issue_type] / total if total else 0.0,
                }
            )
    return rows


def build_common_error_messages(records, topn=15):
    rows = []
    grouped = defaultdict(Counter)
    for record in records:
        grouped[(record["db"], record["model"])].update(record["errors"])

    for (db_key, model), counter in sorted(grouped.items()):
        meta = AI_DATABASES[db_key]
        for rank, (message, count) in enumerate(counter.most_common(topn), start=1):
            rows.append(
                {
                    "db": db_key,
                    "db_label": meta["label"],
                    "prompt_type": meta["prompt_type"],
                    "model": model,
                    "rank": rank,
                    "count": count,
                    "issue_type": classify_issue(message),
                    "issue_label": ISSUE_LABELS[classify_issue(message)],
                    "message": message,
                }
            )
    return rows


def build_overall_model_summary(records):
    rows = []
    grouped = defaultdict(list)
    for record in records:
        grouped[record["model"]].append(record)

    for model, group_records in sorted(grouped.items()):
        row = {"model": model}
        row.update(aggregate_records(group_records))
        db_counter = Counter(record["db"] for record in group_records)
        row["db_coverage"] = len(db_counter)
        row["dbs"] = "|".join(sorted(db_counter.keys()))
        rows.append(row)
    return rows


def build_score_buckets_by_db_model(records):
    rows = []
    grouped = defaultdict(list)
    for record in records:
        grouped[(record["db"], record["model"])].append(record)

    for (db_key, model), group_records in sorted(grouped.items()):
        meta = AI_DATABASES[db_key]
        total = len(group_records)
        buckets = {
            "100": sum(record["is_perfect_100"] for record in group_records),
            "80_99": sum(record["is_high_quality"] and not record["is_perfect_100"] for record in group_records),
            "60_79": sum(record["is_mid_quality"] for record in group_records),
            "1_59": sum(record["is_low_quality"] for record in group_records),
            "0": sum(record["is_zero"] for record in group_records),
        }
        for bucket, count in buckets.items():
            rows.append(
                {
                    "db": db_key,
                    "db_label": meta["label"],
                    "prompt_type": meta["prompt_type"],
                    "model": model,
                    "bucket": bucket,
                    "count": count,
                    "ratio": count / total if total else 0.0,
                }
            )
    return rows


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    records = load_records()

    outputs = {
        "rhythm_summary_by_db.csv": build_summary_by_db(records),
        "rhythm_summary_by_db_model.csv": build_summary_by_db_model(records),
        "rhythm_summary_by_db_model_cipai.csv": build_summary_by_db_model_cipai(records),
        "rhythm_issue_breakdown_by_db.csv": build_issue_breakdown_by_db(records),
        "rhythm_issue_breakdown_by_db_model.csv": build_issue_breakdown_by_db_model(records),
        "rhythm_common_error_messages.csv": build_common_error_messages(records),
        "rhythm_model_overall_summary.csv": build_overall_model_summary(records),
        "rhythm_score_buckets_by_db_model.csv": build_score_buckets_by_db_model(records),
    }

    for filename, rows in outputs.items():
        path = OUTPUT_DIR / filename
        write_csv(path, rows)
        print(f"输出: {path} | rows={len(rows)}")


if __name__ == "__main__":
    main()
