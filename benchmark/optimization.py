#!/usr/bin/env python3
"""Apply or roll back the Phase 5 schema optimizations (indexes, stored columns) on the running containers.

Usage: python3 benchmark/optimization.py apply|rollback [--db mysql|mongodb|both]
Files: schema/<db>/optimization/{01_indexes,99_rollback}.{sql,js}
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_class1 import CONTAINER, ROOT, mongo_file, mysql, sh  # noqa: E402

FILES = {"apply": "01_indexes", "rollback": "99_rollback"}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=FILES)
    ap.add_argument("--db", choices=["mysql", "mongodb", "both"], default="both")
    a = ap.parse_args()
    for db in ["mysql", "mongodb"] if a.db == "both" else [a.db]:
        path = ROOT / "schema" / db / "optimization" / (FILES[a.action] + (".sql" if db == "mysql" else ".js"))
        print(f"{a.action} {db}: {path.relative_to(ROOT)}", flush=True)
        if db == "mysql":
            mysql(path.read_text(encoding="utf-8"), "-t")
        else:
            sh(["docker", "cp", str(path), f"{CONTAINER['mongodb']}:/tmp/{path.name}"])
            print(mongo_file(f"/tmp/{path.name}").strip())
    print("done")


if __name__ == "__main__":
    main()
