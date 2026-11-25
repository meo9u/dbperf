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
