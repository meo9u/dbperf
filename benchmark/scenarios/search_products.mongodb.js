// Class 2, flow 1: search and filter products (category, optional colour / price band / name keyword), paginated.
// Baseline: only the unique indexes. Run: k6 run -e VUS=16 -e DURATION=30s /scripts/search_products.mongodb.js
// VERIFY=1 runs fixed requests once and prints one line per request, to diff against the MySQL script.
import mongo from "k6/x/mongo";
import { Trend, Counter } from "k6/metrics";
import { PAGE_SIZE, searchParams, money, VERIFY_CASES, loadOptions } from "./lib/search_params.js";

export const options = loadOptions("search_products");

// VARIANT=baseline (default): the request as first written. VARIANT=optimized: adds a pre-unwind $match with $elemMatch
// so the multikey index (idx_products_search) prunes products before $unwind; results are identical.
const VARIANT = __ENV.VARIANT || "baseline";

const client = mongo.newClient(__ENV.MONGO_URI);
const latency = new Trend("search_latency", true);
const rowsReturned = new Counter("search_rows");

// Category ids are read in the init stage of every VU (19 small documents), not in setup(): setup() data goes
// through JSON, which would turn the driver's ObjectIds into plain strings that no longer match category_id.
const categoryIds = {};
for (const c of client.find("dbperf", "categories", {})) categoryIds[c.name] = c._id;

function search(p) {
  const skuMatch = { "skus.status": "active" };
  if (p.price) skuMatch["skus.current_price"] = { $gte: p.price[0], $lte: p.price[1] };
  if (p.color) skuMatch["skus.variant_attributes.color"] = p.color;
  const productMatch = { category_id: categoryIds[p.category], status: "active" };
  if (p.keyword) productMatch.name = { $regex: p.keyword, $options: "i" };
  if (VARIANT === "optimized") {
    const elem = { status: "active" };
    if (p.price) elem.current_price = { $gte: p.price[0], $lte: p.price[1] };
    if (p.color) elem["variant_attributes.color"] = p.color;
    productMatch.skus = { $elemMatch: elem };
  }
  return client.aggregate("dbperf", "products", [
    { $match: productMatch },
    { $unwind: "$skus" },
    { $match: skuMatch },
    { $sort: { "skus.sku_code": 1 } },
    { $skip: p.page * PAGE_SIZE },
    { $limit: PAGE_SIZE },
    { $project: { _id: 0, sku_code: "$skus.sku_code", name: 1, price: { $toString: "$skus.current_price" }, color: "$skus.variant_attributes.color" } },
  ]);
}

export default function () {
  if (__ENV.VERIFY) {
    for (let i = 0; i < VERIFY_CASES; i++) {
      const rows = search(searchParams(1, i));
      console.log("CASE|" + i + "|" + JSON.stringify(rows.map((r) => [r.sku_code, r.name, money(r.price), r.color])));
    }
    return;
  }
  const t0 = Date.now();
  const rows = search(searchParams(__VU, __ITER));
  latency.add(Date.now() - t0);
  rowsReturned.add(rows.length);
}
