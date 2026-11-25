// q2 | Top SKUs by units sold in delivered orders created in [FROM_DATE, TO_DATE) (UTC), top TOP_N.
// Parameters: FROM_DATE, TO_DATE, TOP_N. Output columns: sku_code, units_sold, revenue
const FROM_DATE = new Date("2019-01-01T00:00:00Z"); // inclusive
const TO_DATE = new Date("2020-01-01T00:00:00Z"); // exclusive
const TOP_N = 20;
const d = db.getSiblingDB((typeof process !== "undefined" && process.env.MONGO_DB) || "dbperf");

// Money arrives as a string from $toString; pad to exactly 2 decimals (same helper as seed/checks).
const money = (s) => {
  if (!s.includes(".")) return s + ".00";
  const frac = s.split(".")[1].length;
  return frac >= 2 ? s : s + "0".repeat(2 - frac);
};

// Phase 5: status matches 96% of orders, so the status-leading indexes made the planner choose a slower index scan + FETCH; force the collection scan.
const OPTS = { hint: { $natural: 1 } };

const pipeline = [
  { $match: { status: "delivered", created_at: { $gte: FROM_DATE, $lt: TO_DATE } } },
  { $unwind: "$lines" },
  { $group: { _id: "$lines.sku_id", units: { $sum: "$lines.quantity" }, revenue: { $sum: "$lines.line_total" } } },
  { $lookup: { from: "products", localField: "_id", foreignField: "skus.sku_id", as: "product" } },
  { $unwind: "$product" },
  { $set: { sku: { $first: { $filter: { input: "$product.skus", cond: { $eq: ["$$this.sku_id", "$_id"] } } } } } },
  { $sort: { units: -1, "sku.sku_code": 1 } },
  { $limit: TOP_N },
  { $project: {
    _id: 0,
    sku_code: "$sku.sku_code",
    units_sold: { $toString: "$units" },
    revenue: { $toString: { $round: ["$revenue", 2] } },
  } },
];

print(["sku_code", "units_sold", "revenue"].join("\t"));
d.orders.aggregate(pipeline, OPTS).forEach((r) => print([r.sku_code, r.units_sold, money(r.revenue)].join("\t")));
