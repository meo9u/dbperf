#!/usr/bin/env python3
"""Run the checkout scenario (class 2, write flow) at several concurrency levels, from a reset database each time.

For every database and VU level: reset the data (benchmark/reset_data.py, ~40 s), run k6 for a fixed time, then check
what the run left behind (benchmark/checkout_integrity.py: new orders == successful checkouts, seed logic checks).
At the end both databases are reset again and the original MongoDB validators are restored.

Usage:
  python3 benchmark/run_checkout.py --phase baseline_checkout --db both [--levels 4,8,16,32] [--duration 45s]
      [--variant baseline|optimized] [--hot-share 0.5] [--no-seed-checks]
Output: benchmark/results/<phase>/load/{checkout.<db>.vus<N>.summary.json, checkout.summary.tsv, checkout.meta.json}

The schema must be the baseline one (or the one this phase is meant to measure): apply / roll back optimization sets
(benchmark/optimization.py) BEFORE this script; a full reset keeps indexes but removes MongoDB inventory.quantity_available.
"""
import argparse
import datetime
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from checkout_integrity import summarize  # noqa: E402
from reset_data import KNOWN_FAIL, reset_db, restore_validators, run_checks  # noqa: E402
from run_class1 import ROOT, meta_mongo, meta_mysql, mongo_eval, mysql  # noqa: E402
from run_class2 import inspect_limits_k6, k6  # noqa: E402

SCENARIO = "checkout"


def reapply_mongo_optimizations():
    """A reload empties MongoDB inventory, which drops the stored quantity_available field of the class 1 optimization:
    apply that set again (idempotent: indexes exist, validator and field are recomputed)."""
    p = subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "optimization.py"), "apply", "--set", "class1",
                        "--db", "mongodb"], capture_output=True, text=True, encoding="utf-8")
    if p.returncode != 0:
        sys.exit(f"re-applying the MongoDB optimization failed:\n{p.stdout[-800:]}\n{p.stderr[-800:]}")


def summarize_k6(path):
    m = json.loads(path.read_text())["metrics"]
    d = m["iteration_duration"]
    c = lambda name, key="count": m.get(name, {}).get(key, 0)
    ok = int(c("checkout_ok"))
    return {"ok": ok, "tps": c("checkout_ok", "rate"), "avg_ms": d["avg"], "p50_ms": d["med"], "p95_ms": d["p(95)"],
            "p99_ms": d.get("p(99)", float("nan")), "max_ms": d["max"], "retries": int(c("checkout_retry")),
            "stock_out": int(c("checkout_stock_out")), "failed": int(c("checkout_failed")), "errors": int(c("checkout_error"))}


