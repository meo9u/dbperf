-- q3: Revenue by product category in a period. Delivered orders only; categories with no sales are omitted.
-- Parameters: @from_date (inclusive), @to_date (exclusive), UTC.
-- Output columns, in order: category_name, units_sold, revenue (2 decimals)
SET time_zone = '+00:00';
SET @from_date = '2019-01-01 00:00:00';
SET @to_date = '2020-01-01 00:00:00';

SELECT
  c.name AS category_name,
  CAST(SUM(d.quantity) AS UNSIGNED) AS units_sold,
  ROUND(SUM(d.line_total), 2) AS revenue
FROM orders o
JOIN order_detail d ON d.order_id = o.order_id
JOIN sku s ON s.sku_id = d.sku_id
JOIN product p ON p.product_id = s.product_id
JOIN category c ON c.category_id = p.category_id
WHERE o.status = 'delivered'
  AND o.created_at >= @from_date
  AND o.created_at < @to_date
GROUP BY c.category_id, c.name
ORDER BY revenue DESC, c.name ASC;
