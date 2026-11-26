<!-- Phụ lục tách khỏi báo cáo chính (bao-cao-bai-tap-lon.md); giữ lại làm nguồn tham khảo, không nằm trong báo cáo nộp. -->

# PHỤ LỤC

## Phụ lục A. Lược đồ MySQL

### A.1 Lệnh tạo bảng (`schema/mysql/schema.sql`)

```sql
-- MySQL DDL for the dbperf e-commerce domain.
-- Generated from docs/schema/erd.dbml (database-agnostic conceptual model).
-- See docs/schema/erd.md section 3 for the full design review; references
-- below (e.g. "erd.md 3.3.2") point at open items still tracked there.

CREATE DATABASE IF NOT EXISTS dbperf
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE dbperf;

-- --------------------------------------------------------------------------
-- category
-- --------------------------------------------------------------------------
CREATE TABLE category (
  category_id  INT UNSIGNED NOT NULL AUTO_INCREMENT,
  name         VARCHAR(150) NOT NULL,
  status       ENUM('active', 'inactive') NOT NULL,
  created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (category_id)
) ENGINE=InnoDB;

-- --------------------------------------------------------------------------
-- product
-- --------------------------------------------------------------------------
CREATE TABLE product (
  product_id   INT UNSIGNED NOT NULL AUTO_INCREMENT,
  category_id  INT UNSIGNED NOT NULL,
  name         VARCHAR(200) NOT NULL,
  description  TEXT NULL,
  status       ENUM('active', 'inactive') NOT NULL,
  created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (product_id),
  CONSTRAINT fk_product_category
    FOREIGN KEY (category_id) REFERENCES category (category_id)
    ON DELETE RESTRICT
) ENGINE=InnoDB;

-- --------------------------------------------------------------------------
-- sku (product variant)
-- --------------------------------------------------------------------------
CREATE TABLE sku (
  sku_id              INT UNSIGNED NOT NULL AUTO_INCREMENT,
  product_id          INT UNSIGNED NOT NULL,
  sku_code            VARCHAR(64) NOT NULL,
  -- JSON object, e.g. {"color": "red", "size": "M"} — see erd.md 3.4.11.
  -- Not strict 1NF, but queryable via JSON_EXTRACT / generated+indexed
  -- columns if needed later, and mirrors how the MongoDB side embeds
  -- variant attributes directly in the document.
  variant_attributes  JSON NOT NULL,
  current_price       DECIMAL(12,2) NOT NULL,
  status              ENUM('active', 'inactive') NOT NULL,
  updated_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (sku_id),
  UNIQUE KEY uq_sku_code (sku_code),
  CONSTRAINT fk_sku_product
    FOREIGN KEY (product_id) REFERENCES product (product_id)
    ON DELETE RESTRICT,
  CONSTRAINT chk_sku_current_price CHECK (current_price >= 0)
) ENGINE=InnoDB;

-- --------------------------------------------------------------------------
-- warehouse
-- --------------------------------------------------------------------------
CREATE TABLE warehouse (
  warehouse_id  INT UNSIGNED NOT NULL AUTO_INCREMENT,
  name          VARCHAR(150) NOT NULL,
  address       VARCHAR(255) NOT NULL,
  city          VARCHAR(100) NOT NULL,
  status        ENUM('active', 'inactive') NOT NULL,
  PRIMARY KEY (warehouse_id)
) ENGINE=InnoDB;

-- --------------------------------------------------------------------------
-- inventory (stock of 1 sku at 1 warehouse)
-- --------------------------------------------------------------------------
CREATE TABLE inventory (
  inventory_id       INT UNSIGNED NOT NULL AUTO_INCREMENT,
  sku_id             INT UNSIGNED NOT NULL,
  warehouse_id       INT UNSIGNED NOT NULL,
  quantity_on_hand   INT UNSIGNED NOT NULL,
  quantity_reserved  INT UNSIGNED NOT NULL,
  updated_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                       ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (inventory_id),
  UNIQUE KEY uq_inventory_sku_warehouse (sku_id, warehouse_id),
  CONSTRAINT fk_inventory_sku
    FOREIGN KEY (sku_id) REFERENCES sku (sku_id)
    ON DELETE RESTRICT,
  CONSTRAINT fk_inventory_warehouse
    FOREIGN KEY (warehouse_id) REFERENCES warehouse (warehouse_id)
    ON DELETE RESTRICT,
  CONSTRAINT chk_inventory_quantity_on_hand CHECK (quantity_on_hand >= 0),
  CONSTRAINT chk_inventory_quantity_reserved
    CHECK (quantity_reserved >= 0 AND quantity_reserved <= quantity_on_hand)
) ENGINE=InnoDB;

-- --------------------------------------------------------------------------
-- customer
-- --------------------------------------------------------------------------
CREATE TABLE customer (
  customer_id  INT UNSIGNED NOT NULL AUTO_INCREMENT,
  full_name    VARCHAR(150) NOT NULL,
  address      VARCHAR(255) NOT NULL,
  email        VARCHAR(255) NOT NULL,
  phone        VARCHAR(20) NULL,
  created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (customer_id),
  UNIQUE KEY uq_customer_email (email)
) ENGINE=InnoDB;

-- --------------------------------------------------------------------------
-- orders (created_at is the time the order was placed)
-- --------------------------------------------------------------------------
CREATE TABLE orders (
  order_id                 INT UNSIGNED NOT NULL AUTO_INCREMENT,
  customer_id              INT UNSIGNED NOT NULL,
  status                   ENUM('pending', 'shipped', 'delivered', 'cancelled', 'returned') NOT NULL,
  shipping_recipient_name  VARCHAR(150) NOT NULL,
  shipping_phone           VARCHAR(20) NOT NULL,
  shipping_address         VARCHAR(255) NOT NULL,
  -- total_amount is a cross-row aggregate (SUM of order_detail.line_total for
  -- this order_id) — neither CHECK nor GENERATED can express it (both are
  -- single-row only). subtotal_amount / shipping_fee / discount_amount no
  -- longer exist, so the former GENERATED formula is gone (erd.md 3.4.22).
  -- Decision: application-level convention, not a trigger. The app MUST
  -- recompute and write total_amount in the same transaction as any
  -- INSERT/UPDATE/DELETE on order_detail rows for this order_id. No DB-level
  -- enforcement exists here; the MongoDB validator does enforce the equality.
  total_amount             DECIMAL(12,2) NOT NULL,
  created_at               TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (order_id),
  CONSTRAINT fk_orders_customer
    FOREIGN KEY (customer_id) REFERENCES customer (customer_id)
    ON DELETE RESTRICT,
  CONSTRAINT chk_orders_total_amount CHECK (total_amount >= 0)
) ENGINE=InnoDB;

-- --------------------------------------------------------------------------
-- order_detail (order line item)
-- --------------------------------------------------------------------------
CREATE TABLE order_detail (
  order_detail_id        INT UNSIGNED NOT NULL AUTO_INCREMENT,
  order_id               INT UNSIGNED NOT NULL,
  sku_id                 INT UNSIGNED NOT NULL,
  unit_price_snapshot    DECIMAL(12,2) NOT NULL COMMENT 'price locked at purchase time, independent of sku.current_price',
  quantity               SMALLINT UNSIGNED NOT NULL,
  -- Computed column: DB guarantees line_total always equals quantity *
  -- unit_price_snapshot, no app code or CHECK needed. STORED (not VIRTUAL)
  -- since this is read often (order history, revenue reports).
  line_total             DECIMAL(12,2)
                           GENERATED ALWAYS AS (quantity * unit_price_snapshot) STORED
                           NOT NULL COMMENT 'quantity * unit_price_snapshot',
  warehouse_id           INT UNSIGNED NULL COMMENT 'nullable, fulfillment warehouse',
  PRIMARY KEY (order_detail_id),
  CONSTRAINT fk_order_detail_order
    FOREIGN KEY (order_id) REFERENCES orders (order_id)
    ON DELETE RESTRICT,
  CONSTRAINT fk_order_detail_sku
    FOREIGN KEY (sku_id) REFERENCES sku (sku_id)
    ON DELETE RESTRICT,
  CONSTRAINT fk_order_detail_warehouse
    FOREIGN KEY (warehouse_id) REFERENCES warehouse (warehouse_id)
    ON DELETE RESTRICT,
  CONSTRAINT chk_order_detail_quantity CHECK (quantity > 0),
  CONSTRAINT chk_order_detail_unit_price_snapshot CHECK (unit_price_snapshot >= 0)
) ENGINE=InnoDB;

-- --------------------------------------------------------------------------
-- payment
-- --------------------------------------------------------------------------
CREATE TABLE payment (
  payment_id       INT UNSIGNED NOT NULL AUTO_INCREMENT,
  order_id         INT UNSIGNED NOT NULL,
  payment_method   ENUM('credit_card', 'bank_transfer', 'cod', 'e_wallet') NOT NULL,
  amount           DECIMAL(12,2) NOT NULL,
  status           ENUM('pending', 'success', 'failed', 'refunded') NOT NULL,
  created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (payment_id),
  CONSTRAINT fk_payment_order
    FOREIGN KEY (order_id) REFERENCES orders (order_id)
    ON DELETE RESTRICT,
  CONSTRAINT chk_payment_amount CHECK (amount >= 0)
) ENGINE=InnoDB;
```

