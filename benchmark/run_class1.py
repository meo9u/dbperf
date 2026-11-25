#!/usr/bin/env python3
"""Run the class 1 benchmark queries (docs/benchmark-operations.md) on MySQL and/or MongoDB.

Standard library only; talks to the running containers through `docker exec` (mysql / mongosh).

Per query and DB it:
  1. runs the query file RUNS + 1 times inside ONE database session (no docker exec overhead in the timing);
     run 0 is the first (coldest) run and is reported separately as `discarded_cold`;
  2. times each run inside the session (MySQL: performance_schema TIMER_WAIT; MongoDB: performance.now());
  3. saves the output of run 0 as result.tsv, and the query plan as explain.txt / explain.json.
When both DBs are selected, result.tsv files must be identical or nothing is written (exit code 1).

Usage:
  python3 benchmark/run_class1.py --phase baseline --db both [--queries q1,q3] [--runs 11]
Output: benchmark/results/<phase>/{meta.json,summary.tsv,<db>/qN_<name>.{result.tsv,explain.*,timing.json}}
"""
import argparse
import datetime
import json
import math
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTAINER = {"mysql": "dbperf-mysql", "mongodb": "dbperf-mongodb"}
EXT = {"mysql": ".sql", "mongodb": ".js"}
MYSQL_SH = 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot --default-character-set=utf8mb4 -B -r dbperf'
MONGO_SH = ('mongosh -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" '
            '--authenticationDatabase admin --quiet')
# Latest SELECT of this session = the query that just ran (the marker SELECT runs before it).
MYSQL_TIMING_SQL = ("SELECT 'v' AS `@@TIMING@@`, ROUND(TIMER_WAIT/1000000000, 3) AS ms "
                    "FROM performance_schema.events_statements_history "
                    "WHERE thread_id = PS_CURRENT_THREAD_ID() AND event_name = 'statement/sql/select' "
                    "ORDER BY event_id DESC LIMIT 1;")


def sh(cmd, stdin=None):
    p = subprocess.run(cmd, input=stdin, capture_output=True, text=True, encoding="utf-8")
    if p.returncode != 0:
        sys.exit(f"command failed: {' '.join(cmd[:6])} ...\n{p.stderr.strip()}\n{p.stdout[-500:]}")
    return p.stdout


def mysql(sql, extra=""):
    cmd = ["docker", "exec", "-i", CONTAINER["mysql"], "sh", "-c", MYSQL_SH + " " + extra]
    return sh(cmd, stdin=sql)


def mongo_file(path):
    return sh(["docker", "exec", CONTAINER["mongodb"], "sh", "-c", f"{MONGO_SH} --file {path}"])


def mongo_eval(js):
    return sh(["docker", "exec", CONTAINER["mongodb"], "sh", "-c", f"{MONGO_SH} --eval '{js}'"])


def percentile(sorted_vals, p):
    return sorted_vals[max(0, math.ceil(p * len(sorted_vals)) - 1)]


def stats(samples):
    s = sorted(samples)
    return {"min": s[0], "p50": percentile(s, 0.5), "p95": percentile(s, 0.95), "max": s[-1]}


def discover(phase, dbs, wanted):
    names = None
    for db in dbs:
        found = {p.stem: p for p in sorted((ROOT / "queries" / db / phase).glob("q*" + EXT[db]))}
        names = set(found) if names is None else names & set(found)
    found_by_db = {db: {p.stem: p for p in (ROOT / "queries" / db / phase).glob("q*" + EXT[db])} for db in dbs}
    names = sorted(n for n in names if not wanted or any(n.startswith(w + "_") or n == w for w in wanted))
    if not names:
        sys.exit(f"no queries found for phase={phase} dbs={dbs} filter={wanted}")
    return names, found_by_db


# ---------- MySQL ----------

def run_mysql(path, runs):
    body = path.read_text(encoding="utf-8")
    script = "".join(f"SELECT 1 AS `@@RUN@@`;\n{body}\n{MYSQL_TIMING_SQL}\n" for _ in range(runs + 1))
    out = mysql(script)
    results, cur, skip, want_ms = [], None, False, False
    for line in out.split("\n"):
        if line == "@@RUN@@":
            cur, skip = {"lines": [], "ms": None}, True
        elif skip:
            skip = False
        elif line.startswith("@@TIMING@@\t"):
            want_ms = True
        elif want_ms:
            cur["ms"] = float(line.split("\t")[1])
            results.append(cur)
            want_ms = False
        elif cur is not None and line != "":
            cur["lines"].append(line)
    if len(results) != runs + 1:
        sys.exit(f"{path.name}: expected {runs + 1} timed runs from MySQL, got {len(results)}")
    # EXPLAIN ANALYZE of the last statement; earlier statements (SET ...) are setup.
    stmts = [s.strip() for s in re.sub(r"(?m)^\s*--.*$", "", body).split(";") if s.strip()]
    plan = mysql(";\n".join(stmts[:-1] + ["EXPLAIN ANALYZE " + stmts[-1]]) + ";\n").split("\n", 1)[1]
    return results, plan.rstrip("\n") + "\n"


