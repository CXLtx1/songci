import csv
from collections import defaultdict
from pathlib import Path


INPUT_DIR = Path("result/neo-analysis")
OUTPUT_DIR = INPUT_DIR

CORE_MODELS = [
    "doubao-seed-2.0-pro",
    "deepseek-3.2-thinking",
    "qwen3.6-plus",
]
MAIN_DBS = ["b1", "b2", "b3", "c1", "c2"]
METRIC_KEYS = [
    "mihi_full",
    "core_mihi",
    "whole_score",
    "sent_score",
    "imagery_score",
    "excess_core_homogeneity",
]


def read_csv(path):
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


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


def to_float(row, key):
    raw = row.get(key, "")
    return float(raw) if raw not in ("", None) else 0.0


def rank_rows(rows, metric_key):
    ordered = sorted(rows, key=lambda item: (-to_float(item, metric_key), item["model"]))
    rank_map = {}
    for index, row in enumerate(ordered, start=1):
        rank_map[row["model"]] = index
    return rank_map


def pick_axis(delta_whole, delta_sent, delta_imagery, by_abs=False):
    axes = {
        "whole": delta_whole,
        "sent": delta_sent,
        "imagery": delta_imagery,
    }
    if by_abs:
        return max(axes.items(), key=lambda item: (abs(item[1]), item[0]))[0]
    return max(axes.items(), key=lambda item: (item[1], item[0]))[0]


def build_model_condition_profile(summary_rows):
    rows = []
    filtered = [
        row
        for row in summary_rows
        if row.get("status") == "main" and row.get("model") in CORE_MODELS
    ]
    grouped = defaultdict(list)
    for row in filtered:
        grouped[row["db"]].append(row)

    for db_key, db_rows in sorted(grouped.items()):
        rank_maps = {metric: rank_rows(db_rows, metric) for metric in METRIC_KEYS}
        db_means = {
            metric: (
                sum(to_float(row, metric) for row in db_rows) / len(db_rows)
                if db_rows
                else 0.0
            )
            for metric in METRIC_KEYS
        }
        top_model_by_mihi = max(
            db_rows,
            key=lambda item: (to_float(item, "mihi_full"), item["model"]),
        )["model"]

        for row in sorted(db_rows, key=lambda item: item["model"]):
            record = dict(row)
            record["mihi_full_rank"] = rank_maps["mihi_full"][row["model"]]
            record["core_mihi_rank"] = rank_maps["core_mihi"][row["model"]]
            record["whole_score_rank"] = rank_maps["whole_score"][row["model"]]
            record["sent_score_rank"] = rank_maps["sent_score"][row["model"]]
            record["imagery_score_rank"] = rank_maps["imagery_score"][row["model"]]
            record["excess_core_homogeneity_rank"] = rank_maps["excess_core_homogeneity"][row["model"]]
            record["db_mean_mihi_full"] = db_means["mihi_full"]
            record["db_mean_whole_score"] = db_means["whole_score"]
            record["db_mean_sent_score"] = db_means["sent_score"]
            record["db_mean_imagery_score"] = db_means["imagery_score"]
            record["mihi_full_minus_db_mean"] = to_float(row, "mihi_full") - db_means["mihi_full"]
            record["whole_score_minus_db_mean"] = to_float(row, "whole_score") - db_means["whole_score"]
            record["sent_score_minus_db_mean"] = to_float(row, "sent_score") - db_means["sent_score"]
            record["imagery_score_minus_db_mean"] = to_float(row, "imagery_score") - db_means["imagery_score"]
            record["top_model_by_mihi_full"] = top_model_by_mihi
            rows.append(record)
    return rows


def build_model_overall_profile(strict_rows, observe_rows):
    rows = []
    strict_map = {
        (row["db"], row["model"]): row
        for row in strict_rows
        if row.get("status") == "main" and row.get("model") in CORE_MODELS
    }
    observe_map = {
        (row["db"], row["model"]): row
        for row in observe_rows
        if row.get("status") == "main" and row.get("model") in CORE_MODELS
    }

    for model in CORE_MODELS:
        chosen = []
        source_trace = []
        for db_key in MAIN_DBS:
            row = strict_map.get((db_key, model))
            source = "strict"
            if row is None:
                row = observe_map.get((db_key, model))
                source = "observe"
            if row is None:
                continue
            chosen.append(row)
            source_trace.append(f"{db_key}:{source}")

        if not chosen:
            continue

        best_row = max(chosen, key=lambda item: (to_float(item, "mihi_full"), item["db"]))
        worst_row = min(chosen, key=lambda item: (to_float(item, "mihi_full"), item["db"]))
        rows.append(
            {
                "model": model,
                "db_count": len(chosen),
                "db_sources": "|".join(source_trace),
                "avg_mihi_full": sum(to_float(row, "mihi_full") for row in chosen) / len(chosen),
                "avg_core_mihi": sum(to_float(row, "core_mihi") for row in chosen) / len(chosen),
                "avg_whole_score": sum(to_float(row, "whole_score") for row in chosen) / len(chosen),
                "avg_sent_score": sum(to_float(row, "sent_score") for row in chosen) / len(chosen),
                "avg_imagery_score": sum(to_float(row, "imagery_score") for row in chosen) / len(chosen),
                "avg_excess_core_homogeneity": (
                    sum(to_float(row, "excess_core_homogeneity") for row in chosen) / len(chosen)
                ),
                "baseline_b1_mihi_full": to_float(strict_map.get(("b1", model), {}), "mihi_full"),
                "baseline_b1_whole_score": to_float(strict_map.get(("b1", model), {}), "whole_score"),
                "baseline_b1_sent_score": to_float(strict_map.get(("b1", model), {}), "sent_score"),
                "baseline_b1_imagery_score": to_float(strict_map.get(("b1", model), {}), "imagery_score"),
                "best_condition": best_row["db"],
                "best_condition_mihi_full": to_float(best_row, "mihi_full"),
                "worst_condition": worst_row["db"],
                "worst_condition_mihi_full": to_float(worst_row, "mihi_full"),
            }
        )
    return rows