### A.2 Chỉ mục và cột sinh của bước tối ưu nhóm 1 (`schema/mysql/optimization/01_indexes.sql`)

```sql
-- Phase 5 step "idx": indexes and one generated column for the class 1 queries. Undo with 99_rollback.sql.
-- Apply: python3 benchmark/optimization.py apply --db mysql
USE dbperf;

-- q1 (revenue by month), q2 (range on created_at): covering, ordered by status then time.
-- q4 (top customers): covering, ordered by customer inside status.
ALTER TABLE orders
  ADD INDEX idx_orders_status_created_total (status, created_at, total_amount),
  ADD INDEX idx_orders_status_customer_total (status, customer_id, total_amount);

-- q2/q3: read quantity, line_total and sku_id per order without touching the clustered row.
-- Note: because this index starts with order_id, MySQL silently drops the FK helper index fk_order_detail_order;
-- 99_rollback.sql recreates it.
ALTER TABLE order_detail
  ADD INDEX idx_order_detail_cover (order_id, sku_id, quantity, line_total);

-- q5: the filter on (on_hand - reserved) becomes a plain range scan on an indexed stored column.
ALTER TABLE inventory
  ADD COLUMN quantity_available INT UNSIGNED
    GENERATED ALWAYS AS (quantity_on_hand - quantity_reserved) STORED NOT NULL,
  ADD INDEX idx_inventory_available (quantity_available);

ANALYZE TABLE orders, order_detail, inventory;
```

### A.3 Chỉ mục và cột sinh của bước tối ưu tìm kiếm (`schema/mysql/optimization/search_01_indexes.sql`)

```sql
-- Class 2 search_products, step "idx": indexes and one generated column. Undo with search_99_rollback.sql.
-- Apply: python3 benchmark/optimization.py apply --set search --db mysql
USE dbperf;

-- Colour as a stored generated column: the existing query's JSON_UNQUOTE(JSON_EXTRACT(variant_attributes,'$.color'))
-- is the same expression, so MySQL substitutes the column and stops parsing JSON for every SKU row.
ALTER TABLE sku
  ADD COLUMN color VARCHAR(64)
    GENERATED ALWAYS AS (JSON_UNQUOTE(JSON_EXTRACT(variant_attributes, '$.color'))) STORED,
  -- covering index for the product -> sku probe: filters and the sort key are all in the index
  ADD INDEX idx_sku_search (product_id, status, color, current_price, sku_code);

ALTER TABLE product ADD INDEX idx_product_category_status (category_id, status);

ANALYZE TABLE sku, product;
```

## Phụ lục B. Lược đồ MongoDB

### B.1 Collection và validator (`schema/mongodb/01-collections.js`)

```javascript
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
```

### B.2 Chỉ mục bắt buộc (`schema/mongodb/02-indexes.js`)

```javascript
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
```

### B.3 Chỉ mục và trường lưu sẵn của bước tối ưu nhóm 1 (`schema/mongodb/optimization/01_indexes.js`)

```javascript
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
```

### B.4 Chỉ mục của bước tối ưu tìm kiếm (`schema/mongodb/optimization/search_01_indexes.js`)

```javascript
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
```

## Phụ lục C. Mô hình thực thể–quan hệ dạng DBML (`docs/schema/erd.dbml`)

Nguồn của Hình 3.1; mô hình độc lập với hệ quản trị, dùng chung trước khi tách thành lược đồ MySQL và MongoDB.

```text


Enum active_inactive_status {
  active
  inactive
}

Enum order_status_enum {
  pending
  shipped
  delivered
  cancelled
  returned
}

Enum payment_status_enum {
  pending
  success
  failed
  refunded
}

Enum payment_method_enum {
  credit_card
  bank_transfer
  cod
  e_wallet
}

Table category {
  category_id int [pk, increment]
  name varchar(150) [not null]
  status active_inactive_status [not null]
  created_at timestamp [not null]
}

Table product {
  product_id int [pk, increment]
  category_id int [not null]
  name varchar(200) [not null]
  description text [null]
  status active_inactive_status [not null]
  created_at timestamp [not null]
  updated_at timestamp [not null]
}

Table sku {
  sku_id int [pk, increment]
  product_id int [not null]
  sku_code varchar(64) [not null, unique]
  variant_attributes json [not null]
  current_price decimal(12,2) [not null]
  status active_inactive_status [not null]
  updated_at timestamp [not null]
}

Table warehouse {
  warehouse_id int [pk, increment]
  name varchar(150) [not null]
  address varchar(255) [not null]
  city varchar(100) [not null]
  status active_inactive_status [not null]
}

Table inventory {
  inventory_id int [pk, increment]
  sku_id int [not null]
  warehouse_id int [not null]
  quantity_on_hand int [not null, note: 'CHECK (quantity_on_hand >= 0) — document only, enforce in schema/mysql DDL']
  quantity_reserved int [not null, note: 'CHECK (quantity_reserved >= 0 AND quantity_reserved <= quantity_on_hand) — document only, enforce in schema/mysql DDL']
  updated_at timestamp [not null]

  indexes {
    (sku_id, warehouse_id) [unique]
  }
}

Table customer {
  customer_id int [pk, increment]
  full_name varchar(150) [not null]
  address varchar(255) [not null]
  email varchar(255) [not null, unique]
  phone varchar(20) [null]
  created_at timestamp [not null]
  updated_at timestamp [not null]
}

Table orders {
  order_id int [pk, increment]
  customer_id int [not null]
  status order_status_enum [not null]
  shipping_recipient_name varchar(150) [not null]
  shipping_phone varchar(20) [not null]
  shipping_address varchar(255) [not null]
  total_amount decimal(12,2) [not null]
  created_at timestamp [not null]
}

Table order_detail {
  order_detail_id int [pk, increment]
  order_id int [not null]
  sku_id int [not null]
  unit_price_snapshot decimal(12,2) [not null, note: 'price locked at purchase time, independent of sku.current_price']
  quantity smallint [not null, note: 'CHECK (quantity > 0) — document only, enforce in schema/mysql DDL']
  line_total decimal(12,2) [not null, note: 'GENERATED ALWAYS AS (quantity * unit_price_snapshot) STORED in schema/mysql — see erd.md 3.4.15']
  warehouse_id int [null, note: 'nullable, fulfillment warehouse']
}


Table payment {
  payment_id int [pk, increment]
  order_id int [not null]
  payment_method payment_method_enum [not null]
  amount decimal(12,2) [not null]
  status payment_status_enum [not null]
  created_at timestamp [not null]
}

// --------------------------------------------------------------------------
// Relationships — delete: restrict everywhere, see erd.md 3.4.1
// --------------------------------------------------------------------------
Ref: product.category_id > category.category_id [delete: restrict]
Ref: sku.product_id > product.product_id [delete: restrict]
Ref: inventory.sku_id > sku.sku_id [delete: restrict]
Ref: inventory.warehouse_id > warehouse.warehouse_id [delete: restrict]
Ref: orders.customer_id > customer.customer_id [delete: restrict]
Ref: order_detail.order_id > orders.order_id [delete: restrict]
Ref: order_detail.sku_id > sku.sku_id [delete: restrict]
Ref: order_detail.warehouse_id > warehouse.warehouse_id [delete: restrict]
Ref: payment.order_id > orders.order_id [delete: restrict]
```

