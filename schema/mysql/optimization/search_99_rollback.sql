-- Restores the baseline schema (undoes search_01_indexes.sql).
-- idx_sku_search and idx_product_category_status start with the foreign key column, so MySQL drops the FK helper
-- indexes that were created implicitly with the foreign keys (fk_sku_product, fk_product_category). Put each back
-- only when it is missing (the foreign key needs an index at every moment), in the same statement as the drop.
USE dbperf;

SET @has := (SELECT COUNT(*) FROM information_schema.statistics
  WHERE table_schema = 'dbperf' AND table_name = 'sku' AND index_name = 'fk_sku_product');
SET @sql := IF(@has = 0,
  'ALTER TABLE sku ADD INDEX fk_sku_product (product_id), DROP INDEX idx_sku_search, DROP COLUMN color',
  'ALTER TABLE sku DROP INDEX idx_sku_search, DROP COLUMN color');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @has := (SELECT COUNT(*) FROM information_schema.statistics
  WHERE table_schema = 'dbperf' AND table_name = 'product' AND index_name = 'fk_product_category');
SET @sql := IF(@has = 0,
  'ALTER TABLE product ADD INDEX fk_product_category (category_id), DROP INDEX idx_product_category_status',
  'ALTER TABLE product DROP INDEX idx_product_category_status');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

ANALYZE TABLE sku, product;
