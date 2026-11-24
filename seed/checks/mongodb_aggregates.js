// Business aggregates on MongoDB, printed as "key<TAB>value" lines identical in key and format to
// mysql_aggregates.sql (money with 2 decimals). The runner diffs the two outputs.
const d = db.getSiblingDB("dbperf");

const money = (v) => {
  if (v === null || v === undefined) return "0.00";
  let s = v.toString();
  if (!s.includes(".")) return s + ".00";
  const frac = s.split(".")[1].length;
  return frac >= 2 ? s : s + "0".repeat(2 - frac);
};
const out = (k, v) => print(k + "\t" + v);

d.orders.aggregate([{ $group: { _id: "$status", n: { $sum: 1 }, s: { $sum: "$total_amount" } } }])
  .forEach((r) => out("orders_by_status|" + r._id, r.n + "|" + money(r.s)));

d.orders.aggregate([{ $group: {
  _id: { $dateToString: { format: "%Y-%m", date: "$created_at", timezone: "UTC" } },
  n: { $sum: 1 }, s: { $sum: "$total_amount" } } }])
  .forEach((r) => out("revenue_by_month|" + r._id, r.n + "|" + money(r.s)));

const perCustomer = {};
let customersWithOrders = 0;
d.orders.aggregate([{ $group: { _id: "$customer_id", n: { $sum: 1 } } }, { $group: { _id: "$n", c: { $sum: 1 } } }])
  .forEach((r) => { perCustomer[r._id] = r.c; customersWithOrders += r.c; });
perCustomer[0] = d.customers.countDocuments() - customersWithOrders;
for (const [n, c] of Object.entries(perCustomer)) if (c > 0) out("customers_by_order_count|" + n, c);

const hist = (field, key) => d.orders.aggregate([{ $group: { _id: { $size: field }, c: { $sum: 1 } } }])
  .forEach((r) => out(key + "|" + r._id, r.c));
hist("$payments", "orders_by_payment_count");
hist("$lines", "orders_by_line_count");

const lt = d.orders.aggregate([{ $unwind: "$lines" }, { $group: {
  _id: null, n: { $sum: 1 }, q: { $sum: "$lines.quantity" }, s: { $sum: "$lines.line_total" },
  skus: { $addToSet: "$lines.sku_id" } } }]).toArray()[0];
out("lines_total", lt.n + "|" + lt.q + "|" + money(lt.s) + "|" + lt.skus.length);

d.orders.aggregate([{ $unwind: "$payments" }, { $group: {
  _id: { m: "$payments.payment_method", s: "$payments.status" },
  n: { $sum: 1 }, a: { $sum: "$payments.amount" } } }])
  .forEach((r) => out("payments|" + r._id.m + "|" + r._id.s, r.n + "|" + money(r.a)));

const inv = d.inventory.aggregate([{ $group: { _id: null, n: { $sum: 1 }, h: { $sum: "$quantity_on_hand" }, r: { $sum: "$quantity_reserved" } } }]).toArray()[0];
out("inventory_total", inv.n + "|" + inv.h + "|" + inv.r);

d.products.aggregate([{ $unwind: "$skus" }, { $group: { _id: "$skus.status", n: { $sum: 1 }, p: { $sum: "$skus.current_price" } } }])
  .forEach((r) => out("sku_by_status|" + r._id, r.n + "|" + money(r.p)));