## Phụ lục D. Năm truy vấn nhóm 1

Mỗi truy vấn có phiên bản baseline và phiên bản tối ưu cho hai CSDL; tệp nguồn nằm ở `queries/{mysql,mongodb}/{baseline,optimized}/`. Dòng đầu mỗi tệp ghi câu hỏi nghiệp vụ và tham số.

### q1. Doanh thu theo tháng

**MySQL, baseline** (`queries/mysql/baseline/q1_revenue_by_month.sql`)

```sql
-- q1: Revenue by month. Delivered orders only, grouped by the month the order was placed (UTC), whole table.
-- Parameters: none (full scan of orders by design).
-- Output columns, in order: order_month (YYYY-MM), order_count, revenue (2 decimals)
SET time_zone = '+00:00';

SELECT
  DATE_FORMAT(created_at, '%Y-%m') AS order_month,
  COUNT(*) AS order_count,
  ROUND(SUM(total_amount), 2) AS revenue
FROM orders
WHERE status = 'delivered'
GROUP BY order_month
ORDER BY order_month;
```

**MySQL, tối ưu** (`queries/mysql/optimized/q1_revenue_by_month.sql`)

```sql
-- Phase 5: unchanged query; served by covering index idx_orders_status_created_total.
-- q1: Revenue by month. Delivered orders only, grouped by the month the order was placed (UTC), whole table.
-- Parameters: none (full scan of orders by design).
-- Output columns, in order: order_month (YYYY-MM), order_count, revenue (2 decimals)
SET time_zone = '+00:00';

SELECT
  DATE_FORMAT(created_at, '%Y-%m') AS order_month,
  COUNT(*) AS order_count,
  ROUND(SUM(total_amount), 2) AS revenue
FROM orders
WHERE status = 'delivered'
GROUP BY order_month
ORDER BY order_month;
```

**MongoDB, baseline** (`queries/mongodb/baseline/q1_revenue_by_month.js`)

```javascript
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
```

**MongoDB, tối ưu** (`queries/mongodb/optimized/q1_revenue_by_month.js`)

```javascript
// q1 | Revenue by month: number of delivered orders and total revenue per calendar month (UTC).
// Parameters: none (all delivered orders). Output columns: order_month, order_count, revenue
const d = db.getSiblingDB((typeof process !== "undefined" && process.env.MONGO_DB) || "dbperf");

// Money arrives as a string from $toString; pad to exactly 2 decimals (same helper as seed/checks).
const money = (s) => {
  if (!s.includes(".")) return s + ".00";
  const frac = s.split(".")[1].length;
  return frac >= 2 ? s : s + "0".repeat(2 - frac);
};

// Phase 5: status matches 96% of orders, so the status-leading indexes made the planner choose a slower index scan + FETCH; force the collection scan.
const OPTS = { hint: { $natural: 1 } };

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
d.orders.aggregate(pipeline, OPTS).forEach((r) => print([r.order_month, r.order_count, money(r.revenue)].join("\t")));
```

### q2. Top 20 SKU bán chạy năm 2019

**MySQL, baseline** (`queries/mysql/baseline/q2_top_skus.sql`)

```sql
-- q2: Top 20 best-selling SKUs in a period. Delivered orders only, ranked by units sold.
-- Parameters: @from_date (inclusive), @to_date (exclusive), UTC. Top N = 20 is the literal in LIMIT,
--   because MySQL does not accept a user variable in LIMIT.
-- Output columns, in order: sku_code, units_sold, revenue (2 decimals)
SET time_zone = '+00:00';
SET @from_date = '2019-01-01 00:00:00';
SET @to_date = '2020-01-01 00:00:00';

SELECT
  s.sku_code,
  CAST(SUM(d.quantity) AS UNSIGNED) AS units_sold,
  ROUND(SUM(d.line_total), 2) AS revenue
FROM orders o
JOIN order_detail d ON d.order_id = o.order_id
JOIN sku s ON s.sku_id = d.sku_id
WHERE o.status = 'delivered'
  AND o.created_at >= @from_date
  AND o.created_at < @to_date
GROUP BY s.sku_id, s.sku_code
ORDER BY units_sold DESC, s.sku_code ASC
LIMIT 20;
```

**MySQL, tối ưu** (`queries/mysql/optimized/q2_top_skus.sql`)

```sql
-- q2 (optimized): Top 20 best-selling SKUs in a period. Delivered orders only, ranked by units sold.
-- Phase 5: aggregate order_detail by sku_id first, join sku only for the ~19K groups; force the range scan on
--   idx_orders_status_created_total (the optimizer otherwise picks idx_orders_status_customer_total and reads 960K rows).
-- Parameters: @from_date (inclusive), @to_date (exclusive), UTC. Top N = 20 is the literal in LIMIT.
-- Output columns, in order: sku_code, units_sold, revenue (2 decimals)
SET time_zone = '+00:00';
SET @from_date = '2019-01-01 00:00:00';
SET @to_date = '2020-01-01 00:00:00';

SELECT
  s.sku_code,
  t.units_sold,
  ROUND(t.revenue, 2) AS revenue
FROM (
  SELECT /*+ JOIN_ORDER(o, d) */
    d.sku_id,
    CAST(SUM(d.quantity) AS UNSIGNED) AS units_sold,
    SUM(d.line_total) AS revenue
  FROM orders o USE INDEX (idx_orders_status_created_total)
  JOIN order_detail d ON d.order_id = o.order_id
  WHERE o.status = 'delivered'
    AND o.created_at >= @from_date
    AND o.created_at < @to_date
  GROUP BY d.sku_id
) t
JOIN sku s ON s.sku_id = t.sku_id
ORDER BY t.units_sold DESC, s.sku_code ASC
LIMIT 20;
```

**MongoDB, baseline** (`queries/mongodb/baseline/q2_top_skus.js`)

