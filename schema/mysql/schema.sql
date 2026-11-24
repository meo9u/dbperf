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
