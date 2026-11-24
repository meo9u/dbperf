// MongoDB collections and $jsonSchema validators for the dbperf e-commerce domain.
// Target: mongo:8.0.32, single-node replica set rs0.
// Usage: mongosh "<uri>" --file schema/mongodb/01-collections.js
//        (database name from env MONGO_DB, default "dbperf")
// Design rationale and workload traceability: docs/schema/mongodb-design-summary.md.

const dbName = (typeof process !== "undefined" && process.env.MONGO_DB) || "dbperf";
const d = db.getSiblingDB(dbName);

const MONEY_MAX = NumberDecimal("9999999999.99"); // parity with MySQL DECIMAL(12,2)
const ZERO = NumberDecimal("0");

const money = { bsonType: "decimal", minimum: ZERO, maximum: MONEY_MAX };
const oid = { bsonType: "objectId" };
const str = (max) => ({ bsonType: "string", minLength: 1, maxLength: max });
const date = { bsonType: "date" };
const activeInactive = { enum: ["active", "inactive"] };
const orderStatus = { enum: ["pending", "shipped", "delivered", "cancelled", "returned"] };
const paymentMethod = { enum: ["credit_card", "bank_transfer", "cod", "e_wallet"] };
const paymentStatus = { enum: ["pending", "success", "failed", "refunded"] };
const schemaVersion = { bsonType: "int", minimum: 1 };
// Variant attributes: at most 8 keys, key = 1..30 chars of [a-z0-9_], string values up to 100 chars
// (bounds the document size; $jsonSchema has no propertyNames, so patternProperties is used).
const variantObject = {
  bsonType: "object",
  maxProperties: 8,
  patternProperties: { "^[a-z0-9_]{1,30}$": { bsonType: "string", maxLength: 100 } },
  additionalProperties: false,
};

// Optional fields are omitted, never null: no property accepts null.

