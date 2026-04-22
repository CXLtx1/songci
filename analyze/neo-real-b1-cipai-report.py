import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


DEFAULT_INPUT_DIR = Path("result/neo-real-analysis")
DEFAULT_OUTPUT_DIR = Path("result/neo-real-analysis")
TARGET_DB_KEY = "b1"


def parse_args():
    parser = argparse.ArgumentParser(
        description="基于 neo-real-analysis 输出，生成 b1 分词牌真实来源相似性汇总。"
    )
    parser.add_argument(
        "--input-dir",
        default=str(DEFAULT_INPUT_DIR),
        help="neo-real-analysis 结果目录。",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="汇总输出目录。",
    )
    parser.add_argument(
        "--db-key",
        default=TARGET_DB_KEY,
        help="要汇总的数据库代号，默认 b1。",
    )
    parser.add_argument(
        "--top-n-sources",
        type=int,
        default=5,
        help="每个词牌保留的高频来源数量。",
    )
    return parser.parse_args()


def ensure_dir(path):
    Path(path).mkdir(parents=True, exist_ok=True)


def read_csv_rows(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as file:
        yield from csv.DictReader(file)


def to_float(value):
    if value in ("", None):
        return 0.0
    return float(value)


def to_int(value):
    if value in ("", None):
        return 0
    return int(float(value))


def compact_json(data):
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def load_baseline_maps(input_dir):
    whole_map = {}
    sentence_map = {}

    for row in read_csv_rows(Path(input_dir) / "reference_baseline_whole.csv"):
        whole_map[(row["cipai"], row["metric_type"])] = row

    for row in read_csv_rows(Path(input_dir) / "reference_baseline_sentence.csv"):
        sentence_map[(row["cipai"], row["length_bucket"], row["metric_type"])] = row

    return whole_map, sentence_map


def aggregate_profile_rows(input_dir, db_key):
    rows_by_cipai = defaultdict(list)
    for row in read_csv_rows(Path(input_dir) / "ai_poem_source_profile.csv"):
        if row["db_key"] != db_key:
            continue
        row["sentence_count"] = to_int(row["sentence_count"])
        row["whole_sem_top1_score"] = to_float(row["whole_sem_top1_score"])
        row["whole_sem_percentile"] = to_float(row["whole_sem_percentile"])
        row["whole_lex_top1_score"] = to_float(row["whole_lex_top1_score"])
        row["whole_lex_percentile"] = to_float(row["whole_lex_percentile"])
        row["sem_dominant_source_coverage"] = to_float(row["sem_dominant_source_coverage"])
        row["lex_dominant_source_coverage"] = to_float(row["lex_dominant_source_coverage"])
        row["distinct_sem_source_poems"] = to_int(row["distinct_sem_source_poems"])
        row["distinct_lex_source_poems"] = to_int(row["distinct_lex_source_poems"])
        row["max_consecutive_sem_same_source"] = to_int(row["max_consecutive_sem_same_source"])
        row["max_consecutive_lex_same_source"] = to_int(row["max_consecutive_lex_same_source"])
        row["same_source_sentence_count"] = to_int(row["same_source_sentence_count"])
        row["max_sentence_sem_score"] = to_float(row["max_sentence_sem_score"])
        row["max_sentence_lex_score"] = to_float(row["max_sentence_lex_score"])
        rows_by_cipai[row["cipai"]].append(row)
    return rows_by_cipai


def aggregate_whole_alignment_rows(input_dir, db_key, top_n_sources):
    stats = defaultdict(
        lambda: {
            "semantic_same_cipai_top1": 0,
            "semantic_total_top1": 0,
            "lexical_same_cipai_top1": 0,
            "lexical_total_top1": 0,
            "semantic_source_cipai_counter": Counter(),
            "lexical_source_cipai_counter": Counter(),
            "semantic_source_title_counter": Counter(),
            "lexical_source_title_counter": Counter(),
        }
    )

    for row in read_csv_rows(Path(input_dir) / "ai_whole_alignment_topk.csv"):
        if row["db_key"] != db_key or row["rank"] != "1":
            continue
        cipai = row["ai_cipai"]
        bucket = stats[cipai]
        metric_type = row["metric_type"]
        same_cipai = int(row["ai_cipai"] == row["source_cipai"])
        title_key = f"{row['source_cipai']}::{row['source_title']}"

        if metric_type == "semantic":
            bucket["semantic_total_top1"] += 1
            bucket["semantic_same_cipai_top1"] += same_cipai
            bucket["semantic_source_cipai_counter"][row["source_cipai"]] += 1
            bucket["semantic_source_title_counter"][title_key] += 1
        elif metric_type == "lexical":
            bucket["lexical_total_top1"] += 1
            bucket["lexical_same_cipai_top1"] += same_cipai
            bucket["lexical_source_cipai_counter"][row["source_cipai"]] += 1
            bucket["lexical_source_title_counter"][title_key] += 1

    summary_rows = {}
    for cipai, bucket in stats.items():
        summary_rows[cipai] = {
            "semantic_same_cipai_top1_ratio": (
                bucket["semantic_same_cipai_top1"] / bucket["semantic_total_top1"]
                if bucket["semantic_total_top1"]
                else 0.0
            ),
            "lexical_same_cipai_top1_ratio": (
                bucket["lexical_same_cipai_top1"] / bucket["lexical_total_top1"]
                if bucket["lexical_total_top1"]
                else 0.0
            ),
            "semantic_top_source_cipais_json": compact_json(
                bucket["semantic_source_cipai_counter"].most_common(top_n_sources)
            ),
            "lexical_top_source_cipais_json": compact_json(
                bucket["lexical_source_cipai_counter"].most_common(top_n_sources)
            ),
            "semantic_top_source_titles_json": compact_json(
                bucket["semantic_source_title_counter"].most_common(top_n_sources)
            ),
            "lexical_top_source_titles_json": compact_json(
                bucket["lexical_source_title_counter"].most_common(top_n_sources)
            ),
        }
    return summary_rows


def aggregate_sentence_rows(input_dir, db_key, top_n_sources):
    stats = defaultdict(
        lambda: {
            "sentence_count": 0,
            "sem_top1_score_sum": 0.0,
            "lex_top1_score_sum": 0.0,
            "sem_top1_percentile_sum": 0.0,
            "lex_top1_percentile_sum": 0.0,
            "sem_p95_count": 0,
            "lex_p95_count": 0,
            "sem_p99_count": 0,
            "lex_p99_count": 0,
            "exact_lex_count": 0,
            "length_bucket_counter": Counter(),
            "sem_source_poem_counter": Counter(),
            "lex_source_poem_counter": Counter(),
            "sem_source_title_counter": Counter(),
            "lex_source_title_counter": Counter(),
        }
    )

    for row in read_csv_rows(Path(input_dir) / "ai_sentence_alignment_details.csv"):
        if row["db_key"] != db_key:
            continue
        cipai = row["cipai"]
        bucket = stats[cipai]
        sem_score = to_float(row["sem_top1_score"])
        lex_score = to_float(row["lex_top1_score"])
        sem_pct = to_float(row["sem_top1_percentile"])
        lex_pct = to_float(row["lex_top1_percentile"])

        bucket["sentence_count"] += 1
        bucket["sem_top1_score_sum"] += sem_score
        bucket["lex_top1_score_sum"] += lex_score
        bucket["sem_top1_percentile_sum"] += sem_pct
        bucket["lex_top1_percentile_sum"] += lex_pct
        bucket["sem_p95_count"] += int(sem_pct >= 0.95)
        bucket["lex_p95_count"] += int(lex_pct >= 0.95)
        bucket["sem_p99_count"] += int(sem_pct >= 0.99)
        bucket["lex_p99_count"] += int(lex_pct >= 0.99)
        bucket["exact_lex_count"] += int(lex_score >= 0.999999)
        bucket["length_bucket_counter"][row["sentence_length_bucket"]] += 1

        if row["sem_top1_source_poem_id"]:
            bucket["sem_source_poem_counter"][row["sem_top1_source_poem_id"]] += 1
            bucket["sem_source_title_counter"][
                f"{row['sem_top1_source_cipai']}::{row['sem_top1_source_title']}"
            ] += 1
        if row["lex_top1_source_poem_id"]:
            bucket["lex_source_poem_counter"][row["lex_top1_source_poem_id"]] += 1
            bucket["lex_source_title_counter"][
                f"{row['lex_top1_source_cipai']}::{row['lex_top1_source_title']}"
            ] += 1

    summary_rows = {}
    for cipai, bucket in stats.items():
        sentence_count = bucket["sentence_count"] or 1
        summary_rows[cipai] = {
            "sentence_count": bucket["sentence_count"],
            "avg_sentence_sem_top1_score": bucket["sem_top1_score_sum"] / sentence_count,
            "avg_sentence_lex_top1_score": bucket["lex_top1_score_sum"] / sentence_count,
            "avg_sentence_sem_top1_percentile": bucket["sem_top1_percentile_sum"] / sentence_count,
            "avg_sentence_lex_top1_percentile": bucket["lex_top1_percentile_sum"] / sentence_count,
            "sentence_sem_p95_ratio": bucket["sem_p95_count"] / sentence_count,
            "sentence_lex_p95_ratio": bucket["lex_p95_count"] / sentence_count,
            "sentence_sem_p99_ratio": bucket["sem_p99_count"] / sentence_count,
            "sentence_lex_p99_ratio": bucket["lex_p99_count"] / sentence_count,
            "sentence_exact_lex_ratio": bucket["exact_lex_count"] / sentence_count,
            "sentence_length_bucket_distribution_json": compact_json(
                bucket["length_bucket_counter"].most_common()
            ),
            "sentence_sem_top_source_titles_json": compact_json(
                bucket["sem_source_title_counter"].most_common(top_n_sources)
            ),
            "sentence_lex_top_source_titles_json": compact_json(
                bucket["lex_source_title_counter"].most_common(top_n_sources)
            ),
        }
    return summary_rows


def safe_baseline_value(baseline_map, key, field):
    row = baseline_map.get(key)
    if not row:
        return ""
    return row.get(field, "")


def build_summary_rows(
    profile_rows_by_cipai,
    whole_baseline_map,
    sentence_baseline_map,
    whole_alignment_summary,
    sentence_summary,
):
    result_rows = []
    for cipai, items in sorted(profile_rows_by_cipai.items()):
        poem_count = len(items)
        sentence_count = sum(item["sentence_count"] for item in items)
        whole_sem_mean = sum(item["whole_sem_top1_score"] for item in items) / poem_count
        whole_lex_mean = sum(item["whole_lex_top1_score"] for item in items) / poem_count
        whole_sem_pct_mean = sum(item["whole_sem_percentile"] for item in items) / poem_count
        whole_lex_pct_mean = sum(item["whole_lex_percentile"] for item in items) / poem_count
        sem_cov_mean = sum(item["sem_dominant_source_coverage"] for item in items) / poem_count
        lex_cov_mean = sum(item["lex_dominant_source_coverage"] for item in items) / poem_count
        same_source_sentence_mean = sum(item["same_source_sentence_count"] for item in items) / poem_count
        sem_dom_ge_02 = sum(item["sem_dominant_source_coverage"] >= 0.2 for item in items) / poem_count
        lex_dom_ge_02 = sum(item["lex_dominant_source_coverage"] >= 0.2 for item in items) / poem_count
        lex_p95_cov_02 = sum(
            item["whole_lex_percentile"] >= 0.95 and item["lex_dominant_source_coverage"] >= 0.2
            for item in items
        ) / poem_count
        sem_p95_cov_02 = sum(
            item["whole_sem_percentile"] >= 0.95 and item["sem_dominant_source_coverage"] >= 0.2
            for item in items
        ) / poem_count

        whole_alignment = whole_alignment_summary.get(cipai, {})
        sentence_stats = sentence_summary.get(cipai, {})

        result_rows.append(
            {
                "db_key": TARGET_DB_KEY,
                "cipai": cipai,
                "poem_count": poem_count,
                "sentence_count": sentence_count,
                "avg_whole_sem_top1_score": whole_sem_mean,
                "avg_whole_lex_top1_score": whole_lex_mean,
                "avg_whole_sem_top1_percentile": whole_sem_pct_mean,
                "avg_whole_lex_top1_percentile": whole_lex_pct_mean,
                "avg_sem_dominant_source_coverage": sem_cov_mean,
                "avg_lex_dominant_source_coverage": lex_cov_mean,
                "avg_same_source_sentence_count": same_source_sentence_mean,
                "share_sem_dominant_coverage_ge_0_2": sem_dom_ge_02,
                "share_lex_dominant_coverage_ge_0_2": lex_dom_ge_02,
                "share_whole_sem_p95_and_sem_cov_ge_0_2": sem_p95_cov_02,
                "share_whole_lex_p95_and_lex_cov_ge_0_2": lex_p95_cov_02,
                "semantic_same_cipai_top1_ratio": whole_alignment.get(
                    "semantic_same_cipai_top1_ratio",
                    0.0,
                ),
                "lexical_same_cipai_top1_ratio": whole_alignment.get(
                    "lexical_same_cipai_top1_ratio",
                    0.0,
                ),
                "avg_sentence_sem_top1_score": sentence_stats.get(
                    "avg_sentence_sem_top1_score",
                    0.0,
                ),
                "avg_sentence_lex_top1_score": sentence_stats.get(
                    "avg_sentence_lex_top1_score",
                    0.0,
                ),
                "avg_sentence_sem_top1_percentile": sentence_stats.get(
                    "avg_sentence_sem_top1_percentile",
                    0.0,
                ),
                "avg_sentence_lex_top1_percentile": sentence_stats.get(
                    "avg_sentence_lex_top1_percentile",
                    0.0,
                ),
                "sentence_sem_p95_ratio": sentence_stats.get("sentence_sem_p95_ratio", 0.0),
                "sentence_lex_p95_ratio": sentence_stats.get("sentence_lex_p95_ratio", 0.0),
                "sentence_sem_p99_ratio": sentence_stats.get("sentence_sem_p99_ratio", 0.0),
                "sentence_lex_p99_ratio": sentence_stats.get("sentence_lex_p99_ratio", 0.0),
                "sentence_exact_lex_ratio": sentence_stats.get("sentence_exact_lex_ratio", 0.0),
                "baseline_whole_sem_mean": safe_baseline_value(
                    whole_baseline_map,
                    (cipai, "semantic"),
                    "mean",
                ),
                "baseline_whole_sem_p95": safe_baseline_value(
                    whole_baseline_map,
                    (cipai, "semantic"),
                    "p95",
                ),
                "baseline_whole_lex_mean": safe_baseline_value(
                    whole_baseline_map,
                    (cipai, "lexical"),
                    "mean",
                ),
                "baseline_whole_lex_p95": safe_baseline_value(
                    whole_baseline_map,
                    (cipai, "lexical"),
                    "p95",
                ),
                "semantic_top_source_cipais_json": whole_alignment.get(
                    "semantic_top_source_cipais_json",
                    "[]",
                ),
                "lexical_top_source_cipais_json": whole_alignment.get(
                    "lexical_top_source_cipais_json",
                    "[]",
                ),
                "semantic_top_source_titles_json": whole_alignment.get(
                    "semantic_top_source_titles_json",
                    "[]",
                ),
                "lexical_top_source_titles_json": whole_alignment.get(
                    "lexical_top_source_titles_json",
                    "[]",
                ),
                "sentence_length_bucket_distribution_json": sentence_stats.get(
                    "sentence_length_bucket_distribution_json",
                    "[]",
                ),
                "sentence_sem_top_source_titles_json": sentence_stats.get(
                    "sentence_sem_top_source_titles_json",
                    "[]",
                ),
                "sentence_lex_top_source_titles_json": sentence_stats.get(
                    "sentence_lex_top_source_titles_json",
                    "[]",
                ),
            }
        )

    result_rows.sort(key=lambda row: row["avg_whole_lex_top1_percentile"], reverse=True)
    return result_rows


def write_csv(path, rows, fieldnames):
    ensure_dir(Path(path).parent)
    with open(path, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(path, rows, db_key):
    lines = []
    lines.append(f"# {db_key} 分词牌真实来源相似性补充报告")
    lines.append("")
    lines.append(
        "本报告基于 `neo-real-analysis` 已生成结果做后处理，不重新计算嵌入，"
        "只汇总 `b1` 数据库在各词牌下与真实宋词的整首级和句级相似情况。"
    )
    lines.append("")
    lines.append("## 总览")
    lines.append("")
    for row in rows:
        lines.append(
            f"- `{row['cipai']}`："
            f"整首语义分位均值 `{float(row['avg_whole_sem_top1_percentile']):.4f}`，"
            f"整首字面分位均值 `{float(row['avg_whole_lex_top1_percentile']):.4f}`，"
            f"句级字面 P95 比例 `{float(row['sentence_lex_p95_ratio']):.4f}`，"
            f"字面 Top1 同词牌比例 `{float(row['lexical_same_cipai_top1_ratio']):.4f}`。"
        )
    lines.append("")
    lines.append("## 详细表")
    lines.append("")
    lines.append(
        "| 词牌 | 作品数 | 整首语义分位均值 | 整首字面分位均值 | 句级语义分位均值 | 句级字面分位均值 | 字面 Top1 同词牌比例 | 句级字面 P95 比例 |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for row in rows:
        lines.append(
            f"| {row['cipai']} | {row['poem_count']} | "
            f"{float(row['avg_whole_sem_top1_percentile']):.4f} | "
            f"{float(row['avg_whole_lex_top1_percentile']):.4f} | "
            f"{float(row['avg_sentence_sem_top1_percentile']):.4f} | "
            f"{float(row['avg_sentence_lex_top1_percentile']):.4f} | "
            f"{float(row['lexical_same_cipai_top1_ratio']):.4f} | "
            f"{float(row['sentence_lex_p95_ratio']):.4f} |"
        )
    lines.append("")
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def main():
    args = parse_args()
    ensure_dir(args.output_dir)

    whole_baseline_map, sentence_baseline_map = load_baseline_maps(args.input_dir)
    profile_rows_by_cipai = aggregate_profile_rows(args.input_dir, args.db_key)
    whole_alignment_summary = aggregate_whole_alignment_rows(
        args.input_dir,
        args.db_key,
        args.top_n_sources,
    )
    sentence_summary = aggregate_sentence_rows(
        args.input_dir,
        args.db_key,
        args.top_n_sources,
    )

    summary_rows = build_summary_rows(
        profile_rows_by_cipai,
        whole_baseline_map,
        sentence_baseline_map,
        whole_alignment_summary,
        sentence_summary,
    )

    csv_path = Path(args.output_dir) / f"{args.db_key}_cipai_similarity_summary.csv"
    md_path = Path(args.output_dir) / f"{args.db_key}_cipai_similarity_report.md"

    write_csv(
        csv_path,
        summary_rows,
        [
            "db_key",
            "cipai",
            "poem_count",
            "sentence_count",
            "avg_whole_sem_top1_score",
            "avg_whole_lex_top1_score",
            "avg_whole_sem_top1_percentile",
            "avg_whole_lex_top1_percentile",
            "avg_sem_dominant_source_coverage",
            "avg_lex_dominant_source_coverage",
            "avg_same_source_sentence_count",
            "share_sem_dominant_coverage_ge_0_2",
            "share_lex_dominant_coverage_ge_0_2",
            "share_whole_sem_p95_and_sem_cov_ge_0_2",
            "share_whole_lex_p95_and_lex_cov_ge_0_2",
            "semantic_same_cipai_top1_ratio",
            "lexical_same_cipai_top1_ratio",
            "avg_sentence_sem_top1_score",
            "avg_sentence_lex_top1_score",
            "avg_sentence_sem_top1_percentile",
            "avg_sentence_lex_top1_percentile",
            "sentence_sem_p95_ratio",
            "sentence_lex_p95_ratio",
            "sentence_sem_p99_ratio",
            "sentence_lex_p99_ratio",
            "sentence_exact_lex_ratio",
            "baseline_whole_sem_mean",
            "baseline_whole_sem_p95",
            "baseline_whole_lex_mean",
            "baseline_whole_lex_p95",
            "semantic_top_source_cipais_json",
            "lexical_top_source_cipais_json",
            "semantic_top_source_titles_json",
            "lexical_top_source_titles_json",
            "sentence_length_bucket_distribution_json",
            "sentence_sem_top_source_titles_json",
            "sentence_lex_top_source_titles_json",
        ],
    )
    write_markdown(md_path, summary_rows, args.db_key)

    print(f"Done. CSV: {csv_path}")
    print(f"Done. MD : {md_path}")


if __name__ == "__main__":
    main()
