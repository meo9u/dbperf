// Class 2 search_products, step "idx": indexes on products. Undo with search_99_rollback.js.
// Apply: python3 benchmark/optimization.py apply --set search --db mongodb   (env MONGO_DB, default "dbperf")
const d = db.getSiblingDB((typeof process !== "undefined" && process.env.MONGO_DB) || "dbperf");

// Replaces the COLLSCAN of all products for a category filter.
d.products.createIndex({ category_id: 1, status: 1 }, { name: "idx_products_category_status" });
// Multikey over the embedded skus: lets a pre-unwind $match on colour / price prune products (used by the optimized variant).
d.products.createIndex(
  { category_id: 1, status: 1, "skus.variant_attributes.color": 1, "skus.current_price": 1 },
  { name: "idx_products_search" });
print(`search indexes ready in database "${d.getName()}"`);