const validators = {
  categories: {
    $jsonSchema: {
      bsonType: "object",
      required: ["_id", "schema_version", "name", "status", "created_at"],
      additionalProperties: false,
      properties: {
        _id: oid,
        schema_version: schemaVersion,
        name: str(150),
        status: activeInactive,
        created_at: date,
      },
    },
  },

  products: {
    $and: [
      {
        $jsonSchema: {
          bsonType: "object",
          required: [
            "_id", "schema_version", "category_id", "name", "status",
            "skus", "created_at", "updated_at",
          ],
          additionalProperties: false,
          properties: {
            _id: oid,
            schema_version: schemaVersion,
            category_id: oid,
            name: str(200),
            description: { bsonType: "string", maxLength: 4000 },
            status: activeInactive,
            skus: {
              bsonType: "array",
              maxItems: 50,
              items: {
                bsonType: "object",
                required: ["sku_id", "sku_code", "variant_attributes", "current_price", "status", "updated_at"],
                additionalProperties: false,
                properties: {
                  sku_id: oid,
                  // Stored uppercase (case-insensitive uniqueness parity with MySQL).
                  sku_code: { bsonType: "string", minLength: 1, maxLength: 64, pattern: "^[A-Z0-9._-]+$" },
                  variant_attributes: variantObject,
                  current_price: money,
                  status: activeInactive,
                  updated_at: date,
                },
              },
            },
            created_at: date,
            updated_at: date,
          },
        },
      },
      {
        $expr: {
          $and: [
            // Unique indexes only compare across documents: no duplicate SKU inside one product.
            { $eq: [{ $size: { $setUnion: ["$skus.sku_id", []] } }, { $size: "$skus.sku_id" }] },
            { $eq: [{ $size: { $setUnion: ["$skus.sku_code", []] } }, { $size: "$skus.sku_code" }] },
          ],
        },
      },
    ],
  },

  warehouses: {
    $jsonSchema: {
      bsonType: "object",
      required: ["_id", "schema_version", "name", "address", "city", "status"],
      additionalProperties: false,
      properties: {
        _id: oid,
        schema_version: schemaVersion,
        name: str(150),
        address: str(255),
        city: str(100),
        status: activeInactive,
      },
    },
  },

  inventory: {
    $and: [
      {
        $jsonSchema: {
          bsonType: "object",
          required: ["_id", "schema_version", "sku_id", "warehouse_id", "quantity_on_hand", "quantity_reserved", "updated_at"],
          additionalProperties: false,
          properties: {
            _id: oid,
            schema_version: schemaVersion,
            sku_id: oid,
            warehouse_id: oid,
            quantity_on_hand: { bsonType: ["int", "long"], minimum: 0, maximum: 4294967295 }, // INT UNSIGNED
            quantity_reserved: { bsonType: ["int", "long"], minimum: 0, maximum: 4294967295 },
            // Id of the last stock receipt applied, so a retried receipt is not added twice.
            last_receipt_id: { bsonType: "string", minLength: 1, maxLength: 64 },
            updated_at: date,
          },
        },
      },
      { $expr: { $lte: ["$quantity_reserved", "$quantity_on_hand"] } },
    ],
  },

  customers: {
    $jsonSchema: {
      bsonType: "object",
      required: ["_id", "schema_version", "full_name", "address", "email", "created_at", "updated_at"],
      additionalProperties: false,
      properties: {
        _id: oid,
        schema_version: schemaVersion,
        full_name: str(150),
        address: str(255),
        // Stored lowercase (case-insensitive uniqueness parity with MySQL utf8mb4_unicode_ci).
        email: { bsonType: "string", maxLength: 255, pattern: "^[^\\sA-Z@]+@[^\\sA-Z@]+$" },
        phone: str(20),
        created_at: date,
        updated_at: date,
      },
    },
  },

  orders: {
    $and: [
      {
        $jsonSchema: {
          bsonType: "object",
          required: [
            "_id", "schema_version", "customer_id", "status", "shipping",
            "total_amount", "lines", "payments", "created_at",
          ],
          additionalProperties: false,
          properties: {
            _id: oid,
            schema_version: schemaVersion,
            customer_id: oid,
            status: orderStatus,
            // Set at checkout for non-COD orders, removed when a payment succeeds or the order is cancelled.
            payment_due_at: date,
            shipping: {
              bsonType: "object",
              required: ["recipient_name", "phone", "address"],
              additionalProperties: false,
              properties: {
                recipient_name: str(150),
                phone: str(20),
                address: str(255),
              },
            },
            total_amount: money,
            lines: {
              bsonType: "array",
              minItems: 1,
              maxItems: 50,
              items: {
                bsonType: "object",
                required: ["sku_id", "unit_price_snapshot", "quantity", "line_total"],
                additionalProperties: false,
                properties: {
                  sku_id: oid,
                  unit_price_snapshot: money,
                  quantity: { bsonType: ["int", "long"], minimum: 1, maximum: 65535 },
                  line_total: money,
                  warehouse_id: oid,
                },
              },
            },
            payments: {
              bsonType: "array",
              maxItems: 5,
              items: {
                bsonType: "object",
                required: ["payment_id", "payment_method", "amount", "status", "created_at"],
                additionalProperties: false,
                properties: {
                  payment_id: oid,
                  payment_method: paymentMethod,
                  amount: money,
                  status: paymentStatus,
                  created_at: date,
                },
              },
            },
            created_at: date,
          },
        },
      },
      {
        $expr: {
          $and: [
            // line_total = quantity * unit_price_snapshot (MySQL generated column).
            {
              $allElementsTrue: [
                {
                  $map: {
                    input: "$lines",
                    as: "l",
                    in: { $eq: ["$$l.line_total", { $multiply: ["$$l.quantity", "$$l.unit_price_snapshot"] }] },
                  },
                },
              ],
            },
            // total_amount = sum(lines.line_total): the ERD has no subtotal/shipping_fee/discount columns.
            { $eq: ["$total_amount", { $sum: "$lines.line_total" }] },
            // Unique indexes only compare across documents: no duplicate payment inside one order.
            { $eq: [{ $size: { $setUnion: ["$payments.payment_id", []] } }, { $size: "$payments.payment_id" }] },
            // payment_due_at only exists while the order awaits payment.
            { $or: [{ $eq: [{ $type: "$payment_due_at" }, "missing"] }, { $eq: ["$status", "pending"] }] },
          ],
        },
      },
    ],
  },
};

for (const [name, validator] of Object.entries(validators)) {
  if (d.getCollectionNames().includes(name)) {
    d.runCommand({ collMod: name, validator, validationLevel: "strict", validationAction: "error" });
  } else {
    d.createCollection(name, { validator, validationLevel: "strict", validationAction: "error" });
  }
}
print(`collections ready in database "${dbName}": ${Object.keys(validators).join(", ")}`);
