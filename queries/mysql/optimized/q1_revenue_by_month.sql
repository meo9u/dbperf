-- Phase 5: unchanged query; served by covering index idx_orders_status_created_total.
-- q1: Revenue by month. Delivered orders only, grouped by the month the order was placed (UTC), whole table.
-- Parameters: none (full scan of orders by design).
-- Output columns, in order: order_month (YYYY-MM), order_count, revenue (2 decimals)
SET time_zone = '+00:00';

SELECT
  DATE_FORMAT(created_at, '%Y-%m') AS order_month,
  COUNT(*) AS order_count,
  ROUND(SUM(total_amount), 2) AS revenue
FROM orders
WHERE status = 'delivered'
GROUP BY order_month
ORDER BY order_month;
