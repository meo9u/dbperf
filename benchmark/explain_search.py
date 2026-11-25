#!/usr/bin/env python3
"""Save query plans of representative search_products requests (class 2) for the current schema state.

For each case it writes the plan and prints the time and the rows / documents examined:
  MySQL   EXPLAIN ANALYZE of the scenario's SQL          -> results/<phase>/load/search_products.explain.mysql.<case>.txt
  MongoDB explain("executionStats") of the pipeline       -> results/<phase>/load/search_products.explain.mongodb.<case>.json
Use --variant optimized for the MongoDB pipeline with the pre-unwind $elemMatch (MySQL has no request rewrite).

Usage: python3 benchmark/explain_search.py --phase baseline_r2 [--variant baseline|optimized]
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_class1 import ROOT, mongo_eval, mysql  # noqa: E402

CASES = {  # category, colour, price band, keyword, page
    "big_category": ("Garment Upper body", None, None, None, 0),
    "filtered": ("Garment Upper body", "Light Pink", (50, 500), None, 3),
    "keyword": ("Swimwear", None, None, "top", 0),
}


def mysql_sql(c):
    cat, color, price, kw, page = c
    q = ("SELECT s.sku_code, p.name, s.current_price, JSON_UNQUOTE(JSON_EXTRACT(s.variant_attributes, '$.color')) AS color "
         "FROM sku s JOIN product p ON p.product_id = s.product_id "
         f"WHERE p.category_id = (SELECT category_id FROM category WHERE name = '{cat}') AND p.status = 'active' AND s.status = 'active'")
    if price:
        q += f" AND s.current_price BETWEEN {price[0]} AND {price[1]}"
    if color:
        q += f" AND JSON_UNQUOTE(JSON_EXTRACT(s.variant_attributes, '$.color')) = '{color}'"
    if kw:
        q += f" AND p.name LIKE '%{kw}%'"
    return q + f" ORDER BY s.sku_code ASC LIMIT 20 OFFSET {page * 20}"


def mongo_js(c, variant):
    cat, color, price, kw, page = c
    sku = {"skus.status": "active"}
    elem = {"status": "active"}
    if price:
        sku["skus.current_price"] = {"$gte": price[0], "$lte": price[1]}
        elem["current_price"] = {"$gte": price[0], "$lte": price[1]}
    if color:
        sku["skus.variant_attributes.color"] = color
        elem["variant_attributes.color"] = color
    pm = {"category_id": "__CAT__", "status": "active"}
    if kw:
        pm["name"] = {"$regex": kw, "$options": "i"}
    if variant == "optimized":
        pm["skus"] = {"$elemMatch": elem}
    pipeline = [{"$match": pm}, {"$unwind": "$skus"}, {"$match": sku}, {"$sort": {"skus.sku_code": 1}},
                {"$skip": page * 20}, {"$limit": 20}]
    js = json.dumps(pipeline).replace('"__CAT__"', "cat")
    return ('const d=db.getSiblingDB("dbperf");const cat=d.categories.findOne({name:"%s"})._id;'
            'const e=d.products.explain("executionStats").aggregate(%s);print(EJSON.stringify(e,null,2));' % (cat, js))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--phase", required=True)
    ap.add_argument("--variant", default="baseline", choices=["baseline", "optimized"])
    a = ap.parse_args()
    out = ROOT / "benchmark" / "results" / a.phase / "load"
    out.mkdir(parents=True, exist_ok=True)
    for name, case in CASES.items():
        plan = mysql("EXPLAIN ANALYZE " + mysql_sql(case) + ";\n").split("\n", 1)[1].rstrip("\n") + "\n"
        plan = plan.replace("\\n", "\n")
        (out / f"search_products.explain.mysql.{name}.txt").write_text(plan, encoding="utf-8")
        top = re.search(r"actual time=[\d.]+\.\.([\d.]+)", plan)
        first_scan = [l.strip() for l in plan.splitlines() if re.search(r"(Index (range )?scan|Table scan|Index lookup|Covering)", l)][:1]
        print(f"mysql   {name:13s} {top.group(1) if top else '?':>8s} ms  {first_scan[0][:90] if first_scan else ''}")
        text = mongo_eval(mongo_js(case, a.variant))
        (out / f"search_products.explain.mongodb.{name}.json").write_text(text.strip() + "\n", encoding="utf-8")
        stages = re.findall(r'"stage": "(\w+)"', text)[:3]
        docs = re.search(r'"totalDocsExamined": (\d+)', text)
        ms = re.search(r'"executionTimeMillis": (\d+)', text)
        print(f"mongodb {name:13s} {ms.group(1) if ms else '?':>8s} ms  docs={docs.group(1) if docs else '?'} stages={','.join(stages)}")
    print(f"written to {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
