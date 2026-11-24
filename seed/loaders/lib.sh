# Shared helpers, sourced by the loader scripts. Runs inside the seed-* containers.

MANIFEST=/seed-data/manifest.json

# manifest_count <key>: value of "counts"."<key>" in manifest.json (no jq in the images).
manifest_count() {
  awk -v k="\"$1\"" '/"counts": \{/ {on=1; next} on && /\}/ {exit} on && $1 == k":" {gsub(/[^0-9]/, "", $2); print $2}' "$MANIFEST"
}

now_ms() { echo $(( $(date +%s%N) / 1000000 )); }

# check <label> <expected> <actual>: print OK/FAIL and remember a failure in $FAILED.
FAILED=0
check() {
  if [ "$2" = "$3" ]; then printf '  OK    %-18s %s\n' "$1" "$3"
  else printf '  FAIL  %-18s expected %s, got %s\n' "$1" "$2" "$3"; FAILED=1; fi
}
