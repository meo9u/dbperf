#!/usr/bin/env python3
"""Run a class 2 k6 scenario (docs/benchmark-operations.md) on MySQL and/or MongoDB at several concurrency levels.

Standard library only. For every DB and VU level it runs the k6 service once (constant VUs for a fixed time),
exports the k6 summary, then writes a table with throughput and latency per level.

Usage:
  python3 benchmark/run_class2.py --scenario search_products --phase baseline --db both \
      [--levels 4,8,16,32,64] [--duration 45s] [--warmup 20s]
Output: benchmark/results/<phase>/load/{<scenario>.<db>.vus<N>.summary.json, <scenario>.summary.tsv, <scenario>.meta.json}

Only read-only scenarios are safe to repeat. Write scenarios (checkout) change the data: reload the seed data
before each measured run and run seed/checks/ afterwards (see CLAUDE.md).
"""
import argparse
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_class1 import ROOT, inspect_limits, meta_mongo, meta_mysql  # noqa: E402


def k6(scenario, db, vus, duration, export):
    # --user: the results mount is owned by the host user; k6's default user could not write the summary there
    # (k6 only logs the error and still exits 0, so the export is checked below).
    cmd = ["docker", "compose", "--profile", "loadtest", "run", "--rm", "-T", "--user", f"{os.getuid()}:{os.getgid()}", "k6", "run",
           "-e", f"VUS={vus}", "-e", f"DURATION={duration}"]
    if export:
        cmd += [f"--summary-export=/results/{export}"]
    cmd += [f"/scripts/{scenario}.{db}.js"]
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    if p.returncode != 0:
        sys.exit(f"k6 failed ({scenario} {db} vus={vus}):\n{p.stderr[-1500:]}\n{p.stdout[-1500:]}")
    if export and not (ROOT / "benchmark" / "results" / export).exists():
        sys.exit(f"k6 did not write /results/{export}:\n{p.stderr[-800:]}")


def summarize(path):
    m = json.loads(path.read_text())["metrics"]
    d = m["iteration_duration"]
    return {"iterations": int(m["iterations"]["count"]), "tps": m["iterations"]["rate"],
            "avg_ms": d["avg"], "p50_ms": d["med"], "p95_ms": d["p(95)"], "p99_ms": d.get("p(99)", float("nan")),
            "max_ms": d["max"], "rows_per_s": m.get("search_rows", {}).get("rate", 0.0)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenario", required=True, help="benchmark/scenarios/<scenario>.<db>.js")
    ap.add_argument("--phase", default="baseline")
    ap.add_argument("--db", choices=["mysql", "mongodb", "both"], default="both")
    ap.add_argument("--levels", default="4,8,16,32,64", help="comma list of VU counts")
    ap.add_argument("--duration", default="45s", help="time per level")
    ap.add_argument("--warmup", default="20s", help="unrecorded run at 16 VUs before the first level of each DB")
    a = ap.parse_args()
    dbs = ["mysql", "mongodb"] if a.db == "both" else [a.db]
    levels = [int(x) for x in a.levels.split(",")]
    outdir = ROOT / "benchmark" / "results" / a.phase / "load"
    outdir.mkdir(parents=True, exist_ok=True)

    meta = {"scenario": a.scenario, "phase": a.phase, "date_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "levels_vus": levels, "duration_per_level": a.duration, "warmup": a.warmup,
            "k6": {"image": "dbperf-k6:local", **{k: v for k, v in inspect_limits_k6().items()}}}
    if "mysql" in dbs:
        meta["mysql"] = meta_mysql()
    if "mongodb" in dbs:
        meta["mongodb"] = meta_mongo()

    rows = []
    for db in dbs:
        print(f"[{db}] warm-up {a.warmup} ...", flush=True)
        k6(a.scenario, db, 16, a.warmup, None)
        for vus in levels:
            name = f"{a.scenario}.{db}.vus{vus}.summary.json"
            print(f"[{db}] {vus} VUs for {a.duration} ...", flush=True)
            k6(a.scenario, db, vus, a.duration, f"{a.phase}/load/{name}")
            rows.append((db, vus, summarize(outdir / name)))
    (outdir / f"{a.scenario}.meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    header = ["db", "vus", "iterations", "tps", "avg_ms", "p50_ms", "p95_ms", "p99_ms", "max_ms", "rows_per_s"]
    table = [[db, str(v), str(s["iterations"]), f"{s['tps']:.1f}", f"{s['avg_ms']:.1f}", f"{s['p50_ms']:.1f}",
              f"{s['p95_ms']:.1f}", f"{s['p99_ms']:.1f}", f"{s['max_ms']:.1f}", f"{s['rows_per_s']:.0f}"] for db, v, s in rows]
    (outdir / f"{a.scenario}.summary.tsv").write_text("\n".join("\t".join(r) for r in [header] + table) + "\n")
    w = [max(len(x) for x in col) for col in zip(header, *table)]
    for r in [header] + table:
        print("  ".join(x.ljust(w[i]) if i == 0 else x.rjust(w[i]) for i, x in enumerate(r)))
    print(f"\nwritten to {outdir.relative_to(ROOT)}")


def inspect_limits_k6():
    # The k6 service is capped in docker-compose.yml (cpus 2, mem_limit 2g); read it from the compose config.
    out = subprocess.run(["docker", "compose", "--profile", "loadtest", "config", "--format", "json"], cwd=ROOT,
                         capture_output=True, text=True, encoding="utf-8").stdout
    svc = json.loads(out)["services"]["k6"]
    return {"cpus": float(svc.get("cpus", 0)), "mem_limit_mb": int(svc.get("mem_limit", 0)) // 1048576}


if __name__ == "__main__":
    main()
