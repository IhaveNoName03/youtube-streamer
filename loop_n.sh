#!/usr/bin/env bash
# Run the regression suite N times; report per-run status and an aggregate
# flake verdict. Used to prove the loop is deterministic.
set -u
cd /home/cachyos/youtubedl
PY=/home/cachyos/youtubedl/.venv/bin/python
N=${1:-10}

pass=0; fail=0
for i in $(seq 1 "$N"); do
  out=$(timeout 180 "$PY" -m pytest tests/ -q --no-header -p no:cacheprovider 2>&1)
  line=$(echo "$out" | grep -E "passed|failed" | tail -1)
  if echo "$out" | grep -qE "FAILED|^ERROR"; then
    status="FAIL"; fail=$((fail+1))
  else
    status="PASS"; pass=$((pass+1))
  fi
  printf "run %2d: %-4s %s\n" "$i" "$status" "$line"
done

echo
echo "================================"
echo "AGGREGATE over $N runs"
echo "  passed: $pass"
echo "  failed: $fail"
if [ "$fail" -eq 0 ]; then
  echo "  VERDICT: deterministic (0/$N flakes)"
else
  echo "  VERDICT: FLAKY — $fail/$N failed"
fi
echo "================================"
[ "$fail" -eq 0 ]