```javascript
// q2 | Top SKUs by units sold in delivered orders created in [FROM_DATE, TO_DATE) (UTC), top TOP_N.
// Parameters: FROM_DATE, TO_DATE, TOP_N. Output columns: sku_code, units_sold, revenue
const FROM_DATE = new Date("2019-01-01T00:00:00Z"); // inclusive
const TO_DATE = new Date("2020-01-01T00:00:00Z"); // exclusive
const TOP_N = 20;
const d = db.getSiblingDB((typeof process !== "undefined" && process.env.MONGO_DB) || "dbperf");

// Money arrives as a string from $toString; pad to exactly 2 decimals (same helper as seed/checks).
const money = (s) => {
  if (!s.includes(".")) return s + ".00";
  const frac = s.split(".")[1].length;
  return frac >= 2 ? s : s + "0".repeat(2 - frac);
};

const pipeline = [
  { $match: { status: "delivered", created_at: { $gte: FROM_DATE, $lt: TO_DATE } } },
  { $unwind: "$lines" },
  { $group: { _id: "$lines.sku_id", units: { $sum: "$lines.quantity" }, revenue: { $sum: "$lines.line_total" } } },
  { $lookup: { from: "products", localField: "_id", foreignField: "skus.sku_id", as: "product" } },
  { $unwind: "$product" },
  { $set: { sku: { $first: { $filter: { input: "$product.skus", cond: { $eq: ["$$this.sku_id", "$_id"] } } } } } },
  { $sort: { units: -1, "sku.sku_code": 1 } },
  { $limit: TOP_N },
  { $project: {
    _id: 0,
    sku_code: "$sku.sku_code",
    units_sold: { $toString: "$units" },
    revenue: { $toString: { $round: ["$revenue", 2] } },
  } },
];

print(["sku_code", "units_sold", "revenue"].join("\t"));
d.orders.aggregate(pipeline).forEach((r) => print([r.sku_code, r.units_sold, money(r.revenue)].join("\t")));
```

**MongoDB, tối ưu** (`queries/mongodb/optimized/q2_top_skus.js`)

```javascript
// q2 | Top SKUs by units sold in delivered orders created in [FROM_DATE, TO_DATE) (UTC), top TOP_N.
// Parameters: FROM_DATE, TO_DATE, TOP_N. Output columns: sku_code, units_sold, revenue
const FROM_DATE = new Date("2019-01-01T00:00:00Z"); // inclusive
const TO_DATE = new Date("2020-01-01T00:00:00Z"); // exclusive
const TOP_N = 20;
const d = db.getSiblingDB((typeof process !== "undefined" && process.env.MONGO_DB) || "dbperf");

// Money arrives as a string from $toString; pad to exactly 2 decimals (same helper as seed/checks).
const money = (s) => {
  if (!s.includes(".")) return s + ".00";
  const frac = s.split(".")[1].length;
  return frac >= 2 ? s : s + "0".repeat(2 - frac);
};

// Phase 5: status matches 96% of orders, so the status-leading indexes made the planner choose a slower index scan + FETCH; force the collection scan.
const OPTS = { hint: { $natural: 1 } };

const pipeline = [
  { $match: { status: "delivered", created_at: { $gte: FROM_DATE, $lt: TO_DATE } } },
  { $unwind: "$lines" },
  { $group: { _id: "$lines.sku_id", units: { $sum: "$lines.quantity" }, revenue: { $sum: "$lines.line_total" } } },
  { $lookup: { from: "products", localField: "_id", foreignField: "skus.sku_id", as: "product" } },
  { $unwind: "$product" },
  { $set: { sku: { $first: { $filter: { input: "$product.skus", cond: { $eq: ["$$this.sku_id", "$_id"] } } } } } },
  { $sort: { units: -1, "sku.sku_code": 1 } },
  { $limit: TOP_N },
  { $project: {
    _id: 0,
    sku_code: "$sku.sku_code",
    units_sold: { $toString: "$units" },
    revenue: { $toString: { $round: ["$revenue", 2] } },
  } },
];

print(["sku_code", "units_sold", "revenue"].join("\t"));
d.orders.aggregate(pipeline, OPTS).forEach((r) => print([r.sku_code, r.units_sold, money(r.revenue)].join("\t")));
```

### q3. Doanh thu theo danh mục

**MySQL, baseline** (`queries/mysql/baseline/q3_revenue_by_category.sql`)

```sql
-- q3: Revenue by product category, all time. Delivered orders only; categories with no sales are omitted.
-- Parameters: none (full scan of delivered orders by design).
-- Output columns, in order: category_name, units_sold, revenue (2 decimals)
SELECT
  c.name AS category_name,
  CAST(SUM(d.quantity) AS UNSIGNED) AS units_sold,
  ROUND(SUM(d.line_total), 2) AS revenue
FROM orders o
JOIN order_detail d ON d.order_id = o.order_id
JOIN sku s ON s.sku_id = d.sku_id
JOIN product p ON p.product_id = s.product_id
JOIN category c ON c.category_id = p.category_id
WHERE o.status = 'delivered'
GROUP BY c.category_id, c.name
ORDER BY revenue DESC, c.name ASC;
```

**MySQL, tối ưu** (`queries/mysql/optimized/q3_revenue_by_category.sql`)

```sql
-- q3 (optimized): Revenue by product category, all time. Delivered orders only; categories with no sales are omitted.
-- Phase 5: aggregate order_detail by sku_id first (~20K rows), then join sku / product / category on that small set
--   instead of 4 lookups per each of the 2.99M lines. JOIN_ORDER keeps the optimizer from starting at sku.
-- Parameters: none (full scan of delivered orders by design).
-- Output columns, in order: category_name, units_sold, revenue (2 decimals)
SELECT
  c.name AS category_name,
  CAST(SUM(t.units_total) AS UNSIGNED) AS units_sold,
  ROUND(SUM(t.revenue_total), 2) AS revenue
FROM (
  SELECT /*+ JOIN_ORDER(o, d) */
    d.sku_id,
    SUM(d.quantity) AS units_total,
    SUM(d.line_total) AS revenue_total
  FROM orders o
  JOIN order_detail d ON d.order_id = o.order_id
  WHERE o.status = 'delivered'
  GROUP BY d.sku_id
) t
JOIN sku s ON s.sku_id = t.sku_id
JOIN product p ON p.product_id = s.product_id
JOIN category c ON c.category_id = p.category_id
GROUP BY c.category_id, c.name
ORDER BY revenue DESC, c.name ASC;
```

**MongoDB, baseline** (`queries/mongodb/baseline/q3_revenue_by_category.js`)

```javascript
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
```

**MongoDB, tối ưu** (`queries/mongodb/optimized/q3_revenue_by_category.js`)

```javascript
// q3 | Revenue by product category: units sold and line revenue from delivered orders, per category.
// Parameters: none (all delivered orders). Output columns: category_name, units_sold, revenue
const d = db.getSiblingDB((typeof process !== "undefined" && process.env.MONGO_DB) || "dbperf");

// Money arrives as a string from $toString; pad to exactly 2 decimals (same helper as seed/checks).
const money = (s) => {
  if (!s.includes(".")) return s + ".00";
  const frac = s.split(".")[1].length;
  return frac >= 2 ? s : s + "0".repeat(2 - frac);
};

// Phase 5: status matches 96% of orders, so the status-leading indexes made the planner choose a slower index scan + FETCH; force the collection scan.
const OPTS = { hint: { $natural: 1 } };

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
d.orders.aggregate(pipeline, OPTS).forEach((r) => print([r.category_name, r.units_sold, money(r.revenue)].join("\t")));
```

