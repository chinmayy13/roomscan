#!/usr/bin/env bash
# Regenerate every number in BENCHMARK.md and the fix-loop bundle from the raw Stray Scanner zips.
#   bash reproduce.sh /path/to/folder/with/zips
# Expects: single_room.zip, single_scan_floor_only.zip, single_scan_with_ceiling.zip
# First run fuses depth (~4 min total); later runs reuse out/*/chunks.pkl and take ~1 min.
set -euo pipefail
RAW=${1:?usage: bash reproduce.sh /path/to/raw_zips}
PY=${PYTHON:-python}
mkdir -p out results fixloop/before fixloop/after fixloop/iteration2_typical_dims fixloop/iteration3_corner_bias fixloop/firstpass_unstable_yaw docs/figures results/plans

python tests/test_synthetic.py | tee results/synthetic_test.txt
python tests/test_determinism.py | tee results/determinism_test.txt

for c in single_room single_scan_floor_only single_scan_with_ceiling; do
  echo "== $c"
  $PY -m roomscan "$RAW/$c.zip" --out "out/$c" | tee "results/$c.txt"            # main run: drift on, square kernels
  for v in nodrift wall legacy; do mkdir -p "out/${c}_$v"; cp "out/$c/chunks.pkl" "out/${c}_$v/"; done   # reuse fused depth
  $PY -m roomscan "$RAW/$c.zip" --out "out/${c}_nodrift" --no-drift          > "results/${c}_nodrift.txt"
  $PY -m roomscan "$RAW/$c.zip" --out "out/${c}_wall"    --room-dims wall    > "results/${c}_wall.txt"
  $PY -m roomscan "$RAW/$c.zip" --out "out/${c}_legacy"  --legacy-geometry   > "results/${c}_legacy.txt"
  cp "out/$c/plan.png" "docs/figures/plan_$c.png"; cp "out/$c/plan.json" "results/plans/$c.json"
done
$PY scripts/validate_schema.py out/single_room/plan.json out/single_scan_floor_only/plan.json out/single_scan_with_ceiling/plan.json | tee results/schema_validation.txt

A=out/single_scan_floor_only; B=out/single_scan_with_ceiling
# fix loop, declared fix (iteration 1): old geometry, extent (before) vs wall-to-wall (after)
$PY scripts/repeatability.py "${A}_legacy" "${B}_legacy" | tee fixloop/before/repeatability.txt
$PY scripts/diagnose_repeatability.py "${A}_legacy" "${B}_legacy" | tee fixloop/before/diagnosis.txt
# wall-to-wall on the OLD geometry is what was measured at the time; reproduce it exactly:
for c in single_scan_floor_only single_scan_with_ceiling; do $PY -m roomscan "$RAW/$c.zip" --out "out/${c}_wall" --room-dims wall --legacy-geometry > /dev/null; done
$PY scripts/repeatability.py "${A}_wall" "${B}_wall" | tee fixloop/after/repeatability.txt
$PY scripts/overlay.py "${A}_legacy" "${B}_legacy" fixloop/before/overlay.png
# iteration 2 (typical dimensions): failed; and the diagnosis experiments
$PY scripts/experiments/typical_dimensions.py "${A}_legacy" "${B}_legacy" | tee fixloop/iteration2_typical_dims/result.txt
$PY scripts/experiments/boundedness.py "${A}_legacy" "${B}_legacy"        | tee fixloop/iteration2_typical_dims/boundedness.txt
$PY scripts/experiments/face_repeatability_local.py "${A}_legacy" "${B}_legacy" | tee fixloop/iteration2_typical_dims/face_local.txt
# iteration 3 (corner bias): current code
$PY scripts/repeatability.py "$A" "$B" | tee fixloop/iteration3_corner_bias/repeatability.txt
$PY scripts/diagnose_repeatability.py "$A" "$B" | tee fixloop/iteration3_corner_bias/diagnosis.txt
$PY scripts/overlay.py "$A" "$B" docs/figures/repeatability_overlay.png
# drift ablation, current code
$PY scripts/repeatability.py "${A}_nodrift" "${B}_nodrift" | tee results/repeatability_drift_off.txt
$PY scripts/drift_ablation.py "${B}_nodrift" "$B" docs/figures/drift_ablation.png
# FIRST-PASS numbers (superseded): same fixes, but with the unstable first-pass yaw search.
# Regenerated only for the record; they depend on the numpy version (that is the bug). See FIX_DECLARATION.md.
for c in single_scan_floor_only single_scan_with_ceiling; do
  for v in fp_before fp_wall fp_it3; do mkdir -p "out/${c}_$v"; cp "out/$c/chunks.pkl" "out/${c}_$v/"; done
  $PY -m roomscan "$RAW/$c.zip" --out "out/${c}_fp_before" --legacy-geometry --legacy-yaw > /dev/null
  $PY -m roomscan "$RAW/$c.zip" --out "out/${c}_fp_wall"   --legacy-geometry --legacy-yaw --room-dims wall > /dev/null
  $PY -m roomscan "$RAW/$c.zip" --out "out/${c}_fp_it3"    --legacy-yaw > /dev/null
done
$PY scripts/repeatability.py "${A}_fp_before" "${B}_fp_before" | tee fixloop/firstpass_unstable_yaw/before_repeatability.txt
$PY scripts/repeatability.py "${A}_fp_wall"   "${B}_fp_wall"   | tee fixloop/firstpass_unstable_yaw/declared_fix_repeatability.txt
$PY scripts/repeatability.py "${A}_fp_it3"    "${B}_fp_it3"    | tee fixloop/firstpass_unstable_yaw/iteration3_repeatability.txt
# calibration
$PY scripts/interval_coverage.py "$A" "$B" | tee results/interval_coverage.txt
echo "done: see results/, fixloop/, docs/figures/"
