-- Business aggregates on MySQL, one "key<TAB>value" row each. mongodb_aggregates.js prints the
-- same keys and formats; the runner diffs the two outputs. Money is DECIMAL(12,2) as text.
SET time_zone = '+00:00';

SELECT CONCAT('orders_by_status|', status), CONCAT(COUNT(*), '|', SUM(total_amount)) FROM orders GROUP BY status
UNION ALL SELECT CONCAT('revenue_by_month|', ym), CONCAT(n, '|', s) FROM (
    SELECT DATE_FORMAT(created_at, '%Y-%m') ym, COUNT(*) n, SUM(total_amount) s FROM orders GROUP BY ym) m
UNION ALL SELECT CONCAT('customers_by_order_count|', cnt), COUNT(*) FROM (
    SELECT COUNT(o.order_id) cnt FROM customer c LEFT JOIN orders o USING (customer_id) GROUP BY c.customer_id) x GROUP BY cnt
UNION ALL SELECT CONCAT('orders_by_payment_count|', cnt), COUNT(*) FROM (
    SELECT COUNT(*) cnt FROM payment GROUP BY order_id) x GROUP BY cnt
UNION ALL SELECT CONCAT('orders_by_line_count|', cnt), COUNT(*) FROM (
    SELECT COUNT(*) cnt FROM order_detail GROUP BY order_id) x GROUP BY cnt
UNION ALL SELECT 'lines_total', CONCAT(COUNT(*), '|', SUM(quantity), '|', SUM(line_total), '|', COUNT(DISTINCT sku_id)) FROM order_detail
UNION ALL SELECT CONCAT('payments|', payment_method, '|', status), CONCAT(COUNT(*), '|', SUM(amount)) FROM payment GROUP BY payment_method, status
UNION ALL SELECT 'inventory_total', CONCAT(COUNT(*), '|', SUM(quantity_on_hand), '|', SUM(quantity_reserved)) FROM inventory
UNION ALL SELECT CONCAT('sku_by_status|', status), CONCAT(COUNT(*), '|', SUM(current_price)) FROM sku GROUP BY status;