### q4. Top 20 khách hàng

**MySQL, baseline** (`queries/mysql/baseline/q4_top_customers.sql`)

```sql
-- q4: Top 20 customers by total spend. Delivered orders only, all time. Top N = 20 is the literal in LIMIT,
--   because MySQL does not accept a user variable in LIMIT.
-- Parameters: none besides top N.
-- Output columns, in order: email, order_count, total_spent (2 decimals)

SELECT
  c.email,
  COUNT(*) AS order_count,
  ROUND(SUM(o.total_amount), 2) AS total_spent
FROM orders o
JOIN customer c ON c.customer_id = o.customer_id
WHERE o.status = 'delivered'
GROUP BY c.customer_id, c.email
ORDER BY total_spent DESC, c.email ASC
LIMIT 20;
```

**MySQL, tối ưu** (`queries/mysql/optimized/q4_top_customers.sql`)

```sql
-- q4 (optimized): Top 20 customers by total spend. Delivered orders only, all time. Top N = 20 is the literal in LIMIT.
-- Phase 5: aggregate orders by customer_id from the covering index idx_orders_status_customer_total, then join customer.
-- Parameters: none besides top N.
-- Output columns, in order: email, order_count, total_spent (2 decimals)
SELECT
  c.email,
  t.order_count,
  ROUND(t.spent, 2) AS total_spent
FROM (
  SELECT customer_id, COUNT(*) AS order_count, SUM(total_amount) AS spent
  FROM orders
  WHERE status = 'delivered'
  GROUP BY customer_id
) t
JOIN customer c ON c.customer_id = t.customer_id
ORDER BY total_spent DESC, c.email ASC
LIMIT 20;
```

**MongoDB, baseline** (`queries/mongodb/baseline/q4_top_customers.js`)

```javascript
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
```

**MongoDB, tối ưu** (`queries/mongodb/optimized/q4_top_customers.js`)

```javascript
// Phase 5: unchanged pipeline; served by covered index idx_orders_status_customer_total.
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
```

### q5. Tồn kho thấp theo kho

**MySQL, baseline** (`queries/mysql/baseline/q5_low_stock_by_warehouse.sql`)

```sql
-- q5: Low-stock report by warehouse. Inventory rows whose available stock (on hand minus reserved) is at or below a threshold.
-- Parameters: @low_stock_threshold (available units, inclusive).
-- Output columns, in order: warehouse_name, sku_code, product_name, quantity_on_hand, quantity_reserved, quantity_available
SET @low_stock_threshold = 25;

SELECT
  w.name AS warehouse_name,
  s.sku_code,
  p.name AS product_name,
  i.quantity_on_hand,
  i.quantity_reserved,
  i.quantity_on_hand - i.quantity_reserved AS quantity_available
FROM inventory i
JOIN sku s ON s.sku_id = i.sku_id
JOIN product p ON p.product_id = s.product_id
JOIN warehouse w ON w.warehouse_id = i.warehouse_id
WHERE i.quantity_on_hand - i.quantity_reserved <= @low_stock_threshold
ORDER BY w.name ASC, quantity_available ASC, s.sku_code ASC;
```

**MySQL, tối ưu** (`queries/mysql/optimized/q5_low_stock_by_warehouse.sql`)

```sql
-- q5 (optimized): Low-stock report by warehouse. Inventory rows whose available stock is at or below a threshold.
-- Phase 5: filter on the stored generated column inventory.quantity_available (indexed: idx_inventory_available).
-- Parameters: @low_stock_threshold (available units, inclusive).
-- Output columns, in order: warehouse_name, sku_code, product_name, quantity_on_hand, quantity_reserved, quantity_available
SET @low_stock_threshold = 25;

SELECT
  w.name AS warehouse_name,
  s.sku_code,
  p.name AS product_name,
  i.quantity_on_hand,
  i.quantity_reserved,
  i.quantity_available
FROM inventory i
JOIN sku s ON s.sku_id = i.sku_id
JOIN product p ON p.product_id = s.product_id
JOIN warehouse w ON w.warehouse_id = i.warehouse_id
WHERE i.quantity_available <= @low_stock_threshold
ORDER BY w.name ASC, i.quantity_available ASC, s.sku_code ASC;
```

**MongoDB, baseline** (`queries/mongodb/baseline/q5_low_stock_by_warehouse.js`)

```javascript
// q5 | Low-stock report: (warehouse, SKU) rows whose available stock (on_hand - reserved) is at or below LOW_STOCK_THRESHOLD.
// Parameters: LOW_STOCK_THRESHOLD. Output columns: warehouse_name, sku_code, product_name, quantity_on_hand, quantity_reserved, quantity_available
const LOW_STOCK_THRESHOLD = 25;

const d = db.getSiblingDB((typeof process !== "undefined" && process.env.MONGO_DB) || "dbperf");

const pipeline = [
  { $match: { $expr: { $lte: [{ $subtract: ["$quantity_on_hand", "$quantity_reserved"] }, LOW_STOCK_THRESHOLD] } } },
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
```

**MongoDB, tối ưu** (`queries/mongodb/optimized/q5_low_stock_by_warehouse.js`)

```javascript
// q5 | Low-stock report: (warehouse, SKU) rows whose available stock (on_hand - reserved) is at or below LOW_STOCK_THRESHOLD.
// Parameters: LOW_STOCK_THRESHOLD. Output columns: warehouse_name, sku_code, product_name, quantity_on_hand, quantity_reserved, quantity_available
const LOW_STOCK_THRESHOLD = 25;

const d = db.getSiblingDB((typeof process !== "undefined" && process.env.MONGO_DB) || "dbperf");

const pipeline = [
  // Phase 5: filter on the stored quantity_available field (indexed) instead of an expression.
  { $match: { quantity_available: { $lte: LOW_STOCK_THRESHOLD } } },
  { $lookup: { from: "warehouses", localField: "warehouse_id", foreignField: "_id", as: "warehouse" } },
  { $unwind: "$warehouse" },
  { $lookup: { from: "products", localField: "sku_id", foreignField: "skus.sku_id", as: "product" } },
  { $unwind: "$product" },
  { $set: {
    sku: { $first: { $filter: { input: "$product.skus", cond: { $eq: ["$$this.sku_id", "$sku_id"] } } } },
    available: "$quantity_available",
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
```

## Phụ lục E. Kịch bản k6 và tham số

| Kịch bản | Tệp | Tham số chính |
|---|---|---|
| Tìm kiếm sản phẩm | `benchmark/scenarios/search_products.{mysql,mongodb}.js`, tham số dùng chung `lib/search_params.js` | danh mục theo trọng số kích thước (9 danh mục lớn nhất); màu 50% (10 màu phổ biến nhất); khoảng giá 60% (0–10, 10–25, 25–50, 50–500); từ khóa tên 30% (`top`, `dress`, `shorts`, `skinny`, `jacket`, `tee`); trang 0–7 nghiêng về trang đầu; 20 kết quả mỗi trang; sắp xếp theo `sku_code` |
| Đặt hàng | `benchmark/scenarios/checkout.{mysql,mongodb}.js`, tham số dùng chung `lib/checkout_params.js`, danh sách đơn mẫu `lib/checkout_templates.json` | 500 đơn mẫu "nóng" (chứa một trong 200 SKU bán nhiều nhất) và 500 đơn "nguội" (đơn 100.001 trở đi, chỉ lấy đơn đã giao có tối đa 3 dòng hàng); 2.000 khách; 50% yêu cầu dùng đơn nóng; phương thức thanh toán theo phân phối của dữ liệu; tối đa 3 lượt thử |

