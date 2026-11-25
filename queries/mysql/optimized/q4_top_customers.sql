-- q4 (optimized): Top 20 customers by total spend. Delivered orders only, all time. Top N = 20 is the literal in LIMIT.
-- Phase 5: aggregate orders by customer_id from the covering index idx_orders_status_customer_total, then join customer.
-- Parameters: none besides top N.
-- Output columns, in order: email, order_count, total_spent (2 decimals)
SELECT
  c.email,
  t.order_count,
  ROUND(t.spent, 2) AS total_spent
FROM (
  SELECT customer_id, COUNT(*) AS order_count, SUM(total_amount) AS spent
  FROM orders
  WHERE status = 'delivered'
  GROUP BY customer_id
) t
JOIN customer c ON c.customer_id = t.customer_id
ORDER BY total_spent DESC, c.email ASC
LIMIT 20;
