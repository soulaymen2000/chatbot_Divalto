# ============================================================
# ADVANCED REPORT GENERATOR (SUPERVISOR-LEVEL)
# Inspired by your example + FULL metadata usage
# ============================================================

import os
import json
import csv
from collections import defaultdict

INPUT_DIR = r"D:\\pfe2026\\data\\DC\\output"
REPORT_DIR = r"D:\\pfe2026\\data\\DC\\report"

os.makedirs(REPORT_DIR, exist_ok=True)
os.makedirs(os.path.join(REPORT_DIR, "per_file"), exist_ok=True)

# ============================================================
# SIMPLE TOKEN COUNTER
# ============================================================

def count_tokens(text):
    return len(text.split())

# ============================================================
# GLOBAL STORAGE
# ============================================================

global_rows = []
strategy_stats = defaultdict(lambda: {"total":0, "accepted":0})
retry_stats = defaultdict(int)
boundary_issues = 0

# ============================================================
# PROCESS FILES
# ============================================================

for root, _, files in os.walk(INPUT_DIR):
    for file in files:
        if file.endswith(".json"):

            path = os.path.join(root, file)

            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                if not isinstance(data, list) or not data or "chunk_id" not in data[0]:
                    continue

            except Exception as e:
                print(f"Skipping {file}: {e}")
                continue

            file_name = file.replace(".json", "")

            file_scores = []
            per_file_data = []
            file_tokens_total = 0

            # ============================================================
            # PROCESS CHUNKS
            # ============================================================

            for c in data:
                text = c.get("text", "")
                chunk_tokens = c.get("token_count", count_tokens(text))
                file_tokens_total += chunk_tokens

                scores = c.get("validation_score", {})

                completeness = scores.get("completeness", 0)
                coherence = scores.get("coherence", 0)
                relevance = scores.get("relevance", 0)
                boundary = scores.get("boundary", 0)
                fidelity = scores.get("fidelity", 0)
                final_score = scores.get("final_score", 0)

                status = c.get("validation_status", "unknown")
                method = c.get("chunking_method", "unknown")
                retry_depth = c.get("retry_depth", 0)
                boundary_flag = c.get("boundary_issue", False)

                # GLOBAL TRACKING
                strategy_stats[method]["total"] += 1
                if status in ("accepted", "accepted_max_depth"):
                    strategy_stats[method]["accepted"] += 1

                retry_stats[retry_depth] += 1

                if boundary_flag:
                    boundary_issues += 1

                row = {
                    "file": file_name,
                    "chunk_id": c.get("chunk_id"),
                    "chunk_tokens": chunk_tokens,
                    "file_tokens": file_tokens_total,
                    "status": status,
                    "method": method,
                    "retry_depth": retry_depth,

                    "completeness": completeness,
                    "coherence": coherence,
                    "relevance": relevance,
                    "boundary": boundary,
                    "fidelity": fidelity,
                    "final_score": final_score
                }

                file_scores.append(final_score)
                per_file_data.append(row)
                global_rows.append(row)

            # ============================================================
            # FILE SUMMARY
            # ============================================================

            if file_scores:
                file_report = {
                    "file": file_name,
                    "total_chunks": len(file_scores),
                    "file_tokens": file_tokens_total,
                    "avg_score": sum(file_scores) / len(file_scores),
                    "min_score": min(file_scores),
                    "max_score": max(file_scores)
                }
            else:
                file_report = {
                    "file": file_name,
                    "total_chunks": 0,
                    "file_tokens": file_tokens_total
                }

            # SAVE PER FILE
            out_path = os.path.join(REPORT_DIR, "per_file", file_name + ".report.json")

            with open(out_path, "w", encoding="utf-8") as f:
                json.dump({
                    "summary": file_report,
                    "chunks": per_file_data
                }, f, indent=2)

# ============================================================
# GLOBAL METRICS
# ============================================================

all_scores = [r["final_score"] for r in global_rows]

# strategy performance
strategy_perf = {
    k: {
        "acceptance_rate": v["accepted"] / v["total"] if v["total"] else 0,
        "total": v["total"]
    }
    for k, v in strategy_stats.items()
}

# retry distribution
retry_distribution = dict(retry_stats)

# boundary percentage
boundary_pct = boundary_issues / len(global_rows) if global_rows else 0

# final global report
global_report = {
    "total_files": len(set(r["file"] for r in global_rows)),
    "total_chunks": len(global_rows),
    "avg_score": sum(all_scores)/len(all_scores) if all_scores else 0,
    "min_score": min(all_scores) if all_scores else 0,
    "max_score": max(all_scores) if all_scores else 0,

    "strategy_performance": strategy_perf,
    "retry_distribution": retry_distribution,
    "boundary_issues_percentage": boundary_pct
}

with open(os.path.join(REPORT_DIR, "global_report.json"), "w") as f:
    json.dump(global_report, f, indent=2)

# ============================================================
# CSV EXPORT (FULL DETAIL)
# ============================================================

csv_path = os.path.join(REPORT_DIR, "global_report.csv")

if global_rows:
    with open(csv_path, "w", newline="", encoding="utf-8") as csvfile:
        fieldnames = list(global_rows[0].keys())
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        writer.writeheader()
        writer.writerows(global_rows)

print("✅ Supervisor-level reports generated successfully!")
