-- Restores the baseline schema (undoes 01_indexes.sql).
-- Re-run safe: not idempotent, so if it stops half way, run only the statements that are still pending.
USE dbperf;
ALTER TABLE orders
  DROP INDEX idx_orders_status_created_total,
  DROP INDEX idx_orders_status_customer_total;
-- Creating idx_order_detail_cover made MySQL drop the now-redundant FK index fk_order_detail_order;
-- put it back in the same statement, since the foreign key needs an index at every moment.
ALTER TABLE order_detail
  ADD INDEX fk_order_detail_order (order_id),
  DROP INDEX idx_order_detail_cover;
ALTER TABLE inventory DROP INDEX idx_inventory_available, DROP COLUMN quantity_available;
ANALYZE TABLE orders, order_detail, inventory;
