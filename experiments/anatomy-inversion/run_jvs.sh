#!/usr/bin/env bash
# EmJEm on the JVS corpus: prepares the data (once), trains each mode (resuming if interrupted) and evaluates.
# Run from this directory: ./run_jvs.sh JVS_ROOT DATA_DIR RUNS_DIR
# Environment: MODES (default "sp fix"), ITERATIONS (120), PER_ITERATION (600), WORKERS (all CPUs).
set -euo pipefail
jvs=$1 data=$2 runs=$3
modes=${MODES:-sp fix}
iterations=${ITERATIONS:-120}
per_iteration=${PER_ITERATION:-600}
workers=${WORKERS:-$(python3 -c "import os; print(os.cpu_count())")}
filter() { grep -v --line-buffered "Creating a gestural\|ATTENTION\|UserWarning\|warnings.warn\|Cholesky" || true; }
if [[ ! -f $data/meta.json ]]; then
  python3 prep_jvs.py "$jvs" "$data"
fi
for mode in $modes; do
  mkdir -p "$runs/$mode"
  python3 emjem.py "$data" "$runs/$mode" --mode "$mode" --iterations "$iterations" \
    --per-iteration "$per_iteration" --workers "$workers" --resume 2>&1 | filter | tee -a "$runs/$mode/train.log"
  python3 evaluate_real.py "$data" "$runs/$mode" --workers "$workers" 2>&1 | filter | tee "$runs/$mode/eval.log"
done