Tải: k6 vòng kín, `constant-vus`, 45 giây mỗi mức, 20 giây khởi động (tìm kiếm); đặt hàng nạp lại dữ liệu trước mỗi mức và không khởi động riêng. Biến thể: `VARIANT=baseline` hoặc `optimized` (MySQL: một câu `INSERT` nhiều dòng cho các dòng hàng, khóa tồn kho theo thứ tự `(sku_id, warehouse_id)` và đặt cuối giao dịch; MongoDB: khóa tồn kho đặt cuối theo cùng thứ tự). Chế độ `VERIFY=1` chạy một dãy cố định để so sánh kết quả hai CSDL.

## Phụ lục F. Bảng số liệu đầy đủ

### F.1 Nhóm 1: độ trễ p50 (p95), ms

| Truy vấn | CSDL | Baseline gốc | Baseline sau ANALYZE | Chỉ thêm chỉ mục | Tối ưu | Baseline sau hoàn nguyên |
|---|---|---|---|---|---|---|
| q1 | MySQL | 430,7 (444,0) | 412,1 (425,7) | 337,3 (345,3) | 341,7 (349,9) | 428,7 (437,5) |
| q1 | MongoDB | 552,6 (595,1) | 538,7 (569,8) | 712,8 (739,0) | 559,5 (605,4) | 555,1 (587,6) |
| q2 | MySQL | 4.239,6 (4.341,7) | 4.193,9 (4.367,9) | 5.339,9 (5.374,8) | 1.608,4 (1.639,0) | 4.572,6 (5.085,6) |
| q2 | MongoDB | 1.497,8 (1.509,0) | 1.455,9 (1.514,2) | 2.158,3 (2.239,0) | 1.486,3 (1.518,3) | 1.515,1 (1.540,5) |
| q3 | MySQL | 9.038,8 (9.476,7) | 9.078,8 (9.284,1) | 11.431,9 (11.491,6) | 2.743,7 (2.792,1) | 9.666,3 (9.739,5) |
| q3 | MongoDB | 2.130,9 (2.237,0) | 2.201,0 (2.478,4) | 3.927,3 (3.960,2) | 2.149,7 (2.232,3) | 2.182,4 (2.382,2) |
| q4 | MySQL | 1.980,5 (2.014,2) | 1.833,2 (2.070,9) | 624,1 (637,4) | 197,0 (205,0) | 1.994,5 (2.118,8) |
| q4 | MongoDB | 1.191,1 (1.261,9) | 1.305,6 (1.409,4) | 1.101,8 (1.149,3) | 1.099,3 (1.171,7) | 1.246,5 (1.593,4) |
| q5 | MySQL | 474,8 (509,8) | 197,3 (220,3) | 20,6 (22,1) | 19,3 (20,6) | 222,8 (230,7) |
| q5 | MongoDB | 253,5 (275,0) | 271,6 (296,4) | 270,5 (289,0) | 173,2 (189,9) | 279,3 (354,9) |

Thí nghiệm histogram (`results/idx_histogram/`, MySQL, truy vấn baseline sau khi thêm chỉ mục và tạo histogram): q2 p50 6.907,4 ms, q3 p50 11.171,7 ms.

### F.2 Nhóm 2, tìm kiếm: thông lượng (yêu cầu mỗi giây) và độ trễ (ms)

**MySQL**

| Giai đoạn | VU | TPS | p50 | p95 | p99 |
|---|---|---|---|---|---|
| Baseline (lần đo đầu, thống kê cũ) | 4 | 398,7 | 3,4 | 58,8 | 63,9 |
| Baseline (lần đo đầu, thống kê cũ) | 8 | 305,9 | 5,4 | 91,3 | 94,8 |
| Baseline (lần đo đầu, thống kê cũ) | 16 | 188,6 | 91,5 | 206,4 | 296,3 |
| Baseline (lần đo đầu, thống kê cũ) | 32 | 180,7 | 104,0 | 497,8 | 635,6 |
| Baseline (lần đo đầu, thống kê cũ) | 64 | 177,3 | 207,3 | 1.088,6 | 1.401,5 |
| Baseline sau ANALYZE | 4 | 669,4 | 2,0 | 49,5 | 62,9 |
| Baseline sau ANALYZE | 8 | 484,5 | 2,8 | 85,2 | 102,4 |
| Baseline sau ANALYZE | 16 | 319,8 | 6,6 | 190,5 | 307,6 |
| Baseline sau ANALYZE | 32 | 312,4 | 95,6 | 300,0 | 505,1 |
| Baseline sau ANALYZE | 64 | 299,3 | 108,3 | 603,2 | 1.108,2 |
| Chỉ thêm chỉ mục | 4 | 1.275,3 | 1,3 | 6,1 | 50,1 |
| Chỉ thêm chỉ mục | 8 | 1.023,1 | 1,6 | 75,7 | 80,4 |
| Chỉ thêm chỉ mục | 16 | 710,7 | 3,2 | 92,4 | 97,9 |
| Chỉ thêm chỉ mục | 32 | 632,0 | 10,0 | 102,4 | 195,2 |
| Chỉ thêm chỉ mục | 64 | 660,8 | 97,5 | 203,5 | 302,6 |
| Tối ưu | 4 | 1.235,6 | 1,3 | 6,3 | 50,5 |
| Tối ưu | 8 | 970,1 | 1,7 | 76,1 | 80,7 |
| Tối ưu | 16 | 688,5 | 3,4 | 92,5 | 98,2 |
| Tối ưu | 32 | 652,3 | 9,5 | 101,9 | 193,5 |
| Tối ưu | 64 | 658,5 | 97,4 | 203,8 | 304,4 |
| Thí nghiệm gợi ý JOIN_ORDER (MySQL) / tối ưu lần 1 (MongoDB) | 4 | 913,3 | 1,5 | 9,2 | 54,2 |
| Thí nghiệm gợi ý JOIN_ORDER (MySQL) / tối ưu lần 1 (MongoDB) | 8 | 724,1 | 2,1 | 78,9 | 84,6 |
| Thí nghiệm gợi ý JOIN_ORDER (MySQL) / tối ưu lần 1 (MongoDB) | 16 | 536,2 | 4,4 | 96,7 | 102,3 |
| Thí nghiệm gợi ý JOIN_ORDER (MySQL) / tối ưu lần 1 (MongoDB) | 32 | 497,5 | 91,0 | 192,3 | 202,9 |
| Thí nghiệm gợi ý JOIN_ORDER (MySQL) / tối ưu lần 1 (MongoDB) | 64 | 500,9 | 100,2 | 303,4 | 496,7 |

**MongoDB**

