// Class 2, flow 1: search and filter products (category, optional colour / price band / name keyword), paginated.
// Baseline: no indexes beyond the schema. Run: k6 run -e VUS=16 -e DURATION=30s /scripts/search_products.mysql.js
// VERIFY=1 runs fixed requests once and prints one line per request, to diff against the MongoDB script.
import sql from "k6/x/sql";
import driver from "k6/x/sql/driver/mysql";
import { Trend, Counter } from "k6/metrics";
import { PAGE_SIZE, searchParams, money, text, VERIFY_CASES, loadOptions } from "./lib/search_params.js";

export const options = loadOptions("search_products");

// VARIANT=baseline (default) or optimized run the same query: for MySQL the optimization is the indexes / generated
// column (schema/mysql/optimization/search_01_indexes.sql), no request rewrite helped. VARIANT=hint is the join-order
// experiment (see search()).
const VARIANT = __ENV.VARIANT || "baseline";

const db = sql.open(driver, __ENV.MYSQL_DSN);
const latency = new Trend("search_latency", true);
const rowsReturned = new Counter("search_rows");

// Category ids are read once per VU in the init stage, the same way as in the MongoDB script.
const categoryIds = {};
for (const r of db.query("SELECT category_id, name FROM category")) categoryIds[text(r.name)] = Number(r.category_id);

function search(p) {
  // VARIANT=hint (an experiment, measured slower overall than the plain query): with a colour / price / keyword filter
  // force the product-first join order instead of the optimizer's default (scan sku by sku_code until 20 rows match).
  const hint = VARIANT === "hint" && (p.color || p.price || p.keyword) ? "/*+ JOIN_ORDER(p, s) */ " : "";
  let q = "SELECT " + hint + "s.sku_code, p.name, s.current_price, JSON_UNQUOTE(JSON_EXTRACT(s.variant_attributes, '$.color')) AS color " +
          "FROM sku s JOIN product p ON p.product_id = s.product_id " +
          "WHERE p.category_id = ? AND p.status = 'active' AND s.status = 'active'";
  const args = [categoryIds[p.category]];
  if (p.price) { q += " AND s.current_price BETWEEN ? AND ?"; args.push(p.price[0], p.price[1]); }
  if (p.color) { q += " AND JSON_UNQUOTE(JSON_EXTRACT(s.variant_attributes, '$.color')) = ?"; args.push(p.color); }
  if (p.keyword) { q += " AND p.name LIKE ?"; args.push("%" + p.keyword + "%"); }
  q += " ORDER BY s.sku_code ASC LIMIT ? OFFSET ?";
  args.push(PAGE_SIZE, p.page * PAGE_SIZE);
  return db.query(q, ...args);
}

export default function () {
  if (__ENV.VERIFY) {
    for (let i = 0; i < VERIFY_CASES; i++) {
      const rows = search(searchParams(1, i));
      console.log("CASE|" + i + "|" + JSON.stringify(rows.map((r) => [text(r.sku_code), text(r.name), money(text(r.current_price)), text(r.color)])));
    }
    return;
  }
  const t0 = Date.now();
  const rows = search(searchParams(__VU, __ITER));
  latency.add(Date.now() - t0);
  rowsReturned.add(rows.length);
}
