-- Restores the baseline schema (undoes 01_indexes.sql).
-- Re-run safe: not idempotent, so if it stops half way, run only the statements that are still pending.
USE dbperf;
ALTER TABLE orders
  DROP INDEX idx_orders_status_created_total,
  DROP INDEX idx_orders_status_customer_total;
-- Creating idx_order_detail_cover makes MySQL drop the FK helper index fk_order_detail_order, but only when that
-- index was created implicitly with the foreign key (a fresh schema). If it was re-created by hand it stays, so
-- the rollback adds it back only when it is missing (the foreign key needs an index at every moment).
SET @has_fk_index := (SELECT COUNT(*) FROM information_schema.statistics
  WHERE table_schema = 'dbperf' AND table_name = 'order_detail' AND index_name = 'fk_order_detail_order');
SET @sql := IF(@has_fk_index = 0,
  'ALTER TABLE order_detail ADD INDEX fk_order_detail_order (order_id), DROP INDEX idx_order_detail_cover',
  'ALTER TABLE order_detail DROP INDEX idx_order_detail_cover');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
ALTER TABLE inventory DROP INDEX idx_inventory_available, DROP COLUMN quantity_available;
ANALYZE TABLE orders, order_detail, inventory;