| Giai đoạn | VU | TPS | p50 | p95 | p99 |
|---|---|---|---|---|---|
| Baseline (lần đo đầu, thống kê cũ) | 4 | 551,8 | 3,1 | 50,9 | 56,7 |
| Baseline (lần đo đầu, thống kê cũ) | 8 | 457,8 | 3,9 | 82,5 | 86,8 |
| Baseline (lần đo đầu, thống kê cũ) | 16 | 301,9 | 85,9 | 102,7 | 190,8 |
| Baseline (lần đo đầu, thống kê cũ) | 32 | 315,9 | 97,4 | 210,5 | 304,2 |
| Baseline (lần đo đầu, thống kê cũ) | 64 | 280,1 | 195,8 | 597,5 | 802,8 |
| Baseline sau ANALYZE | 4 | 553,0 | 3,1 | 51,0 | 57,1 |
| Baseline sau ANALYZE | 8 | 455,0 | 3,9 | 82,5 | 87,1 |
| Baseline sau ANALYZE | 16 | 325,3 | 11,4 | 101,3 | 189,4 |
| Baseline sau ANALYZE | 32 | 305,9 | 97,8 | 288,9 | 304,9 |
| Baseline sau ANALYZE | 64 | 286,3 | 195,1 | 595,5 | 797,1 |
| Chỉ thêm chỉ mục | 4 | 630,6 | 2,5 | 49,5 | 56,7 |
| Chỉ thêm chỉ mục | 8 | 515,7 | 3,2 | 82,2 | 86,1 |
| Chỉ thêm chỉ mục | 16 | 345,6 | 9,7 | 102,1 | 189,3 |
| Chỉ thêm chỉ mục | 32 | 321,8 | 96,5 | 291,2 | 390,2 |
| Chỉ thêm chỉ mục | 64 | 318,2 | 108,5 | 590,0 | 796,1 |
| Tối ưu | 4 | 849,6 | 1,5 | 11,5 | 55,4 |
| Tối ưu | 8 | 701,2 | 1,9 | 79,9 | 86,5 |
| Tối ưu | 16 | 505,3 | 4,0 | 99,3 | 183,8 |
| Tối ưu | 32 | 472,4 | 89,4 | 198,2 | 295,5 |
| Tối ưu | 64 | 479,1 | 98,9 | 400,2 | 598,4 |
| Thí nghiệm gợi ý JOIN_ORDER (MySQL) / tối ưu lần 1 (MongoDB) | 4 | 851,7 | 1,5 | 11,2 | 55,6 |
| Thí nghiệm gợi ý JOIN_ORDER (MySQL) / tối ưu lần 1 (MongoDB) | 8 | 697,5 | 1,9 | 79,9 | 86,8 |
| Thí nghiệm gợi ý JOIN_ORDER (MySQL) / tối ưu lần 1 (MongoDB) | 16 | 503,9 | 4,0 | 99,5 | 186,6 |
| Thí nghiệm gợi ý JOIN_ORDER (MySQL) / tối ưu lần 1 (MongoDB) | 32 | 468,7 | 89,3 | 199,4 | 296,8 |
| Thí nghiệm gợi ý JOIN_ORDER (MySQL) / tối ưu lần 1 (MongoDB) | 64 | 468,1 | 99,2 | 402,4 | 601,6 |

### F.3 Nhóm 2, đặt hàng: thông lượng (checkout thành công mỗi giây), độ trễ (ms) và thử lại

**MySQL**

| Giai đoạn | VU | Checkout thành công | TPS | p50 | p95 | p99 | Thử lại | Tỉ lệ thử lại (%) | Hết lượt thử |
|---|---|---|---|---|---|---|---|---|---|
| Baseline, lần 1 | 4 | 23.108 | 513,4 | 6,8 | 9,7 | 41,2 | 0 | 0,0 | 0 |
| Baseline, lần 1 | 8 | 25.911 | 575,7 | 11,3 | 18,0 | 73,7 | 0 | 0,0 | 0 |
| Baseline, lần 1 | 16 | 31.125 | 691,4 | 20,6 | 32,0 | 56,2 | 0 | 0,0 | 0 |
| Baseline, lần 1 | 32 | 35.588 | 790,4 | 38,2 | 58,8 | 78,7 | 0 | 0,0 | 0 |
| Baseline, lần 2 | 4 | 28.953 | 643,3 | 5,8 | 8,4 | 11,8 | 0 | 0,0 | 0 |
| Baseline, lần 2 | 8 | 34.100 | 757,7 | 10,0 | 12,6 | 26,2 | 0 | 0,0 | 0 |
| Baseline, lần 2 | 16 | 34.736 | 771,8 | 18,4 | 31,2 | 70,4 | 0 | 0,0 | 0 |
| Baseline, lần 2 | 32 | 36.008 | 799,7 | 34,8 | 69,6 | 85,3 | 0 | 0,0 | 0 |
| Tối ưu thứ tự khóa | 4 | 27.103 | 602,2 | 6,2 | 8,9 | 12,5 | 0 | 0,0 | 0 |
| Tối ưu thứ tự khóa | 8 | 30.935 | 687,3 | 11,0 | 14,9 | 25,3 | 0 | 0,0 | 0 |
| Tối ưu thứ tự khóa | 16 | 31.291 | 695,1 | 20,3 | 31,3 | 104,8 | 0 | 0,0 | 0 |
| Tối ưu thứ tự khóa | 32 | 37.720 | 837,9 | 36,0 | 56,2 | 74,3 | 0 | 0,0 | 0 |
| Có các chỉ mục tối ưu | 4 | 26.185 | 581,8 | 6,3 | 9,2 | 15,2 | 0 | 0,0 | 0 |
| Có các chỉ mục tối ưu | 8 | 31.429 | 698,3 | 10,6 | 14,1 | 34,2 | 0 | 0,0 | 0 |
| Có các chỉ mục tối ưu | 16 | 34.149 | 758,7 | 19,7 | 27,8 | 58,8 | 0 | 0,0 | 0 |
| Có các chỉ mục tối ưu | 32 | 35.977 | 799,3 | 36,7 | 61,1 | 92,3 | 0 | 0,0 | 0 |
| Kiểm tra `interpolateParams` (chỉ MySQL) | 4 | 30.355 | 674,5 | 5,6 | 7,1 | 10,8 | 0 | 0,0 | 0 |
| Kiểm tra `interpolateParams` (chỉ MySQL) | 8 | 32.367 | 719,1 | 10,1 | 13,2 | 24,1 | 0 | 0,0 | 0 |
| Kiểm tra `interpolateParams` (chỉ MySQL) | 32 | 38.540 | 856,0 | 36,4 | 48,1 | 67,5 | 0 | 0,0 | 0 |

**MongoDB**

