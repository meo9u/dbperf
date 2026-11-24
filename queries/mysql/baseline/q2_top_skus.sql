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
