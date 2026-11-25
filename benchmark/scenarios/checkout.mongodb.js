// Class 2, flow 2: place an order (checkout). One multi-document transaction: reserve stock for every line
// ($inc quantity_reserved), insert the order with embedded lines, pending payment and shipping. Out of stock = the
// inventory validator rejects the update (session.updateOne returns nothing, so there is no matched count to read);
// WriteConflict is retried up to MAX_ATTEMPTS times.
// The order is built from a template order: Decimal128 / ObjectId / date values must keep their BSON type, which
// xk6-mongo only preserves for values read from the database (see docs/benchmark-operations.md). Needs
// orders.schema_version relaxed to int|long (python3 benchmark/reset_data.py --prepare-checkout) and k6 --no-deps.
// VARIANT=baseline: reserve stock first, template line order. VARIANT=optimized: insert the order first and take
// the contended inventory writes last, in (sku_id, warehouse_id) order.
// Reset the data before every run (python3 benchmark/reset_data.py). VERIFY=1 runs a fixed sequence once.
import mongo from "k6/x/mongo";
import { Counter } from "k6/metrics";
import { sleep } from "k6";
import { TPL, ALL_TEMPLATE_IDS, MAX_ATTEMPTS, VERIFY_CHECKOUTS, checkoutParams, loadOptions, orderHex, customerHex, idFromBytes } from "./lib/checkout_params.js";

export const options = loadOptions("checkout");
const VARIANT = __ENV.VARIANT || "baseline";
// MAINTAIN_AVAILABLE=1: the class 1 optimization stores inventory.quantity_available (on_hand - reserved) and indexes it;
// MongoDB cannot derive it, so every reservation must update it too (MySQL's generated column does this by itself).
const MAINTAIN = __ENV.MAINTAIN_AVAILABLE === "1";

const client = mongo.newClient(__ENV.MONGO_URI);
const okC = new Counter("checkout_ok"), retryC = new Counter("checkout_retry");
const stockOutC = new Counter("checkout_stock_out"), failedC = new Counter("checkout_failed"), errorC = new Counter("checkout_error");

// ObjectIds cannot be built in JS (a 12-number array is not an ObjectId); the server converts hex strings for us.
const mint = (hexes) => client.aggregate("dbperf", "categories",
  [{ $limit: 1 }, { $project: { _id: 0, ids: { $map: { input: hexes, as: "h", in: { $toObjectId: "$$h" } } } } }])[0].ids;

// VU init: template orders, customers, and a pool of fresh payment ids.
const templates = {};
for (const d of client.find("dbperf", "orders", { _id: { $in: mint(ALL_TEMPLATE_IDS.map(orderHex)) } }, { _id: 1 }, 100000)) {
  templates[idFromBytes(d._id)] = d;
}
const customers = {};
for (const d of client.find("dbperf", "customers", { _id: { $in: mint(TPL.customers.map(customerHex)) } }, { _id: 1 }, 100000)) {
  customers[idFromBytes(d._id)] = d;
}
const PAYMENT_IDS = 5000;
const payRun = Math.floor(Math.random() * 0xffffff).toString(16).padStart(6, "0");
const paymentIds = mint(Array.from({ length: PAYMENT_IDS }, (_, i) => "b1" + payRun + i.toString(16).padStart(16, "0")));
let payNext = 0;

function lineKey(l) { return { sku: idFromBytes(l.sku_id), wh: idFromBytes(l.warehouse_id) }; }

let phase = ""; // "reserve" while updating inventory, "insert" while writing the order: tells a stock-out from a bug

function reserve(s, lines) {
  phase = "reserve";
  for (const l of lines) {
    s.updateOne("dbperf", "inventory", { sku_id: l.sku_id, warehouse_id: l.warehouse_id }, { $inc: MAINTAIN ? { quantity_reserved: l.quantity, quantity_available: -l.quantity } : { quantity_reserved: l.quantity } });
  }
}

function attempt(p) {
  const t = templates[p.templateId], c = customers[p.customerId];
  const now = new Date();
  const order = {
    schema_version: t.schema_version, customer_id: c._id, status: "pending",
    shipping: { recipient_name: c.full_name, phone: c.phone, address: c.address },
    total_amount: t.total_amount, lines: t.lines,
    payments: [{ payment_id: paymentIds[payNext++ % PAYMENT_IDS], payment_method: p.method, amount: t.total_amount, status: "pending", created_at: now }],
    created_at: now,
  };
  if (p.method !== "cod") order.payment_due_at = new Date(now.getTime() + 86400000);
  const s = client.startSession();
  try {
    s.startTransaction();
    if (VARIANT !== "optimized") reserve(s, t.lines);
    phase = "insert";
    s.insert("dbperf", "orders", order);
    if (VARIANT === "optimized") {
      reserve(s, t.lines.slice().sort((a, b) => { const x = lineKey(a), y = lineKey(b); return (x.sku - y.sku) || (x.wh - y.wh); }));
    }
    s.commitTransaction();
  } catch (e) {
    try { s.abortTransaction(); } catch (_) { /* already aborted by the server */ }
    throw e;
  } finally {
    try { s.endSession(); } catch (_) { /* ignore */ }
  }
}

let logged = 0;
function checkout(p) {
  for (let tries = 1; ; tries++) {
    try { attempt(p); okC.add(1); return "ok"; }
    catch (e) {
      const m = String(e);
      if (/WriteConflict|TransientTransactionError/.test(m)) {  // write-write conflict: retry the transaction
        if (tries >= MAX_ATTEMPTS) { failedC.add(1); return "failed"; }
        retryC.add(1); sleep(0.002 * tries * (1 + p.jitter)); continue;
      }
      if (phase === "reserve" && /Document failed validation/.test(m)) { stockOutC.add(1); return "stock_out"; }  // inventory validator
      errorC.add(1);
      if (logged++ < 3) console.error("checkout error: " + m.replace(/\s+/g, " ").slice(0, 300));
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
