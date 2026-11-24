-- Data-logic checks on MySQL. One row per check: name, severity, violations.
--   FAIL: must be 0 (the runner exits non-zero otherwise)
--   WARN: should be 0 but is a known or tolerated data issue, reported only
--   INFO: a measurement, no pass or fail
-- Every name here has an equivalent in mongodb_logic.js; the runner compares their counts.
SET time_zone = '+00:00';

SELECT 'fk_line_sku', 'FAIL', COUNT(*) FROM order_detail d LEFT JOIN sku s USING (sku_id) WHERE s.sku_id IS NULL
UNION ALL SELECT 'fk_line_warehouse', 'FAIL', COUNT(*) FROM order_detail d LEFT JOIN warehouse w USING (warehouse_id) WHERE d.warehouse_id IS NOT NULL AND w.warehouse_id IS NULL
UNION ALL SELECT 'fk_order_customer', 'FAIL', COUNT(*) FROM orders o LEFT JOIN customer c USING (customer_id) WHERE c.customer_id IS NULL
UNION ALL SELECT 'fk_product_category', 'FAIL', COUNT(*) FROM product p LEFT JOIN category c USING (category_id) WHERE c.category_id IS NULL
UNION ALL SELECT 'fk_inventory_refs', 'FAIL', COUNT(*) FROM inventory i LEFT JOIN sku s USING (sku_id) LEFT JOIN warehouse w USING (warehouse_id) WHERE s.sku_id IS NULL OR w.warehouse_id IS NULL
UNION ALL SELECT 'order_zero_lines', 'FAIL', COUNT(*) FROM orders o WHERE NOT EXISTS (SELECT 1 FROM order_detail d WHERE d.order_id = o.order_id)
UNION ALL SELECT 'order_has_no_payment', 'FAIL', COUNT(*) FROM orders o WHERE NOT EXISTS (SELECT 1 FROM payment p WHERE p.order_id = o.order_id)
UNION ALL SELECT 'payments_over_5_per_order', 'FAIL', COUNT(*) FROM (SELECT order_id FROM payment GROUP BY order_id HAVING COUNT(*) > 5) x
UNION ALL SELECT 'dup_sku_in_order', 'FAIL', COUNT(*) FROM (SELECT order_id, sku_id FROM order_detail GROUP BY order_id, sku_id HAVING COUNT(*) > 1) x
UNION ALL SELECT 'total_ne_line_sum', 'FAIL', COUNT(*) FROM orders o JOIN (SELECT order_id, SUM(line_total) s FROM order_detail GROUP BY order_id) d USING (order_id) WHERE o.total_amount <> d.s
UNION ALL SELECT 'payment_sum_ne_total', 'FAIL', COUNT(*) FROM orders o JOIN (SELECT order_id, SUM(amount) s FROM payment GROUP BY order_id) p USING (order_id) WHERE o.total_amount <> p.s
UNION ALL SELECT 'order_total_not_positive', 'FAIL', COUNT(*) FROM orders WHERE total_amount <= 0
UNION ALL SELECT 'line_price_not_positive', 'FAIL', COUNT(*) FROM order_detail WHERE unit_price_snapshot <= 0
UNION ALL SELECT 'customer_phone_format', 'FAIL', COUNT(*) FROM customer WHERE phone IS NOT NULL AND phone NOT REGEXP '^\\+[0-9]{5,16}$'
UNION ALL SELECT 'shipping_phone_format', 'FAIL', COUNT(*) FROM orders WHERE shipping_phone NOT REGEXP '^\\+[0-9]{5,16}$'
UNION ALL SELECT 'customer_email_format', 'FAIL', COUNT(*) FROM customer WHERE email NOT REGEXP '^[^ @]+@[^ @]+\\.[^ @]+$'
UNION ALL SELECT 'time_order_before_customer', 'FAIL', COUNT(*) FROM orders o JOIN customer c USING (customer_id) WHERE o.created_at < c.created_at
UNION ALL SELECT 'time_payment_before_order', 'FAIL', COUNT(*) FROM payment p JOIN orders o USING (order_id) WHERE p.created_at < o.created_at
UNION ALL SELECT 'time_order_before_product', 'FAIL', COUNT(*) FROM orders o WHERE EXISTS (
    SELECT 1 FROM order_detail d JOIN sku s USING (sku_id) JOIN product p USING (product_id)
    WHERE d.order_id = o.order_id AND p.created_at > o.created_at)
