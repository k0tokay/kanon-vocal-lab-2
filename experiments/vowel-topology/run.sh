#!/bin/sh
# Full pipeline for one vowel: sampling, Rips, normals, checked edges, joining.
# Usage: sh run.sh <vowel> [python]   (run from experiments/vowel-topology)
set -e
V=$1; P=${2:-python3}; R=results/kanon-$V
$P sample.py --vowel $V --seeds $(seq 42 51) --steps 3000 --workers 10 --fresh
for k in 2 3 4 5; do $P sample.py --vowel $V --seeds $(seq 42 51) --steps 3000 --workers 10; done
echo "== rips"; $P rips.py $R/samples.npz --tolerances .01 .05
echo "== spectrum"; $P spectrum.py $R/samples.npz --workers 10
echo "== paths 0.05"; $P paths.py $R/samples.npz --workers 10
echo "== paths 0.01"; $P paths.py $R/samples.npz --cap .01 --neighbours 15 --workers 10 --out $R/samples-edges-0.01.npz
echo "== connect"; $P connect.py --samples $R/samples.npz --workers 10
echo "== cluster"; $P cluster.py $R/samples.npz
echo "== outlines"; $P outlines.py $R/samples.npz --shapes ${SHAPES:-$V-compare}
