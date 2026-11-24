#!/usr/bin/env bash
# Data-logic checks and aggregates on MySQL; compares with MongoDB results if they exist.
set -uo pipefail
. /checks/lib.sh

export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"
my() { mysql -h mysql -uroot -N -B --default-character-set=utf8mb4 dbperf; }

my < /checks/mysql_logic.sql > "$RESULTS/logic_mysql.tsv" || { echo "MySQL logic query failed"; exit 2; }
my < /checks/mysql_aggregates.sql | LC_ALL=C sort > "$RESULTS/agg_mysql.tsv" || { echo "MySQL aggregate query failed"; exit 2; }

echo "MySQL logic checks:"
status=0
print_logic "$RESULTS/logic_mysql.tsv" || status=1
compare_with_other mysql mongodb || status=1
exit $status