| Giai đoạn | VU | Checkout thành công | TPS | p50 | p95 | p99 | Thử lại | Tỉ lệ thử lại (%) | Hết lượt thử |
|---|---|---|---|---|---|---|---|---|---|
| Baseline, lần 1 | 4 | 81.734 | 1.751,2 | 2,0 | 3,0 | 3,8 | 10 | 0,0 | 0 |
| Baseline, lần 1 | 8 | 121.123 | 2.691,3 | 2,2 | 3,8 | 24,3 | 82 | 0,1 | 0 |
| Baseline, lần 1 | 16 | 121.504 | 2.699,9 | 2,8 | 46,8 | 63,7 | 250 | 0,2 | 0 |
| Baseline, lần 1 | 32 | 120.619 | 2.680,2 | 4,2 | 67,7 | 79,7 | 807 | 0,7 | 2 |
| Baseline, lần 2 | 4 | 86.926 | 1.930,5 | 2,0 | 2,8 | 3,7 | 22 | 0,0 | 0 |
| Baseline, lần 2 | 8 | 118.144 | 2.623,8 | 2,0 | 5,0 | 31,5 | 69 | 0,1 | 0 |
| Baseline, lần 2 | 16 | 120.984 | 2.688,4 | 2,5 | 49,4 | 66,5 | 221 | 0,2 | 0 |
| Baseline, lần 2 | 32 | 120.270 | 2.672,4 | 3,8 | 70,2 | 80,7 | 805 | 0,7 | 1 |
| Tối ưu thứ tự khóa | 4 | 82.744 | 1.838,6 | 2,0 | 3,0 | 4,0 | 41 | 0,0 | 0 |
| Tối ưu thứ tự khóa | 8 | 120.387 | 2.675,2 | 2,2 | 3,9 | 23,2 | 61 | 0,1 | 0 |
| Tối ưu thứ tự khóa | 16 | 121.621 | 2.702,6 | 2,9 | 44,4 | 63,1 | 180 | 0,1 | 0 |
| Tối ưu thứ tự khóa | 32 | 119.394 | 2.653,0 | 4,4 | 66,6 | 78,9 | 893 | 0,7 | 2 |
| Có các chỉ mục tối ưu | 4 | 77.702 | 1.726,6 | 2,0 | 3,1 | 4,4 | 25 | 0,0 | 0 |
| Có các chỉ mục tối ưu | 8 | 96.935 | 2.154,0 | 2,2 | 7,5 | 51,0 | 62 | 0,1 | 0 |
| Có các chỉ mục tối ưu | 16 | 93.989 | 2.086,2 | 2,6 | 61,7 | 77,1 | 132 | 0,1 | 0 |
| Có các chỉ mục tối ưu | 32 | 84.432 | 1.876,2 | 4,6 | 81,7 | 88,9 | 584 | 0,7 | 2 |

## Phụ lục G. Hướng dẫn tái lập thực nghiệm

Điều kiện: Docker và Docker Compose, tệp `.env` (mẫu ở `.env.example`) và dữ liệu trong `seed/data/`. Các lệnh chạy từ thư mục gốc của kho mã.

```bash
# 1. Khởi động hạ tầng, nạp và kiểm tra dữ liệu
docker compose up -d
docker compose --profile seed run --rm seed-mysql
docker compose --profile seed run --rm seed-mongodb
docker compose --profile seed run --rm seed-check-mysql
docker compose --profile seed run --rm seed-check-mongodb
docker compose --profile loadtest build k6

# 2. Nhóm 1: truy vấn quét dữ liệu
python3 benchmark/run_class1.py --phase baseline_analyzed --query-phase baseline --db both
python3 benchmark/optimization.py apply
python3 benchmark/run_class1.py --phase idx --query-phase baseline --db both
python3 benchmark/run_class1.py --phase optimized --db both
python3 benchmark/compare.py
python3 benchmark/optimization.py rollback

# 3. Nhóm 2: tìm kiếm
python3 benchmark/run_class2.py --scenario search_products --phase baseline_r2 --variant baseline --db both
python3 benchmark/optimization.py apply --set search
python3 benchmark/run_class2.py --scenario search_products --phase idx --variant baseline --db both
python3 benchmark/run_class2.py --scenario search_products --phase optimized --variant optimized --db both
python3 benchmark/compare_class2.py --scenario search_products --phases baseline_r2 baseline idx optimized optimized_hint
python3 benchmark/optimization.py rollback --set search

# 4. Nhóm 2: đặt hàng (nạp lại dữ liệu trước mỗi mức tải)
python3 benchmark/run_checkout.py --phase baseline_checkout --db both --levels 4,8,16,32 --duration 45s
python3 benchmark/run_checkout.py --phase optimized_checkout --variant optimized --db both --levels 4,8,16,32 --duration 45s
python3 benchmark/optimization.py apply && python3 benchmark/optimization.py apply --set search
python3 benchmark/run_checkout.py --phase indexed_checkout --indexed --db both --levels 4,8,16,32 --duration 45s
python3 benchmark/optimization.py rollback --set search && python3 benchmark/optimization.py rollback

# 5. Sinh lại các hình của báo cáo
python3 report/figures/make_figures.py
```

Mỗi lần chạy ghi kết quả vào `benchmark/results/<phase>/`. Kiểm tra tính tương đương giữa hai CSDL: truy vấn nhóm 1 tự dừng nếu kết quả khác nhau; tìm kiếm và đặt hàng dùng `-e VERIFY=1` (xem `CLAUDE.md`).

## Phụ lục H. Cấu trúc kho mã nguồn

| Đường dẫn | Nội dung |
|---|---|
| `docker-compose.yml` | MySQL, MongoDB (replica set một nút), dịch vụ nạp dữ liệu và kiểm tra, k6 |
| `schema/mysql/`, `schema/mongodb/` | lược đồ gốc; thư mục con `optimization/` chứa chỉ mục tối ưu và script hoàn nguyên |
| `seed/` | trình nạp (`loaders/`), các kiểm tra logic dữ liệu (`checks/`), dữ liệu (`data/`, không đưa vào kho) |
| `queries/{mysql,mongodb}/{baseline,optimized}/` | năm truy vấn nhóm 1 |
| `benchmark/scenarios/` | kịch bản k6 (tìm kiếm, đặt hàng) và tham số dùng chung (`lib/`) |
| `benchmark/*.py` | script điều phối đo (`run_class1`, `run_class2`, `run_checkout`), áp dụng tối ưu (`optimization`), so sánh (`compare*`), nạp lại dữ liệu (`reset_data`), kiểm tra toàn vẹn (`checkout_integrity`) |
| `benchmark/results/<phase>/` | kết quả từng giai đoạn đo |
| `docs/` | thiết kế (`docs/schema/`), nghiệp vụ đo, ba báo cáo thành phần |
| `report/` | báo cáo này, dàn ý, các hình (`figures/`) |

## Phụ lục I. Nhật ký giả định và điều chỉnh để đo được

| Nội dung | Giá trị hoặc quyết định |
|---|---|
| Định nghĩa doanh thu | chỉ tính đơn `delivered` (giả định của đồ án) |
| Bộ nhớ đệm | cả hai 1536 MB, đặt tường minh; cấu hình mặc định ban đầu là 128 MB (InnoDB) và 1536 MB (WiredTiger) |
| Thống kê MySQL | làm mới (`ANALYZE TABLE`) trước baseline; baseline gốc dùng thống kê cũ và được giữ để đối chiếu |
| Tồn kho khi đo đặt hàng | cộng thêm 100.000 đơn vị mỗi dòng ở cả hai CSDL sau mỗi lần nạp lại, để không checkout nào thất bại vì hết hàng |
| Validator MongoDB | `orders.schema_version` nới từ `int` sang `int` hoặc `long` chỉ trong lúc chạy đặt hàng (công cụ gửi số nguyên là `int64`); các validator khác nguyên vẹn |
| Đơn mới ở MongoDB | dựng từ đơn mẫu đọc từ CSDL (giữ kiểu `Decimal128`, `ObjectId`, ngày); `payment_id` mới tạo phía máy chủ bằng `$toObjectId` |
| Độ bền và cô lập | mặc định của từng CSDL (MySQL: `innodb_flush_log_at_trx_commit=1`, `sync_binlog=1`, REPEATABLE READ; MongoDB: write concern `majority`, read concern `local`) |
| Khóa idempotency | thiết kế có, kịch bản đo không dùng |
| Bộ kiểm tra dữ liệu MongoDB | các so sánh số lượng tồn kho chuyển sang `Number(...)` vì trường được cập nhật bởi công cụ tải là kiểu `Long` |
| Thử lại khi xung đột | tối đa 3 lượt thử kể cả lượt đầu |
| Đo độ nhiễu | baseline của tìm kiếm và đặt hàng đo hai lần; các cấu hình khác một đợt |