# ---------- MongoDB ----------

# The query source is inlined (not eval'd or wrapped in a Function) so that mongosh's async rewriter still
# auto-awaits driver calls; each copy sits in its own block so the file's top-level `const`s do not collide.
TIMING_BLOCK = """print('@@RUN@@');
{{
  const __t0 = performance.now();
  {{
{src}
  }}
  print('@@TIMING@@\\t' + (performance.now() - __t0).toFixed(3));
}}
"""

EXPLAIN_RE = re.compile(r"\bd\.(\w+)\.aggregate\(pipeline(, OPTS)?\)\.forEach\(")


def timing_js(src, runs):
    return "".join(TIMING_BLOCK.format(src=src) for _ in range(runs + 1))


def explain_js(src):
    """Swap the final `d.<coll>.aggregate(pipeline).forEach(` for an executionStats explain; silence print()."""
    body, n = EXPLAIN_RE.subn(r'__out = d.\1.explain("executionStats").aggregate(pipeline\2); [].forEach(', src)
    if n != 1:
        sys.exit("cannot build explain wrapper: expected exactly one d.<coll>.aggregate(pipeline).forEach( call")
    return ("let __out = null;\n{\n  const print = () => {};\n" + body + "\n}\n"
            "print(EJSON.stringify(__out, null, 2));\n")


def stage_mongo(phase, names, found, runs):
    """Copy the query files plus generated wrappers into the container."""
    sh(["docker", "exec", CONTAINER["mongodb"], "rm", "-rf", "/tmp/qbench"])
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        for n in names:
            src = found[n].read_text(encoding="utf-8")
            (t / f"{n}.timing.js").write_text(timing_js(src, runs), encoding="utf-8")
            (t / f"{n}.explain.js").write_text(explain_js(src), encoding="utf-8")
        sh(["docker", "cp", str(t), f"{CONTAINER['mongodb']}:/tmp/qbench"])


def run_mongo(name, runs):
    out = mongo_file(f"/tmp/qbench/{name}.timing.js")
    results, cur = [], None
    for line in out.split("\n"):
        if line == "@@RUN@@":
            cur = {"lines": [], "ms": None}
        elif line.startswith("@@TIMING@@\t"):
            cur["ms"] = float(line.split("\t")[1])
            results.append(cur)
        elif cur is not None and line != "":
            cur["lines"].append(line)
    if len(results) != runs + 1:
        sys.exit(f"{name}: expected {runs + 1} timed runs from MongoDB, got {len(results)}")
    return results, mongo_file(f"/tmp/qbench/{name}.explain.js").rstrip("\n") + "\n"


# ---------- metadata ----------

