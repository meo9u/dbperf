#!/usr/bin/env python3
"""Put both databases back into the seeded state before a write run (checkout), and optionally verify it.

Steps: reload MySQL and MongoDB from seed/data (seed-mysql, seed-mongodb; they keep indexes and validators and verify
row counts against seed/data/manifest.json), ANALYZE TABLE on every MySQL table (statistics decide MySQL plans, see
docs/bao-cao-ket-qua-class2-search.md section 5), read-only warm-up of the tables checkout touches, and with --check
the seed logic checks (seed-check-*), which must show only the FAIL already present in the data
(status_payment_consistency = 562) and identical aggregates between the two databases.

--prepare-checkout (checkout runs) adds 100,000 units to every inventory row in both databases, so no checkout fails
for lack of stock, and relaxes orders.schema_version from int to int|long in MongoDB: xk6-mongo exports every JS
integer as int64, which the original validator rejects. Restore the original validators afterwards with
`python3 benchmark/reset_data.py --restore-validators` (or any `docker compose up` / `run` that starts
mongodb-schema-init). Run k6 with --no-deps so the relaxed validator is not reset between runs.

Usage:
  python3 benchmark/reset_data.py [--check] [--prepare-checkout]
  python3 benchmark/reset_data.py --restore-validators
Write runs (checkout) must start from the baseline schema: roll back optimization sets first, or re-apply them after.
"""
import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_class1 import ROOT, mongo_eval, mysql  # noqa: E402

KNOWN_FAIL = {"status_payment_consistency": 562}  # already in the loaded data, identical in both databases
TABLES = "category, customer, inventory, order_detail, orders, payment, product, sku, warehouse"


def compose(*args):
    p = subprocess.run(["docker", "compose", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    return p.returncode, p.stdout + p.stderr


def step(label, fn):
    t0 = time.time()
    out = fn()
    print(f"  {label:<34s} {time.time() - t0:6.1f} s", flush=True)
    return out


def seed(service):
    rc, out = compose("--profile", "seed", "run", "--rm", "--no-deps", service)
    if rc != 0 or "MISMATCH" in out.upper():
        sys.exit(f"{service} failed (exit {rc}):\n{out[-1500:]}")
    return out


def run_checks(service):
    rc, out = compose("--profile", "seed", "run", "--rm", "--no-deps", service)
    fails = {m.group(1): int(m.group(2)) for m in re.finditer(r"^\s+FAIL\s+(\S+)\s+(\d+)\s*$", out, re.M)}
    return fails, out


def restore_validators():
    rc, out = compose("run", "--rm", "--no-deps", "mongodb-schema-init")
    if rc != 0:
        sys.exit(f"mongodb-schema-init failed:\n{out[-800:]}")
    print("original MongoDB validators restored")


def prepare_checkout():
    js = ('const d=db.getSiblingDB("dbperf");const v=d.getCollectionInfos({name:"orders"})[0].options.validator;'
          'v.$and[0].$jsonSchema.properties.schema_version={bsonType:["int","long"],minimum:1};'
          'print(d.runCommand({collMod:"orders",validator:v,validationLevel:"strict",validationAction:"error"}).ok)')
    if mongo_eval(js).strip() != "1":
        sys.exit("could not relax orders.schema_version")


def warm_up(db):
    """Read what checkout touches so the caches are not empty right after the reload."""
    if db == "mysql":
        mysql("SELECT COUNT(*), SUM(quantity_reserved) FROM inventory; SELECT COUNT(*) FROM sku; SELECT COUNT(*) FROM customer;"
              " SELECT COUNT(*) FROM product; SELECT COUNT(*) FROM warehouse; SELECT MAX(order_id) FROM orders;", "-N")
    else:
        mongo_eval('const d=db.getSiblingDB("dbperf");d.inventory.countDocuments({});d.customers.countDocuments({});'
                   'd.products.countDocuments({});d.orders.find({},{_id:1}).sort({_id:-1}).limit(1).toArray();')


AMPLE_STOCK = 100000  # units added to every inventory row for checkout runs


def reset_db(db, prepare=False):
    """Reload one database from seed/data (what a write run needs before every level).
    prepare=True is for checkout runs: relax the MongoDB orders validator and add ample stock to this database."""
    if db == "mysql":
        step("seed-mysql (truncate + load)", lambda: seed("seed-mysql"))
        step("ANALYZE TABLE (MySQL, all tables)", lambda: mysql(f"ANALYZE TABLE {TABLES};"))
        if prepare:
            step("add stock (MySQL inventory)", lambda: mysql(f"UPDATE inventory SET quantity_on_hand = quantity_on_hand + {AMPLE_STOCK};"))
    else:
        step("seed-mongodb (empty + load)", lambda: seed("seed-mongodb"))
        if prepare:
            step("relax orders.schema_version", prepare_checkout)
            step("add stock (MongoDB inventory)", lambda: mongo_eval(
                f'db.getSiblingDB("dbperf").inventory.updateMany({{}},{{$inc:{{quantity_on_hand:{AMPLE_STOCK}}}}}).modifiedCount'))
    step("read-only warm-up", lambda: warm_up(db))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="run seed-check-mysql and seed-check-mongodb afterwards")
    ap.add_argument("--prepare-checkout", action="store_true", help="relax orders.schema_version for xk6-mongo inserts")
    ap.add_argument("--restore-validators", action="store_true", help="only restore the original MongoDB validators")
    a = ap.parse_args()
    if a.restore_validators:
        restore_validators()
        return
    t0 = time.time()
    print("reset to the seeded state:")
    reset_db("mysql", prepare=a.prepare_checkout)
    reset_db("mongodb", prepare=a.prepare_checkout)
    if a.check:
        for svc in ("seed-check-mysql", "seed-check-mongodb"):
            fails, out = step(svc, lambda s=svc: run_checks(s))
            unexpected = {k: v for k, v in fails.items() if KNOWN_FAIL.get(k) != v}
            print(f"    FAIL checks: {fails or 'none'}")
            if unexpected:
                sys.exit(f"unexpected FAIL checks after reset: {unexpected}\n{out[-1200:]}")
        if "aggregates identical" not in out:
            sys.exit("MySQL and MongoDB aggregates are not identical after reset:\n" + out[-1200:])
        print("    MySQL and MongoDB aggregates identical")
    print(f"done in {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
