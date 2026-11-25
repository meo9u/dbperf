// q1 | Revenue by month: number of delivered orders and total revenue per calendar month (UTC).
// Parameters: none (all delivered orders). Output columns: order_month, order_count, revenue
const d = db.getSiblingDB((typeof process !== "undefined" && process.env.MONGO_DB) || "dbperf");

// Money arrives as a string from $toString; pad to exactly 2 decimals (same helper as seed/checks).
const money = (s) => {
  if (!s.includes(".")) return s + ".00";
  const frac = s.split(".")[1].length;
  return frac >= 2 ? s : s + "0".repeat(2 - frac);
};

const pipeline = [
  { $match: { status: "delivered" } },
  { $group: {
    _id: { $dateToString: { format: "%Y-%m", date: "$created_at", timezone: "UTC" } },
    order_count: { $sum: 1 },
    revenue: { $sum: "$total_amount" },
  } },
  { $sort: { _id: 1 } },
  { $project: {
    _id: 0,
    order_month: "$_id",
    order_count: { $toString: "$order_count" },
    revenue: { $toString: { $round: ["$revenue", 2] } },
  } },
];

print(["order_month", "order_count", "revenue"].join("\t"));
d.orders.aggregate(pipeline).forEach((r) => print([r.order_month, r.order_count, money(r.revenue)].join("\t")));
