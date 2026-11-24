#!/usr/bin/env bash
# Truncate and reload all MySQL tables from the CSVs, then verify counts.
# Runs in the seed-mysql container. The CSVs are staged into the mysql_files volume, which the
# server mounts as /var/lib/mysql-files (its secure_file_priv), then read with server-side
# LOAD DATA INFILE: no local_infile, and strict-mode errors are kept (LOCAL downgrades them).
set -euo pipefail
. /loaders/lib.sh

export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"
SRV=/var/lib/mysql-files
my() { mysql -h mysql -uroot --default-character-set=utf8mb4 dbperf "$@"; }

# Parent tables first (FK order); line_total of order_detail is GENERATED, so it is not listed.
TABLES=(category product sku warehouse inventory customer orders order_detail payment)
declare -A COLS=(
  [category]="category_id,name,status,created_at"
  [product]="product_id,category_id,name,description,status,created_at,updated_at"
  [sku]="sku_id,product_id,sku_code,variant_attributes,current_price,status,updated_at"
  [warehouse]="warehouse_id,name,address,city,status"
  [inventory]="inventory_id,sku_id,warehouse_id,quantity_on_hand,quantity_reserved,updated_at"
  [customer]="customer_id,full_name,address,email,phone,created_at,updated_at"
  [orders]="order_id,customer_id,status,shipping_recipient_name,shipping_phone,shipping_address,total_amount,created_at"
  [order_detail]="order_detail_id,order_id,sku_id,unit_price_snapshot,quantity,warehouse_id"
  [payment]="payment_id,order_id,payment_method,amount,status,created_at"
)

echo "Staging CSVs..."
cp /seed-data/mysql/*.csv /stage/
trap 'rm -f /stage/*.csv' EXIT

echo "Truncating tables..."
{
  echo "SET FOREIGN_KEY_CHECKS=0;"
  for t in "${TABLES[@]}"; do echo "TRUNCATE TABLE $t;"; done
} | my

echo "Loading ${#TABLES[@]} tables into MySQL..."
total_start=$(now_ms)
for t in "${TABLES[@]}"; do
  start=$(now_ms)
  my -e "LOAD DATA INFILE '$SRV/$t.csv' INTO TABLE $t CHARACTER SET utf8mb4
         FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '\"' ESCAPED BY '\\\\'
         LINES TERMINATED BY '\\n' IGNORE 1 LINES (${COLS[$t]});"
  printf '  %-13s %6d ms\n' "$t" $(( $(now_ms) - start ))
done
echo "MySQL load finished in $(( $(now_ms) - total_start )) ms"

/loaders/verify_mysql.sh
