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
