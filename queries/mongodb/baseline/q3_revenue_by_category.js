// q3 | Revenue by product category: units sold and line revenue from delivered orders, per category.
// Parameters: none (all delivered orders). Output columns: category_name, units_sold, revenue
const d = db.getSiblingDB((typeof process !== "undefined" && process.env.MONGO_DB) || "dbperf");

// Money arrives as a string from $toString; pad to exactly 2 decimals (same helper as seed/checks).
const money = (s) => {
  if (!s.includes(".")) return s + ".00";
  const frac = s.split(".")[1].length;
  return frac >= 2 ? s : s + "0".repeat(2 - frac);
};

const pipeline = [
  { $match: { status: "delivered" } },
  { $unwind: "$lines" },
  { $group: { _id: "$lines.sku_id", units: { $sum: "$lines.quantity" }, revenue: { $sum: "$lines.line_total" } } },
  // Step 1: SKU -> product (gives category_id).
  { $lookup: { from: "products", localField: "_id", foreignField: "skus.sku_id", as: "product" } },
  { $unwind: "$product" },
  { $group: { _id: "$product.category_id", units: { $sum: "$units" }, revenue: { $sum: "$revenue" } } },
  // Step 2: category_id -> category name.
  { $lookup: { from: "categories", localField: "_id", foreignField: "_id", as: "category" } },
  { $unwind: "$category" },
  { $sort: { revenue: -1, "category.name": 1 } },
  { $project: {
    _id: 0,
    category_name: "$category.name",
    units_sold: { $toString: "$units" },
    revenue: { $toString: { $round: ["$revenue", 2] } },
  } },
];

print(["category_name", "units_sold", "revenue"].join("\t"));
d.orders.aggregate(pipeline).forEach((r) => print([r.category_name, r.units_sold, money(r.revenue)].join("\t")));
