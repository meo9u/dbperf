// Indexes required by uniqueness constraints only (the MySQL UNIQUE KEYs).
// All other indexes are designed on paper (see mongodb-design-summary.md, step 4) and created in Phase 5.
// Usage: mongosh "<uri>" --file schema/mongodb/02-indexes.js   (env MONGO_DB, default "dbperf")

const dbName = (typeof process !== "undefined" && process.env.MONGO_DB) || "dbperf";
const d = db.getSiblingDB(dbName);

d.products.createIndex({ "skus.sku_id": 1 }, { name: "uq_products_sku_id", unique: true });
d.products.createIndex({ "skus.sku_code": 1 }, { name: "uq_products_sku_code", unique: true });
d.inventory.createIndex({ sku_id: 1, warehouse_id: 1 }, { name: "uq_inventory_sku_warehouse", unique: true });
d.customers.createIndex({ email: 1 }, { name: "uq_customers_email", unique: true });
print(`unique indexes ready in database "${dbName}"`);
