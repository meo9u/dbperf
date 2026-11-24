# Shared helpers for check_mysql.sh and check_mongodb.sh (run inside the seed-check-* containers).
# Results are kept in the seed_results volume (/results) so whichever side runs second can
# compare against the first: logic_<db>.tsv (name, severity, violations) and agg_<db>.tsv (key, value).

RESULTS=/results
mkdir -p "$RESULTS"

# print_logic <file>: table of results, returns 1 if any FAIL check has violations.
print_logic() {
  awk -F'\t' '
    { printf "  %-5s %-34s %s\n", ($2=="FAIL" && $3>0) ? "FAIL" : ($2=="WARN" && $3>0 ? "WARN" : ($2=="INFO" ? "INFO" : "OK")), $1, $3
      if ($2=="FAIL" && $3>0) bad++ }
    END { printf "  -> %d FAIL check(s) with violations\n", bad+0; exit bad>0 }' "$1"
}

# compare_with_other <this> <other> : logic counts and aggregates must match across the two DBs.
compare_with_other() {
  local this=$1 other=$2 status=0
  if [ ! -f "$RESULTS/logic_$other.tsv" ]; then
    echo "Cross-DB comparison skipped: run the $other check too (results are kept in the seed_results volume)."
    return 0
  fi
  echo "Cross-DB comparison with $other (results from $(date -r "$RESULTS/logic_$other.tsv" '+%F %T')):"
  local a b
  if [ "$this" = mysql ]; then a=$RESULTS/logic_mysql.tsv b=$RESULTS/logic_mongodb.tsv; else a=$RESULTS/logic_mysql.tsv b=$RESULTS/logic_mongodb.tsv; fi
  # Same check name -> same violation count (a mismatch means the data or a check differs between DBs).
  local diffs
  diffs=$(awk -F'\t' 'NR==FNR {m[$1]=$3; next} ($1 in m) && m[$1]!=$3 { printf "    %-34s mysql=%s mongodb=%s\n", $1, m[$1], $3 }' "$a" "$b")
  if [ -n "$diffs" ]; then echo "  FAIL  logic check counts differ:"; echo "$diffs"; status=1
  else echo "  OK    logic check counts identical ($(wc -l < "$a" | tr -d ' ') MySQL checks, $(wc -l < "$b" | tr -d ' ') MongoDB checks)"; fi
  diffs=$(diff <(LC_ALL=C sort "$RESULTS/agg_mysql.tsv") <(LC_ALL=C sort "$RESULTS/agg_mongodb.tsv") || true)
  if [ -n "$diffs" ]; then echo "  FAIL  aggregates differ (< mysql, > mongodb):"; echo "$diffs" | head -40; status=1
  else echo "  OK    aggregates identical ($(wc -l < "$RESULTS/agg_mysql.tsv" | tr -d ' ') rows)"; fi
  return $status
}