def durability():
    """Settings that decide the cost of a commit; recorded with every result (defaults of each database)."""
    my = mysql("SELECT @@innodb_flush_log_at_trx_commit, @@sync_binlog, @@transaction_isolation, @@log_bin;", "-N").strip().split("\t")
    mo = mongo_eval('const r=db.adminCommand({getDefaultRWConcern:1});print(JSON.stringify({defaultWriteConcern:r.defaultWriteConcern,'
                    'defaultReadConcern:r.defaultReadConcern,storageEngine:db.serverStatus().storageEngine.name}))')
    return {"mysql": {"innodb_flush_log_at_trx_commit": int(my[0]), "sync_binlog": int(my[1]), "transaction_isolation": my[2],
                      "log_bin": int(my[3])},
            "mongodb": json.loads(mo)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--phase", required=True)
    ap.add_argument("--db", choices=["mysql", "mongodb", "both"], default="both")
    ap.add_argument("--levels", default="4,8,16,32")
    ap.add_argument("--duration", default="45s")
    ap.add_argument("--variant", default="baseline", choices=["baseline", "optimized"])
    ap.add_argument("--hot-share", default="0.5", help="share of checkouts that use a contended (hot) template order")
    ap.add_argument("--indexed", action="store_true",
                    help="optimization sets (class1, search) are applied: re-apply the MongoDB part after every reload and "
                         "keep inventory.quantity_available up to date (index tax measurement)")
    ap.add_argument("--env", action="append", default=[], metavar="KEY=VALUE", help="extra k6 environment variable (repeatable)")
    ap.add_argument("--no-seed-checks", action="store_true", help="skip seed-check-* after each level (integrity counts are still checked)")
    a = ap.parse_args()
    dbs = ["mysql", "mongodb"] if a.db == "both" else [a.db]
    levels = [int(x) for x in a.levels.split(",")]
    outdir = ROOT / "benchmark" / "results" / a.phase / "load"
    outdir.mkdir(parents=True, exist_ok=True)

    meta = {"scenario": SCENARIO, "phase": a.phase, "variant": a.variant, "hot_share": float(a.hot_share), "indexed": a.indexed, "extra_env": a.env,
            "date_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "levels_vus": levels, "duration_per_level": a.duration, "durability": durability(),
            "k6": {"image": "dbperf-k6:local", **inspect_limits_k6()},
            "mysql": meta_mysql(), "mongodb": meta_mongo()}
    rows, problems = [], []
    try:
        for db in dbs:
            for vus in levels:
                print(f"[{db}] {vus} VUs: reset ...", flush=True)
                reset_db(db, prepare=True)
                if a.indexed and db == "mongodb":
                    reapply_mongo_optimizations()
                name = f"{SCENARIO}.{db}.vus{vus}.summary.json"
                print(f"[{db}] {vus} VUs for {a.duration} ...", flush=True)
                k6(SCENARIO, db, vus, a.duration, f"{a.phase}/load/{name}", a.variant, [f"HOT_SHARE={a.hot_share}"] + a.env + (["MAINTAIN_AVAILABLE=1"] if a.indexed and db == "mongodb" else []))
                s = summarize_k6(outdir / name)
                st = summarize(db)
                verdict = "OK"
                if st["new_orders"] != s["ok"] or st["new_payments"] != s["ok"]:
                    verdict = f"FAIL(new_orders={st['new_orders']} payments={st['new_payments']} ok={s['ok']})"
                if verdict == "OK" and not a.no_seed_checks:
                    fails, _ = run_checks("seed-check-" + db)
                    bad = {k: v for k, v in fails.items() if KNOWN_FAIL.get(k) != v}
                    if bad:
                        verdict = f"FAIL(seed checks {bad})"
                if verdict != "OK":
                    problems.append((db, vus, verdict))
                s.update({"integrity": verdict, "new_lines": st["new_lines"], "new_qty": st["new_qty"]})
                rows.append((db, vus, s))
                print(f"    ok={s['ok']} tps={s['tps']:.1f} p95={s['p95_ms']:.1f} ms retries={s['retries']} stock_out={s['stock_out']} "
                      f"failed={s['failed']} errors={s['errors']} integrity={verdict}", flush=True)
    finally:
        print("final reset of both databases ...", flush=True)
        reset_db("mysql")
        reset_db("mongodb")
        restore_validators()
    (outdir / f"{SCENARIO}.meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    header = ["db", "vus", "ok", "tps", "avg_ms", "p50_ms", "p95_ms", "p99_ms", "max_ms", "retries", "retry_pct", "stock_out", "failed", "errors", "integrity"]
    table = [[db, str(v), str(s["ok"]), f"{s['tps']:.1f}", f"{s['avg_ms']:.1f}", f"{s['p50_ms']:.1f}", f"{s['p95_ms']:.1f}",
              f"{s['p99_ms']:.1f}", f"{s['max_ms']:.1f}", str(s["retries"]),
              f"{100 * s['retries'] / max(1, s['ok'] + s['retries']):.1f}", str(s["stock_out"]), str(s["failed"]), str(s["errors"]), s["integrity"]]
             for db, v, s in rows]
    (outdir / f"{SCENARIO}.summary.tsv").write_text("\n".join("\t".join(r) for r in [header] + table) + "\n")
    w = [max(len(x) for x in col) for col in zip(header, *table)]
    for r in [header] + table:
        print("  ".join(x.ljust(w[i]) if i == 0 else x.rjust(w[i]) for i, x in enumerate(r)))
    print(f"\nwritten to {outdir.relative_to(ROOT)}")
    if problems:
        sys.exit(f"integrity problems: {problems}")


if __name__ == "__main__":
    main()