def build_constraint_response(delta_rows):
    rows = []
    for row in delta_rows:
        delta_whole = to_float(row, "delta_whole_score")
        delta_sent = to_float(row, "delta_sent_score")
        delta_imagery = to_float(row, "delta_imagery_score")
        enriched = dict(row)
        enriched["dominant_positive_axis"] = pick_axis(delta_whole, delta_sent, delta_imagery)
        enriched["dominant_absolute_axis"] = pick_axis(
            delta_whole,
            delta_sent,
            delta_imagery,
            by_abs=True,
        )
        rows.append(enriched)
    return rows


def summarize_contrast_group(items, prefix):
    values = {
        "delta_mihi_full": [to_float(row, "delta_mihi_full") for row in items],
        "delta_core_mihi": [to_float(row, "delta_core_mihi") for row in items],
        "delta_whole_score": [to_float(row, "delta_whole_score") for row in items],
        "delta_sent_score": [to_float(row, "delta_sent_score") for row in items],
        "delta_imagery_score": [to_float(row, "delta_imagery_score") for row in items],
    }
    result = {
        f"{prefix}_contrast_count": len(items),
    }
    for key, nums in values.items():
        result[f"{prefix}_mean_{key}"] = (sum(nums) / len(nums)) if nums else 0.0
    if items:
        peak = max(items, key=lambda row: abs(to_float(row, "delta_mihi_full")))
        result[f"{prefix}_peak_contrast"] = f"{peak['from_db']}->{peak['to_db']}"
        result[f"{prefix}_peak_delta_mihi_full"] = to_float(peak, "delta_mihi_full")
        result[f"{prefix}_dominant_axis_by_mean_abs"] = pick_axis(
            result[f"{prefix}_mean_delta_whole_score"],
            result[f"{prefix}_mean_delta_sent_score"],
            result[f"{prefix}_mean_delta_imagery_score"],
            by_abs=True,
        )
    else:
        result[f"{prefix}_peak_contrast"] = ""
        result[f"{prefix}_peak_delta_mihi_full"] = 0.0
        result[f"{prefix}_dominant_axis_by_mean_abs"] = ""
    return result


def build_constraint_sensitivity(delta_rows):
    rows = []
    grouped = defaultdict(list)
    for row in delta_rows:
        if row.get("model") in CORE_MODELS:
            grouped[row["model"]].append(row)

    for model in CORE_MODELS:
        model_rows = grouped.get(model, [])
        theme_rows = [row for row in model_rows if row.get("from_db") == "b1"]
        strong_rows = [row for row in model_rows if row.get("from_db") in {"b2", "b3"}]
        row = {"model": model}
        row.update(summarize_contrast_group(theme_rows, "theme"))
        row.update(summarize_contrast_group(strong_rows, "strong"))
        rows.append(row)
    return rows


def main():
    strict_rows = read_csv(INPUT_DIR / "neo_model_summary.csv")
    observe_rows = read_csv(INPUT_DIR / "neo_model_summary_observe.csv")
    delta_rows = read_csv(INPUT_DIR / "neo_condition_deltas.csv")

    outputs = {
        "neo_model_condition_profile.csv": build_model_condition_profile(strict_rows),
        "neo_model_overall_profile.csv": build_model_overall_profile(strict_rows, observe_rows),
        "neo_model_constraint_response.csv": build_constraint_response(delta_rows),
        "neo_model_constraint_sensitivity.csv": build_constraint_sensitivity(delta_rows),
    }

    for filename, rows in outputs.items():
        path = OUTPUT_DIR / filename
        write_csv(path, rows)
        print(f"输出: {path} | rows={len(rows)}")


if __name__ == "__main__":
    main()
