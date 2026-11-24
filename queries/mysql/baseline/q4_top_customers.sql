-- q4: Top 20 customers by total spend. Delivered orders only, all time. Top N = 20 is the literal in LIMIT,
--   because MySQL does not accept a user variable in LIMIT.
-- Parameters: none besides top N.
-- Output columns, in order: email, order_count, total_spent (2 decimals)

SELECT
  c.email,
  COUNT(*) AS order_count,
  ROUND(SUM(o.total_amount), 2) AS total_spent
FROM orders o
JOIN customer c ON c.customer_id = o.customer_id
WHERE o.status = 'delivered'
GROUP BY c.customer_id, c.email
ORDER BY total_spent DESC, c.email ASC
LIMIT 20;
