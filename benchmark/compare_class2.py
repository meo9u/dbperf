#!/usr/bin/env python3
"""Compare class 2 load results across phases (default: baseline idx optimized).

Reads benchmark/results/<phase>/load/<scenario>.summary.tsv, prints per DB and VU level the throughput (TPS) and
latency of every phase plus the TPS ratio of each later phase vs the first, and the peak TPS per phase. Writes benchmark/results/load_comparison.<scenario>.tsv.

Usage: python3 benchmark/compare_class2.py --scenario search_products [--phases baseline idx optimized]
Pass a repeat of a phase (for example baseline_r2) as an extra phase to see the run-to-run noise.
"""
import argparse
import sys
from pathlib import Path

RESULTS = Path(__file__).resolve().parent / "results"


def load(phase, scenario):
    path = RESULTS / phase / "load" / f"{scenario}.summary.tsv"
    if not path.exists():
        sys.exit(f"missing {path}")
    lines = [l.split("\t") for l in path.read_text().strip().split("\n")]
    head = lines[0]
    return {(r[0], int(r[1])): dict(zip(head, r)) for r in lines[1:]}


def peak(rows, db):
    """(peak TPS, VU level where it occurs). Closed-loop runs on 2 CPUs peak at low concurrency and then fall."""
    best = max(((float(r["tps"]), v) for (d, v), r in rows.items() if d == db))
    return best


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenario", required=True)
    ap.add_argument("--phases", nargs="+", default=["baseline", "idx", "optimized"])
    a = ap.parse_args()
    data = {p: load(p, a.scenario) for p in a.phases}
    first, others = a.phases[0], a.phases[1:]
    header = ["db", "vus"] + [f"{p}_{m}" for p in a.phases for m in ("tps", "p50_ms", "p95_ms", "p99_ms")]
    header += [f"{p}_tps_x" for p in others]
    rows = []
    for key in sorted(data[first], key=lambda k: (k[0], k[1])):
        r = [key[0], str(key[1])]
        for p in a.phases:
            d = data[p].get(key)
            r += [d["tps"], d["p50_ms"], d["p95_ms"], d["p99_ms"]] if d else [""] * 4
        for p in others:
            d = data[p].get(key)
            r.append(f"{float(d['tps']) / float(data[first][key]['tps']):.2f}x" if d else "")
        rows.append(r)
    out = RESULTS / f"load_comparison.{a.scenario}.tsv"
    out.write_text("\n".join("\t".join(r) for r in [header] + rows) + "\n")
    w = [max(len(x) for x in col) for col in zip(header, *rows)]
    for r in [header] + rows:
        print("  ".join(x.ljust(w[i]) if i == 0 else x.rjust(w[i]) for i, x in enumerate(r)))
    print()
    for db in sorted({k[0] for k in data[first]}):
        print(f"{db}: peak TPS (VUs) " + ", ".join("%s=%.0f(%d)" % ((p,) + peak(data[p], db)) for p in a.phases))
    print(f"\nwritten to {out.relative_to(RESULTS.parent.parent)}")


if __name__ == "__main__":
    main()