def inspect_limits(db):
    mem, cpus = sh(["docker", "inspect", "-f", "{{.HostConfig.Memory}} {{.HostConfig.NanoCpus}}",
                    CONTAINER[db]]).split()
    return {"mem_limit_mb": int(mem) // 1048576, "cpus": int(cpus) / 1e9}


def meta_mysql():
    rows = lambda sql: [l.split("\t") for l in mysql(sql, "-N").strip().split("\n") if l]
    v = rows("SELECT VERSION(), @@innodb_buffer_pool_size/1048576, @@innodb_flush_log_at_trx_commit, "
             "@@sync_binlog, @@log_bin;")[0]
    pages = dict(rows("SHOW GLOBAL STATUS WHERE Variable_name IN "
                      "('Innodb_buffer_pool_pages_data','Innodb_buffer_pool_pages_total');"))
    tables = [r[0] for r in rows("SELECT table_name FROM information_schema.tables "
                                 "WHERE table_schema='dbperf' AND table_type='BASE TABLE' ORDER BY 1;")]
    counts = {t: int(rows(f"SELECT COUNT(*) FROM `{t}`;")[0][0]) for t in tables}
    sizes = {t: {"data_mb": round(int(dl) / 1048576, 1), "index_mb": round(int(il) / 1048576, 1)}
             for t, dl, il in rows("SET SESSION information_schema_stats_expiry = 0; "
                                   "SELECT table_name, data_length, index_length FROM information_schema.tables "
                                   "WHERE table_schema='dbperf' AND table_type='BASE TABLE' ORDER BY 1;")}
    idx = {}
    for t, i, cols in rows("SELECT table_name, index_name, GROUP_CONCAT(column_name ORDER BY seq_in_index) "
                           "FROM information_schema.statistics WHERE table_schema='dbperf' "
                           "GROUP BY table_name, index_name ORDER BY 1, 2;"):
        idx.setdefault(t, []).append(f"{i}({cols})")
    return {"version": v[0], "buffer_pool_mb": float(v[1]), "innodb_flush_log_at_trx_commit": int(v[2]),
            "sync_binlog": int(v[3]), "log_bin": int(v[4]),
            "buffer_pool_pages_used_at_start": int(pages["Innodb_buffer_pool_pages_data"]),
            "buffer_pool_pages_total": int(pages["Innodb_buffer_pool_pages_total"]),
            "row_counts": counts, "sizes": sizes, "indexes": idx, **inspect_limits("mysql")}


def meta_mongo():
    js = ("const d=db.getSiblingDB(\"dbperf\"); const cols=d.getCollectionNames(); const c=db.serverStatus().wiredTiger.cache;"
          "print(JSON.stringify({version: db.version(), wt_cache_max_mb: c[\"maximum bytes configured\"]/1048576,"
          "wt_cache_used_at_start_mb: c[\"bytes currently in the cache\"]/1048576,"
          "row_counts: Object.fromEntries(cols.map(n=>[n, d.getCollection(n).countDocuments({})])),"
          "sizes: Object.fromEntries(cols.map(n=>{const s=d.runCommand({collStats:n});"
          "return [n,{data_mb:Math.round(s.storageSize/104857.6)/10,index_mb:Math.round(s.totalIndexSize/104857.6)/10}]})),"
          "indexes: Object.fromEntries(cols.map(n=>[n, d.getCollection(n).getIndexes().map(i=>i.name)]))}))")
    return {**json.loads(mongo_eval(js)), **inspect_limits("mongodb")}


# ---------- main ----------

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--phase", default="baseline", help="results/<phase>/ and, unless --query-phase is set, queries/<db>/<phase>/")
    ap.add_argument("--query-phase", default=None,
                    help="read queries from queries/<db>/<this>/ instead (e.g. --phase idx --query-phase baseline)")
    ap.add_argument("--db", choices=["mysql", "mongodb", "both"], default="both")
    ap.add_argument("--queries", default="", help="comma list, e.g. q1,q3 (default: all)")
    ap.add_argument("--runs", type=int, default=11, help="measured runs per query, excluding the first (cold) run")
    a = ap.parse_args()
    if a.runs < 1:
        sys.exit("--runs must be >= 1")
    dbs = ["mysql", "mongodb"] if a.db == "both" else [a.db]
    qphase = a.query_phase or a.phase
    names, found = discover(qphase, dbs, [q for q in a.queries.split(",") if q])
    outdir = ROOT / "benchmark" / "results" / a.phase

    meta = {"phase": a.phase, "query_phase": qphase, "date_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "runs": a.runs, "queries": names}
    if "mysql" in dbs:
        meta["mysql"] = meta_mysql()
    if "mongodb" in dbs:
        meta["mongodb"] = meta_mongo()
        stage_mongo(qphase, names, found["mongodb"], a.runs)

    data = {}  # (name, db) -> (results, plan)
    for n in names:
        for db in dbs:
            print(f"running {n} on {db} ...", flush=True)
            data[(n, db)] = run_mysql(found[db][n], a.runs) if db == "mysql" else run_mongo(n, a.runs)

    if len(dbs) == 2:  # equivalence gate: nothing is written unless both DBs agree
        bad = [n for n in names if data[(n, "mysql")][0][0]["lines"] != data[(n, "mongodb")][0][0]["lines"]]
        if bad:
            sys.exit(f"FAIL: result.tsv differs between MySQL and MongoDB for {bad}; nothing written")

    if a.phase != "baseline":  # an optimization must not change any result
        for (n, db), (results, _) in data.items():
            ref = ROOT / "benchmark" / "results" / "baseline" / db / f"{n}.result.tsv"
            if ref.exists() and ref.read_text(encoding="utf-8") != "\n".join(results[0]["lines"]) + "\n":
                sys.exit(f"FAIL: {n} on {db} returns different rows than baseline; nothing written")

    rows = []
    for (n, db), (results, plan) in data.items():
        d = outdir / db
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{n}.result.tsv").write_text("\n".join(results[0]["lines"]) + "\n", encoding="utf-8")
        (d / (f"{n}.explain.txt" if db == "mysql" else f"{n}.explain.json")).write_text(plan, encoding="utf-8")
        samples = [r["ms"] for r in results[1:]]
        timing = {"query": n, "db": db, "phase": a.phase, "runs": a.runs, "discarded_cold": results[0]["ms"],
                  "latency_ms": stats(samples), "samples_ms": samples}
        (d / f"{n}.timing.json").write_text(json.dumps(timing, indent=2) + "\n", encoding="utf-8")
        rows.append((n, db, len(results[0]["lines"]) - 1, results[0]["ms"], timing["latency_ms"]))
    (outdir / "meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    header = ["query", "db", "rows", "cold_ms", "min_ms", "p50_ms", "p95_ms", "max_ms"]
    table = [[n, db, str(r), f"{c:.1f}", *(f"{s[k]:.1f}" for k in ("min", "p50", "p95", "max"))]
             for n, db, r, c, s in sorted(rows)]
    (outdir / "summary.tsv").write_text("\n".join("\t".join(r) for r in [header] + table) + "\n")
    w = [max(len(x) for x in col) for col in zip(header, *table)]
    for r in [header] + table:
        print("  ".join(x.rjust(w[i]) if i > 1 else x.ljust(w[i]) for i, x in enumerate(r)))
    print(f"\nwritten to {outdir.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
