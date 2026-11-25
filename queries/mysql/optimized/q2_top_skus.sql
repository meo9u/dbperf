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
