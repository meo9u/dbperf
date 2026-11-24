#!/usr/bin/env bash
# Data-logic checks and aggregates on MongoDB; compares with MySQL results if they exist.
set -uo pipefail
. /checks/lib.sh

mg() {
  mongosh --host "rs0/mongodb:27017" --username "$MONGO_ROOT_USERNAME" --password "$MONGO_ROOT_PASSWORD" \
    --authenticationDatabase admin --quiet --file "$1"
}

mg /checks/mongodb_logic.js > "$RESULTS/logic_mongodb.tsv" || { echo "MongoDB logic script failed"; exit 2; }
mg /checks/mongodb_aggregates.js | LC_ALL=C sort > "$RESULTS/agg_mongodb.tsv" || { echo "MongoDB aggregate script failed"; exit 2; }

echo "MongoDB logic checks:"
status=0
print_logic "$RESULTS/logic_mongodb.tsv" || status=1
compare_with_other mongodb mysql || status=1
exit $status
