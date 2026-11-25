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
