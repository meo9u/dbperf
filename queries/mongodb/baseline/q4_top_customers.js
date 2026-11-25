// q4 | Top customers by total spend on delivered orders, top TOP_N.
// Parameters: TOP_N. Output columns: email, order_count, total_spent
const TOP_N = 20;
const d = db.getSiblingDB((typeof process !== "undefined" && process.env.MONGO_DB) || "dbperf");

// Money arrives as a string from $toString; pad to exactly 2 decimals (same helper as seed/checks).
const money = (s) => {
  if (!s.includes(".")) return s + ".00";
  const frac = s.split(".")[1].length;
  return frac >= 2 ? s : s + "0".repeat(2 - frac);
};

const pipeline = [
  { $match: { status: "delivered" } },
  { $group: { _id: "$customer_id", order_count: { $sum: 1 }, spent: { $sum: "$total_amount" } } },
  { $lookup: { from: "customers", localField: "_id", foreignField: "_id", as: "customer" } },
  { $unwind: "$customer" },
  { $sort: { spent: -1, "customer.email": 1 } },
  { $limit: TOP_N },
  { $project: {
    _id: 0,
    email: "$customer.email",
    order_count: { $toString: "$order_count" },
    total_spent: { $toString: { $round: ["$spent", 2] } },
  } },
];

print(["email", "order_count", "total_spent"].join("\t"));
d.orders.aggregate(pipeline).forEach((r) => print([r.email, r.order_count, money(r.total_spent)].join("\t")));
