// Class 2, flow 2: place an order (checkout). One transaction: reserve stock for every line, insert the order, its
// lines and a pending payment. Out of stock = CHECK violation (error 3819); deadlock / lock timeout (1213 / 1205)
// is retried up to MAX_ATTEMPTS times. xk6-sql has no transaction API: START TRANSACTION / COMMIT run on the same
// pooled connection (verified with 32 VUs, see docs/benchmark-operations.md).
// VARIANT=baseline: reserve stock first (template line order), one INSERT per order line. VARIANT=optimized: write the
// order first (one multi-row INSERT for the lines) and take the contended inventory row locks last, in
// (sku_id, warehouse_id) order.
// Reset the data before every run (python3 benchmark/reset_data.py). VERIFY=1 runs a fixed sequence once.
import sql from "k6/x/sql";
import driver from "k6/x/sql/driver/mysql";
import { Counter } from "k6/metrics";
import { sleep } from "k6";
import { TPL, ALL_TEMPLATE_IDS, MAX_ATTEMPTS, VERIFY_CHECKOUTS, checkoutParams, loadOptions, text, byRow } from "./lib/checkout_params.js";

export const options = loadOptions("checkout");
const VARIANT = __ENV.VARIANT || "baseline";

// MYSQL_INTERPOLATE=1: let the driver substitute the parameters on the client (one round trip per statement) instead
// of prepare + execute + close on the server (default; 3 round trips). Used to measure the cost of that harness choice.
const dsn = __ENV.MYSQL_DSN + (__ENV.MYSQL_INTERPOLATE === "1" ? (__ENV.MYSQL_DSN.includes("?") ? "&" : "?") + "interpolateParams=true" : "");
const db = sql.open(driver, dsn);
const okC = new Counter("checkout_ok"), retryC = new Counter("checkout_retry");
const stockOutC = new Counter("checkout_stock_out"), failedC = new Counter("checkout_failed"), errorC = new Counter("checkout_error");

// VU init: template orders (lines, total) and customers (shipping data) for the fixed id lists.
const templates = {};
for (const r of db.query(
  "SELECT d.order_id, d.sku_id, d.warehouse_id, d.quantity, d.unit_price_snapshot AS price, o.total_amount AS total " +
  "FROM order_detail d JOIN orders o ON o.order_id = d.order_id WHERE d.order_id IN (" + ALL_TEMPLATE_IDS.join(",") + ") " +
  "ORDER BY d.order_detail_id")) {
  const id = Number(r.order_id);
  (templates[id] = templates[id] || { total: text(r.total), lines: [] }).lines.push(
    { sku: Number(r.sku_id), wh: Number(r.warehouse_id), qty: Number(r.quantity), price: text(r.price) });
}
const customers = {};
for (const r of db.query("SELECT customer_id, full_name, phone, address FROM customer WHERE customer_id IN (" + TPL.customers.join(",") + ")")) {
  customers[Number(r.customer_id)] = { name: text(r.full_name), phone: text(r.phone), address: text(r.address) };
}

function reserve(lines) {
  for (const l of lines) {
    db.exec("UPDATE inventory SET quantity_reserved = quantity_reserved + ? WHERE sku_id = ? AND warehouse_id = ?", l.qty, l.sku, l.wh);
  }
}

function attempt(p) {
  const t = templates[p.templateId], c = customers[p.customerId];
  db.exec("START TRANSACTION");
  try {
    if (VARIANT !== "optimized") reserve(t.lines);
    const o = db.exec("INSERT INTO orders (customer_id, status, shipping_recipient_name, shipping_phone, shipping_address, total_amount, created_at) " +
                      "VALUES (?, 'pending', ?, ?, ?, ?, NOW())", p.customerId, c.name, c.phone, c.address, t.total);
    const orderId = o.lastInsertId();   // a method in xk6-sql
    if (VARIANT === "optimized") {   // one multi-row INSERT: fewer round trips, shorter transaction
      const args = [];
      for (const l of t.lines) args.push(orderId, l.sku, l.price, l.qty, l.wh);
      db.exec("INSERT INTO order_detail (order_id, sku_id, unit_price_snapshot, quantity, warehouse_id) VALUES " +
              t.lines.map(() => "(?, ?, ?, ?, ?)").join(", "), ...args);
    } else {
      for (const l of t.lines) {
        db.exec("INSERT INTO order_detail (order_id, sku_id, unit_price_snapshot, quantity, warehouse_id) VALUES (?, ?, ?, ?, ?)", orderId, l.sku, l.price, l.qty, l.wh);
      }
    }
    db.exec("INSERT INTO payment (order_id, payment_method, amount, status) VALUES (?, ?, ?, 'pending')", orderId, p.method, t.total);
    if (VARIANT === "optimized") reserve(t.lines.slice().sort(byRow));
    db.exec("COMMIT");
  } catch (e) {
    try { db.exec("ROLLBACK"); } catch (_) { /* connection already lost */ }
    throw e;
  }
}

let logged = 0;
function checkout(p) {
  for (let tries = 1; ; tries++) {
    try { attempt(p); okC.add(1); return "ok"; }
    catch (e) {
      const m = String(e);
      if (/Error (1213|1205)\b/.test(m)) {                      // deadlock / lock wait timeout: retry
        if (tries >= MAX_ATTEMPTS) { failedC.add(1); return "failed"; }
        retryC.add(1); sleep(0.002 * tries * (1 + p.jitter)); continue;
      }
      if (/Error 3819\b/.test(m)) { stockOutC.add(1); return "stock_out"; }   // chk_inventory_quantity_reserved
      errorC.add(1);
      if (logged++ < 3) console.error("checkout error: " + m.slice(0, 300));
      return "error";
    }
  }
}

export default function () {
  if (__ENV.VERIFY) {
    const res = { ok: 0, stock_out: 0, failed: 0, error: 0 };
    for (let i = 0; i < VERIFY_CHECKOUTS; i++) res[checkout(checkoutParams(1, i))]++;
    console.log("VERIFY_DONE " + JSON.stringify(res));
    return;
  }
  checkout(checkoutParams(__VU, __ITER));
}
