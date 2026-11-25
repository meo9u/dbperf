// Restores the baseline schema (undoes 01_indexes.js).
const d = db.getSiblingDB((typeof process !== "undefined" && process.env.MONGO_DB) || "dbperf");
for (const [coll, name] of [["orders", "idx_orders_status_created_total"], ["orders", "idx_orders_status_customer_total"],
                            ["inventory", "idx_inventory_available"]]) {
  if (d.getCollection(coll).getIndexes().some((i) => i.name === name)) d.getCollection(coll).dropIndex(name);
}
d.inventory.updateMany({}, { $unset: { quantity_available: "" } });
const validator = d.getCollectionInfos({ name: "inventory" })[0].options.validator;
delete validator.$and[0].$jsonSchema.properties.quantity_available;
d.runCommand({ collMod: "inventory", validator, validationLevel: "strict", validationAction: "error" });
print(`baseline indexes restored in database "${d.getName()}"`);
