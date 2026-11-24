#!/usr/bin/env bash
# Compare MongoDB document counts with seed/data/manifest.json. Payments, order lines and
# SKUs are embedded, so they are compared by the summed length of their arrays.
set -euo pipefail
. /loaders/lib.sh

mg() {
  mongosh --host "rs0/mongodb:27017" --username "$MONGO_ROOT_USERNAME" --password "$MONGO_ROOT_PASSWORD" \
    --authenticationDatabase admin --quiet dbperf --eval "$1"
}
arrsum() { mg "db.$1.aggregate([{\$group:{_id:null,n:{\$sum:{\$size:\"\$$2\"}}}}]).toArray()[0].n"; }

echo "MongoDB counts vs manifest:"
check categories "$(manifest_count category)" "$(mg 'db.categories.countDocuments()')"
check warehouses "$(manifest_count warehouse)" "$(mg 'db.warehouses.countDocuments()')"
check customers "$(manifest_count customer)" "$(mg 'db.customers.countDocuments()')"
check products "$(manifest_count product)" "$(mg 'db.products.countDocuments()')"
check skus "$(manifest_count sku)" "$(arrsum products skus)"
check inventory "$(manifest_count inventory)" "$(mg 'db.inventory.countDocuments()')"
check orders "$(manifest_count orders)" "$(mg 'db.orders.countDocuments()')"
check orders.lines "$(manifest_count order_detail)" "$(arrsum orders lines)"
check orders.payments "$(manifest_count payment)" "$(arrsum orders payments)"
exit $FAILED
