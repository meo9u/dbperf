// Phase 5 step "idx": indexes for the class 1 queries. Undo with 99_rollback.js.
// Apply: python3 benchmark/optimization.py apply --db mongodb   (env MONGO_DB, default "dbperf")
// Note: `docker compose up -d` re-runs 01-collections.js, which resets the inventory validator and would
// reject writes to documents that carry quantity_available. Re-apply this file after any `up`.
const d = db.getSiblingDB((typeof process !== "undefined" && process.env.MONGO_DB) || "dbperf");

// q1 (revenue by month), q2 (range on created_at), covered: only status, created_at, total_amount are read.
d.orders.createIndex({ status: 1, created_at: 1, total_amount: 1 }, { name: "idx_orders_status_created_total" });
// q4 (top customers), covered.
d.orders.createIndex({ status: 1, customer_id: 1, total_amount: 1 }, { name: "idx_orders_status_customer_total" });

// q5: store quantity_available (schema change: writers must keep it in sync) and index it.
// The inventory validator has additionalProperties:false, so allow the new field first.
const validator = d.getCollectionInfos({ name: "inventory" })[0].options.validator;
validator.$and[0].$jsonSchema.properties.quantity_available = { bsonType: ["int", "long"], minimum: 0 };
d.runCommand({ collMod: "inventory", validator, validationLevel: "strict", validationAction: "error" });
d.inventory.updateMany({}, [{ $set: { quantity_available: { $subtract: ["$quantity_on_hand", "$quantity_reserved"] } } }]);
d.inventory.createIndex({ quantity_available: 1 }, { name: "idx_inventory_available" });
print(`optimization indexes ready in database "${d.getName()}"`);