UNION ALL SELECT 'status_payment_consistency', 'FAIL', COUNT(*) FROM payment p JOIN orders o USING (order_id) WHERE NOT (
       (o.status = 'pending'   AND p.status = 'pending')
    OR (o.status IN ('shipped', 'delivered') AND p.status = 'success')
    OR (o.status = 'cancelled' AND p.status IN ('failed', 'refunded', 'pending'))
    OR (o.status = 'returned'  AND p.status = 'refunded'))
UNION ALL SELECT 'inventory_reserved_gt_on_hand', 'FAIL', COUNT(*) FROM inventory WHERE quantity_reserved > quantity_on_hand
UNION ALL SELECT 'inventory_reserved_ne_pending', 'FAIL',
    (SELECT COUNT(*) FROM inventory i LEFT JOIN (
        SELECT d.sku_id, d.warehouse_id, SUM(d.quantity) q FROM order_detail d JOIN orders o USING (order_id)
        WHERE o.status = 'pending' AND d.warehouse_id IS NOT NULL GROUP BY d.sku_id, d.warehouse_id) pq
      USING (sku_id, warehouse_id) WHERE i.quantity_reserved <> COALESCE(pq.q, 0))
  + (SELECT COUNT(*) FROM (
        SELECT d.sku_id, d.warehouse_id FROM order_detail d JOIN orders o USING (order_id)
        WHERE o.status = 'pending' AND d.warehouse_id IS NOT NULL GROUP BY d.sku_id, d.warehouse_id) pk
      LEFT JOIN inventory i USING (sku_id, warehouse_id) WHERE i.inventory_id IS NULL)
UNION ALL SELECT 'stale_pending_orders', 'WARN', COUNT(*) FROM orders WHERE status = 'pending' AND created_at < (SELECT MAX(created_at) FROM orders) - INTERVAL 30 DAY
UNION ALL SELECT 'stale_shipped_orders', 'WARN', COUNT(*) FROM orders WHERE status = 'shipped' AND created_at < (SELECT MAX(created_at) FROM orders) - INTERVAL 30 DAY
UNION ALL SELECT 'customer_updated_before_created', 'WARN', COUNT(*) FROM customer WHERE updated_at < created_at
UNION ALL SELECT 'product_updated_before_created', 'WARN', COUNT(*) FROM product WHERE updated_at < created_at
UNION ALL SELECT 'line_price_differs_from_catalog', 'INFO', COUNT(*) FROM order_detail d JOIN sku s USING (sku_id) WHERE d.unit_price_snapshot <> s.current_price
UNION ALL SELECT 'line_on_inactive_sku', 'INFO', COUNT(*) FROM order_detail d JOIN sku s USING (sku_id) WHERE s.status = 'inactive'
UNION ALL SELECT 'sku_never_ordered', 'INFO', COUNT(*) FROM sku s WHERE NOT EXISTS (SELECT 1 FROM order_detail d WHERE d.sku_id = s.sku_id)
UNION ALL SELECT 'cancelled_line_has_warehouse', 'INFO', COUNT(*) FROM order_detail d JOIN orders o USING (order_id) WHERE o.status = 'cancelled' AND d.warehouse_id IS NOT NULL
UNION ALL SELECT 'recipient_differs_from_customer', 'INFO', COUNT(*) FROM orders o JOIN customer c USING (customer_id) WHERE BINARY o.shipping_recipient_name <> BINARY c.full_name;
