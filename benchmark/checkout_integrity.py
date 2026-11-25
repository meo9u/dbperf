#!/usr/bin/env python3
"""Check what a checkout run left in the database (run it after the run, before the next reset).

Per database it reads the orders created by the run (MySQL: order_id > 1,000,000, the seeded maximum; MongoDB: _id
below the seeded ObjectId range, because driver-generated ids start with a timestamp) and reports:
  new_orders / new_lines / new_payments / new_qty, and a fingerprint (sha1 of the sorted order contents that does not
  depend on ids or timestamps), so two databases fed the same sequence of checkouts can be compared.
With --ok N it also requires new_orders == new_payments == N (no lost or duplicated write), and with --seed-checks it
runs seed-check-<db> (inventory_reserved_ne_pending must stay 0, status_payment_consistency stays at the 562 already in
the data).

Usage:
  python3 benchmark/checkout_integrity.py --db mysql --ok 1234 [--seed-checks]
  python3 benchmark/checkout_integrity.py --db both --compare      # fingerprints of both databases must be equal
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reset_data import KNOWN_FAIL, run_checks  # noqa: E402
from run_class1 import mongo_eval, mysql  # noqa: E402

SEEDED_MAX_ORDER = 1000000


def state_mysql():
    rows = mysql(
        "SELECT o.customer_id, o.total_amount, p.payment_method, d.sku_id, d.warehouse_id, d.quantity, d.unit_price_snapshot, "
        "o.order_id FROM orders o JOIN order_detail d ON d.order_id = o.order_id JOIN payment p ON p.order_id = o.order_id "
        f"WHERE o.order_id > {SEEDED_MAX_ORDER};", "-N")
    lines = [r.split("\t") for r in rows.strip().split("\n") if r]
    orders = int(mysql(f"SELECT COUNT(*) FROM orders WHERE order_id > {SEEDED_MAX_ORDER};", "-N").strip())
    pays = int(mysql(f"SELECT COUNT(*) FROM payment WHERE order_id > {SEEDED_MAX_ORDER};", "-N").strip())
    return orders, pays, [l[:7] for l in lines]


def state_mongo():
    js = ('const d=db.getSiblingDB("dbperf");const lim=ObjectId("f00100000000000000000000");const num=(o)=>parseInt(o.toHexString().slice(-6),16);'
          'let orders=0,pays=0;d.orders.find({_id:{$lt:lim}}).forEach((o)=>{orders++;pays+=o.payments.length;'
          'o.lines.forEach((l)=>print([num(o.customer_id),o.total_amount.toString(),o.payments[0].payment_method,num(l.sku_id),'
          'num(l.warehouse_id),l.quantity,l.unit_price_snapshot.toString()].join("\\t")));});print("COUNTS\\t"+orders+"\\t"+pays);')
    out = [l for l in mongo_eval(js).strip().split("\n") if l]
    counts = [l for l in out if l.startswith("COUNTS\t")][0].split("\t")
    lines = [l.split("\t") for l in out if not l.startswith("COUNTS")]
    return int(counts[1]), int(counts[2]), lines


def summarize(db):
    orders, pays, lines = state_mysql() if db == "mysql" else state_mongo()
    norm = sorted("\t".join([r[0], f"{float(r[1]):.2f}", r[2], r[3], r[4], r[5], f"{float(r[6]):.2f}"]) for r in lines)
    return {"db": db, "new_orders": orders, "new_payments": pays, "new_lines": len(lines),
            "new_qty": sum(int(r[5]) for r in lines), "fingerprint": hashlib.sha1("\n".join(norm).encode()).hexdigest()[:16]}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", choices=["mysql", "mongodb", "both"], required=True)
    ap.add_argument("--ok", type=int, help="checkouts the run reported as successful (single database only)")
    ap.add_argument("--seed-checks", action="store_true")
    ap.add_argument("--compare", action="store_true", help="with --db both: fingerprints must be equal")
    a = ap.parse_args()
    dbs = ["mysql", "mongodb"] if a.db == "both" else [a.db]
    results, failed = [], False
    for db in dbs:
        s = summarize(db)
        results.append(s)
        print(json.dumps(s))
        if a.ok is not None and (s["new_orders"] != a.ok or s["new_payments"] != a.ok):
            print(f"FAIL {db}: new_orders={s['new_orders']} new_payments={s['new_payments']} but checkout_ok={a.ok}")
            failed = True
        if a.seed_checks:
            fails, out = run_checks("seed-check-" + ("mysql" if db == "mysql" else "mongodb"))
            unexpected = {k: v for k, v in fails.items() if KNOWN_FAIL.get(k) != v}
            print(f"  seed checks {db}: FAIL checks {fails or 'none'}")
            if unexpected:
                print(f"FAIL {db}: unexpected seed check failures {unexpected}")
                failed = True
    if a.compare and len(results) == 2:
        same = all(results[0][k] == results[1][k] for k in ("new_orders", "new_payments", "new_lines", "new_qty", "fingerprint"))
        print("compare:", "IDENTICAL" if same else "DIFFERENT")
        failed = failed or not same
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
