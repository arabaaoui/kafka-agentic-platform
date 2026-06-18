#!/usr/bin/env bash
# Eval CI gate — kafka-agentic-platform v0
# Exit 0 if pass rate >= 80%, exit 1 otherwise.
# Usage: ./evals/run_evals.sh [--output-file results.json]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
OUTPUT="${2:-${ROOT}/.platform/eval_results.json}"

mkdir -p "$(dirname "${OUTPUT}")"

echo "=== kafka-agentic-platform eval suite ==="
echo "Config: ${SCRIPT_DIR}/promptfoo.yaml"
echo "Output: ${OUTPUT}"
echo ""

# Run promptfoo and capture JSON output
promptfoo eval \
  --config "${SCRIPT_DIR}/promptfoo.yaml" \
  --output "${OUTPUT}" \
  --output-format json \
  --no-cache \
  2>&1

# Parse pass rate from JSON output
PASS_RATE=$(python3 - <<'EOF'
import json, sys

with open(sys.argv[1]) as f:
    data = json.load(f)

results = data.get("results", {})
total = results.get("stats", {}).get("successes", 0) + results.get("stats", {}).get("failures", 0)
passed = results.get("stats", {}).get("successes", 0)

if total == 0:
    print("0.0")
else:
    print(f"{passed / total:.4f}")
EOF
"${OUTPUT}")

echo ""
echo "=== Eval results ==="
echo "Pass rate: ${PASS_RATE}"

# Gate: fail CI if below 80%
python3 -c "
rate = float('${PASS_RATE}')
threshold = 0.80
print(f'Pass rate: {rate:.1%} (threshold: {threshold:.0%})')
if rate < threshold:
    print(f'FAIL: pass rate {rate:.1%} below CI gate {threshold:.0%}')
    raise SystemExit(1)
print('PASS: eval suite above CI gate')
"
