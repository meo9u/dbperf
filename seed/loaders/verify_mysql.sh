#!/usr/bin/env bash
# Compare MySQL row counts with seed/data/manifest.json.
set -euo pipefail
. /loaders/lib.sh

export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"
echo "MySQL counts vs manifest:"
for t in category product sku warehouse inventory customer orders order_detail payment; do
  check "$t" "$(manifest_count "$t")" "$(mysql -h mysql -uroot -N -B dbperf -e "SELECT COUNT(*) FROM $t")"
done
exit $FAILED
