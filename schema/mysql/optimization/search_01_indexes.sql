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
