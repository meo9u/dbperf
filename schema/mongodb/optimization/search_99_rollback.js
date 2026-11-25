// Restores the baseline indexes (undoes search_01_indexes.js).
const d = db.getSiblingDB((typeof process !== "undefined" && process.env.MONGO_DB) || "dbperf");
for (const name of ["idx_products_category_status", "idx_products_search"]) {
  if (d.products.getIndexes().some((i) => i.name === name)) d.products.dropIndex(name);
}
print(`baseline indexes restored in database "${d.getName()}"`);
