#!/usr/bin/env python3
"""Compare benchmark phases (default: baseline idx optimized) per query and DB.

Reads benchmark/results/<phase>/<db>/qN_*.{timing.json,explain.*,result.tsv} and writes
benchmark/results/comparison.tsv plus a table on stdout: p50/p95 per phase, speedup vs the first phase,
rows / documents examined from the plan, and whether result.tsv equals the first phase.

Usage: python3 benchmark/compare.py [--phases baseline idx optimized]
"""
import argparse
import json
import re
import sys
from pathlib import Path

RESULTS = Path(__file__).resolve().parent / "results"


def examined_mysql(path):
    """Largest 'rows=' read by a leaf scan or lookup in EXPLAIN ANALYZE (a rough 'rows touched' figure)."""
    best = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if re.search(r"(Table scan|Index (range )?scan|Covering index (range )?scan|Index lookup|Covering index lookup)", line):
            m = re.search(r"actual time=[\d.e+-]+\.\.[\d.e+-]+ rows=([\d.e+]+) loops=(\d+)", line)
            if m:
                best = max(best, int(float(m.group(1)) * int(m.group(2))))
    return best


def plan_mysql(path):
    t = path.read_text(encoding="utf-8")
    kind = "table scan" if "Table scan on" in t.replace("<temporary>", "") and "Covering" not in t else "index"
    return "covering index" if "Covering index" in t else kind


def examined_mongo(path):
    s = path.read_text(encoding="utf-8")
    docs = [int(x) for x in re.findall(r'"totalDocsExamined": (\d+)', s)]
    return max(docs) if docs else 0


def plan_mongo(path):
    s = path.read_text(encoding="utf-8")
    if "PROJECTION_COVERED" in s:
        return "covered index"
    if "IXSCAN" in s:
        return "index+fetch"
    return "collscan"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--phases", nargs="+", default=["baseline", "idx", "optimized"])
    a = ap.parse_args()
    phases = [p for p in a.phases if (RESULTS / p).is_dir()]
    if len(phases) < 2:
        sys.exit(f"need at least two phases with results, found {phases}")
    first, others = phases[0], phases[1:]
    header = ["query", "db"] + [f"{p}_{m}" for p in phases for m in ("p50_ms", "p95_ms")]
    header += [f"{p}_{m}" for p in others for m in ("speedup", "same_result")]
    header += [f"{p}_examined" for p in phases] + [f"{p}_plan" for p in phases]
    rows = []
    for db in ("mysql", "mongodb"):
        ex = "explain.txt" if db == "mysql" else "explain.json"
        examined = examined_mysql if db == "mysql" else examined_mongo
        plan = plan_mysql if db == "mysql" else plan_mongo
        for t in sorted((RESULTS / first / db).glob("*.timing.json")):
            q = t.name[: -len(".timing.json")]
            d = {p: RESULTS / p / db for p in phases}
            have = {p: (d[p] / f"{q}.timing.json").exists() for p in phases}
            lat = {p: json.loads((d[p] / f"{q}.timing.json").read_text())["latency_ms"] for p in phases if have[p]}
            res = {p: (d[p] / f"{q}.result.tsv").read_text(encoding="utf-8") for p in phases if have[p]}
            row = [q, db]
            for p in phases:
                row += [f"{lat[p]['p50']:.1f}", f"{lat[p]['p95']:.1f}"] if have[p] else ["", ""]
            for p in others:
                row += [f"{lat[first]['p50'] / lat[p]['p50']:.2f}x", "yes" if res[p] == res[first] else "NO"] if have[p] else ["", ""]
            row += [str(examined(d[p] / f"{q}.{ex}")) if have[p] else "" for p in phases]
            row += [plan(d[p] / f"{q}.{ex}") if have[p] else "" for p in phases]
            rows.append(row)
    (RESULTS / "comparison.tsv").write_text("\n".join("\t".join(r) for r in [header] + rows) + "\n", encoding="utf-8")
    w = [max(len(x) for x in col) for col in zip(header, *rows)]
    for r in [header] + rows:
        print("  ".join(x.ljust(w[i]) if i < 2 else x.rjust(w[i]) for i, x in enumerate(r)))
    print(f"\nwritten to {(RESULTS / 'comparison.tsv').relative_to(RESULTS.parent.parent)}")


if __name__ == "__main__":
    main()
