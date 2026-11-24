// q5 | Low-stock report: (warehouse, SKU) rows whose available stock (on_hand - reserved) is below LOW_STOCK_THRESHOLD.
// Parameters: LOW_STOCK_THRESHOLD. Output columns: warehouse_name, sku_code, product_name, quantity_on_hand, quantity_reserved, quantity_available
const LOW_STOCK_THRESHOLD = 10;

const d = db.getSiblingDB((typeof process !== "undefined" && process.env.MONGO_DB) || "dbperf");

const pipeline = [
  { $match: { $expr: { $lt: [{ $subtract: ["$quantity_on_hand", "$quantity_reserved"] }, LOW_STOCK_THRESHOLD] } } },
  { $lookup: { from: "warehouses", localField: "warehouse_id", foreignField: "_id", as: "warehouse" } },
  { $unwind: "$warehouse" },
  { $lookup: { from: "products", localField: "sku_id", foreignField: "skus.sku_id", as: "product" } },
  { $unwind: "$product" },
  { $set: {
    sku: { $first: { $filter: { input: "$product.skus", cond: { $eq: ["$$this.sku_id", "$sku_id"] } } } },
    available: { $subtract: ["$quantity_on_hand", "$quantity_reserved"] },
  } },
  { $sort: { "warehouse.name": 1, available: 1, "sku.sku_code": 1 } },
  { $project: {
    _id: 0,
    warehouse_name: "$warehouse.name",
    sku_code: "$sku.sku_code",
    product_name: "$product.name",
    quantity_on_hand: { $toString: "$quantity_on_hand" },
    quantity_reserved: { $toString: "$quantity_reserved" },
    quantity_available: { $toString: "$available" },
  } },
];

print(["warehouse_name", "sku_code", "product_name", "quantity_on_hand", "quantity_reserved", "quantity_available"].join("\t"));
d.inventory.aggregate(pipeline).forEach((r) =>
  print([r.warehouse_name, r.sku_code, r.product_name, r.quantity_on_hand, r.quantity_reserved, r.quantity_available].join("\t")));
