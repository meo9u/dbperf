-- q3: Revenue by product category, all time. Delivered orders only; categories with no sales are omitted.
-- Parameters: none (full scan of delivered orders by design).
-- Output columns, in order: category_name, units_sold, revenue (2 decimals)
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
GROUP BY c.category_id, c.name
ORDER BY revenue DESC, c.name ASC;
