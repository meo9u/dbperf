// Data-logic checks on MongoDB: same names, severities and meaning as mysql_logic.sql.
// Prints "name<TAB>severity<TAB>violations". MongoDB has no joins or foreign keys, so the
// collections are read once into memory (about 100K orders in the pilot set).
const d = db.getSiblingDB("dbperf");
const hex = (id) => id.toHexString();
const cents = (v) => Math.round(Number(v.toString()) * 100);

const res = new Map();
const def = (sev, ...names) => names.forEach((n) => res.set(n, [sev, 0]));
const hit = (n) => { res.get(n)[1]++; };
def("FAIL", "fk_line_sku", "fk_line_warehouse", "fk_order_customer", "fk_product_category", "fk_inventory_refs",
  "order_zero_lines", "order_has_no_payment", "payments_over_5_per_order", "dup_sku_in_order", "total_ne_line_sum",
  "payment_sum_ne_total", "order_total_not_positive", "line_price_not_positive", "customer_phone_format",
  "shipping_phone_format", "customer_email_format", "time_order_before_customer", "time_payment_before_order",
  "time_order_before_product", "status_payment_consistency", "inventory_reserved_gt_on_hand",
  "inventory_reserved_ne_pending");
def("WARN", "stale_pending_orders", "stale_shipped_orders", "customer_updated_before_created", "product_updated_before_created");
def("INFO", "line_price_differs_from_catalog", "line_on_inactive_sku", "sku_never_ordered",
  "cancelled_line_has_warehouse", "recipient_differs_from_customer");

const phone = /^\+[0-9]{5,16}$/;
const email = /^[^ @]+@[^ @]+\.[^ @]+$/;
const payOk = {
  pending: ["pending"], shipped: ["success"], delivered: ["success"],
  cancelled: ["failed", "refunded", "pending"], returned: ["refunded"],
};

const categories = new Set(d.categories.find({}, { _id: 1 }).toArray().map((c) => hex(c._id)));
const warehouses = new Set(d.warehouses.find({}, { _id: 1 }).toArray().map((w) => hex(w._id)));
const customers = new Map();
d.customers.find().forEach((c) => {
  customers.set(hex(c._id), { created: c.created_at, name: c.full_name });
  if (c.phone !== undefined && !phone.test(c.phone)) hit("customer_phone_format");
  if (!email.test(c.email)) hit("customer_email_format");
  if (c.updated_at < c.created_at) hit("customer_updated_before_created");
});
const skus = new Map();
d.products.find().forEach((p) => {
  if (!categories.has(hex(p.category_id))) hit("fk_product_category");
  if (p.updated_at < p.created_at) hit("product_updated_before_created");
  p.skus.forEach((s) => skus.set(hex(s.sku_id), { created: p.created_at, status: s.status, price: cents(s.current_price) }));
});

const maxCreated = d.orders.find({}, { created_at: 1 }).sort({ created_at: -1 }).limit(1).next().created_at;
const cutoff = new Date(maxCreated.getTime() - 30 * 86400000);
const sold = new Set();
const pendingQty = new Map();

d.orders.find().batchSize(5000).forEach((o) => {
  const cust = customers.get(hex(o.customer_id));
  if (!cust) hit("fk_order_customer");
  else {
    if (o.created_at < cust.created) hit("time_order_before_customer");
    if (o.shipping.recipient_name !== cust.name) hit("recipient_differs_from_customer");
  }
  if (!phone.test(o.shipping.phone)) hit("shipping_phone_format");
  const total = cents(o.total_amount);
  if (total <= 0) hit("order_total_not_positive");
  if (o.status === "pending" && o.created_at < cutoff) hit("stale_pending_orders");
  if (o.status === "shipped" && o.created_at < cutoff) hit("stale_shipped_orders");

  if (o.lines.length === 0) hit("order_zero_lines");
  const seen = new Set(), dup = new Set();
  let sum = 0, beforeProduct = false;
  o.lines.forEach((l) => {
    const sk = hex(l.sku_id), s = skus.get(sk), lt = cents(l.line_total), up = cents(l.unit_price_snapshot);
    sum += lt;
    sold.add(sk);
    if (!s) hit("fk_line_sku");
    else {
      if (s.created > o.created_at) beforeProduct = true;
      if (up !== s.price) hit("line_price_differs_from_catalog");
      if (s.status === "inactive") hit("line_on_inactive_sku");
    }
    if (l.warehouse_id !== undefined) {
      const wk = hex(l.warehouse_id);
      if (!warehouses.has(wk)) hit("fk_line_warehouse");
      if (o.status === "cancelled") hit("cancelled_line_has_warehouse");
      if (o.status === "pending") pendingQty.set(sk + "|" + wk, (pendingQty.get(sk + "|" + wk) || 0) + Number(l.quantity));
    }
    if (up <= 0) hit("line_price_not_positive");
    if (seen.has(sk) && !dup.has(sk)) { dup.add(sk); hit("dup_sku_in_order"); }
    seen.add(sk);
  });
  if (beforeProduct) hit("time_order_before_product");
  if (o.lines.length > 0 && sum !== total) hit("total_ne_line_sum");

  if (o.payments.length === 0) hit("order_has_no_payment");
  if (o.payments.length > 5) hit("payments_over_5_per_order");
  let paid = 0;
  o.payments.forEach((p) => {
    paid += cents(p.amount);
    if (p.created_at < o.created_at) hit("time_payment_before_order");
    if (!payOk[o.status].includes(p.status)) hit("status_payment_consistency");
  });
  if (o.payments.length > 0 && paid !== total) hit("payment_sum_ne_total");
});

const invKeys = new Set();
d.inventory.find().forEach((i) => {
  const sk = hex(i.sku_id), wk = hex(i.warehouse_id), key = sk + "|" + wk;
  invKeys.add(key);
  if (!skus.has(sk) || !warehouses.has(wk)) hit("fk_inventory_refs");
  // Number(): a field changed by $inc from a client that sends int64 (k6) is a Long, not a JS number.
  if (Number(i.quantity_reserved) > Number(i.quantity_on_hand)) hit("inventory_reserved_gt_on_hand");
  if (Number(i.quantity_reserved) !== (pendingQty.get(key) || 0)) hit("inventory_reserved_ne_pending");
});
for (const key of pendingQty.keys()) if (!invKeys.has(key)) hit("inventory_reserved_ne_pending");
for (const sk of skus.keys()) if (!sold.has(sk)) hit("sku_never_ordered");

for (const [name, [sev, n]] of res) print(name + "\t" + sev + "\t" + n);
