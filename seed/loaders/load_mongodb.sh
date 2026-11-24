#!/usr/bin/env bash
# Empty and reload all MongoDB collections from the JSONL files, then verify counts.
# Runs in the seed-mongodb container. Collections are emptied with deleteMany (not dropped)
# so the validators and unique indexes from schema/mongodb/ stay in place and every
# inserted document is checked by the $jsonSchema validators.
set -euo pipefail
. /loaders/lib.sh

RS="rs0/mongodb:27017"
AUTH=(--username "$MONGO_ROOT_USERNAME" --password "$MONGO_ROOT_PASSWORD" --authenticationDatabase admin)
COLLECTIONS=(categories warehouses customers products inventory orders)

echo "Emptying collections..."
for c in "${COLLECTIONS[@]}"; do
  mongosh --host "$RS" "${AUTH[@]}" --quiet dbperf --eval "db.$c.deleteMany({})" >/dev/null
done

echo "Loading ${#COLLECTIONS[@]} collections into MongoDB..."
total_start=$(now_ms)
for c in "${COLLECTIONS[@]}"; do
  start=$(now_ms)
  mongoimport --host "$RS" "${AUTH[@]}" --db dbperf --collection "$c" \
    --file "/seed-data/mongodb/$c.jsonl" --type json \
    --mode insert --numInsertionWorkers 4 --stopOnError --quiet
  printf '  %-13s %6d ms\n' "$c" $(( $(now_ms) - start ))
done
echo "MongoDB load finished in $(( $(now_ms) - total_start )) ms"

/loaders/verify_mongodb.sh
