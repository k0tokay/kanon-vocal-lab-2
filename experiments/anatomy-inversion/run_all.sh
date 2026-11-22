#!/bin/zsh
# Runs the oracle bound and the three EmJEm conditions on data/synth-v1, each followed by evaluation.
# Run from this directory: ./run_all.sh [ITERATIONS]
set -e
iterations=${1:-120}
until [[ -f data/synth-v1/meta.json ]]; do sleep 5; done
filter() { grep -v --line-buffered "Creating a gestural\|ATTENTION\|UserWarning\|warnings.warn"; }
python3 emjem.py data/synth-v1 runs/oracle --mode oracle --iterations 60 2>&1 | filter > runs-oracle.log
python3 evaluate.py data/synth-v1 runs/oracle 2>&1 | filter >> runs-oracle.log
for mode in sp fix ut; do
  python3 emjem.py data/synth-v1 runs/$mode --mode $mode --iterations $iterations 2>&1 | filter > runs-$mode.log
  python3 evaluate.py data/synth-v1 runs/$mode 2>&1 | filter >> runs-$mode.log
done
echo done
