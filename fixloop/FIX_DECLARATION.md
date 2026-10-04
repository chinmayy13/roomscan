# Fix loop

Everything here regenerates with `bash reproduce.sh <raw_zips>`.

## Read this first: the numbers changed during the work, and why

I first reported repeatability numbers (24.8 cm before, 16.1 cm after) from one machine. When I ran the same
pipeline on my own laptop (numpy 1.26 instead of 2.4) it gave different room dimensions: one room moved by
36 cm. I traced it:

- After drift correction, the two environments' point clouds differ by at most **0.24 micrometres** (float32
  rounding), and one more point survives voxel binning.
- `manhattan_yaw` picked the plan's rotation from a **random 200,000-point subsample** on a 0.25° grid. The true
  direction of that flat sits between two grid steps (scores at 27.50° and 27.75° are within 0.1%). One extra
  point changed the subsample, flipped the tie, rotated the whole planning grid, and moved R2 by 36 cm.
- Fix: search all points, then refine to 0.02° (`plan.manhattan_yaw`). With it, numpy 1.26 and numpy 2.4 give
  **identical rooms on all three captures**, including a run from raw zip with no cache.
  `tests/test_determinism.py` guards it.

**Consequence:** part of what I first reported was tie-break luck. I re-ran every step on the corrected pipeline.
The first-pass numbers are kept below for the record and still regenerate with `--legacy-yaw`, but only on numpy 2.x:
that dependence is the bug.

## Authoritative results (corrected pipeline)
Gate: repeatability, two LiDAR captures of the same flat agree within 1 cm or 0.5% per dimension
(`single_scan_floor_only` vs `single_scan_with_ceiling`, 10 matched dimensions).

| Step | median \|diff\| | max | pass | files |
|---|---|---|---|---|
| Before: old geometry (`--legacy-geometry`) | **40.0 cm** | 82.0 | 0/10 | `before/` |
| Declared fix: wall-to-wall dims (`--room-dims wall`) | 37.9 cm | 79.0 | 0/10 | `after/` |
| Follow-up 2: median-run "typical" dims | 36.0 cm | 80.0 | 0/10 | `iteration2_typical_dims/` |
| **Follow-up 3: square kernels, snap evidence above 1.1 m (current default)** | **33.5 cm** | 61.3 | **1/10** | `iteration3_corner_bias/` |
| Current code with drift correction off | 46.8 cm (12 dims) | 255.4 | 0/12 | `results/repeatability_drift_off.txt` |

## What the evidence supports
- **The gate is still failed.** 1 of 10 dimensions passes (R2 x-extent, 0.4 cm); the median is 33.5 cm.
- **Follow-up 3 is a real improvement, a modest one: 40.0 → 33.5 cm (16%)**, not the 35% first reported. Its
  root cause is real and independently verified: a disk-shaped morphological opening rounds room corners and puts
  outline edges ~10 cm inside the walls. A synthetic flat with known dimensions came out exactly 20 cm short in one
  axis before the fix and 0.0 cm after (`tests/test_synthetic.py`). A table edge was also being accepted as a "measured
  wall face"; snapping evidence now starts at 1.1 m.
- **The declared fix did almost nothing, not harm.** On the corrected baseline it moves 40.0 → 37.9 cm. In the first
  pass it looked like a large regression (24.8 → 40.4); that was partly the unstable yaw. Wall-to-wall is still not
  well defined when outlines differ (a wardrobe front can win in one scan and the wall in the other).
- **Why it stops short of the gate:**
  1. Wall faces agree between the two scans to a median **4.1 cm** (31 faces); with per-room alignment 3.3 cm
     (`iteration2_typical_dims/face_local.txt`). The 1 cm gate is below the measurement floor on this data.
  2. Only **3 of 10** matched dimensions have a wall-snapped face at both ends in both scans (median gap 14.7 cm);
     the other 7 end where the scan stopped (median 50.7 cm). Most of the error is coverage and segmentation, not wall position.
  3. Side effect: the footprints of the two scans now differ by 9.4% (59.40 vs 65.23 m²), up from 5.4% (60.25 vs 63.62) with the old geometry.
     No ground truth says which is nearer.

## The first pass, as it happened (superseded; unstable yaw)
Regenerate with `--legacy-yaw` on numpy 2.x: `firstpass_unstable_yaw/`.

**Declaration (written before any fix).** Worst gate: repeatability, **0/10, median 24.8 cm, max 66.3 cm**. Hypothesis: the
outline is unstable, not the wall measurement (same faces agreed to ~4 cm). Fix: wall-to-wall dimensions. Prediction: ≤ 4 cm.
**Result: 40.4 cm, badly wrong.** Follow-up 2 (typical dims): predicted 12–15 cm, got 32.0 cm. Follow-up 3: predicted
15–20 cm, got 16.1 cm.

**Honest accounting of those predictions.** The first two were wrong. The third matched the first-pass number, but on the corrected
pipeline the same fix gives 33.5 cm, so that hit was partly luck and I would not claim it. The predictions for follow-ups 2 and 3
were written in my notes before each run, not committed, so I cannot timestamp them.

## Calibration change shipped alongside: intervals were overconfident
`scripts/interval_coverage.py`: the 5 mm face prior covered **10%** of the 31 matched face pairs (a 95% interval should cover 95%).
Face σ is now 4 cm, covering **94%**. Outline-extent σ is 23 cm (the same formula on the corrected data gives 21 cm; 23 kept, the
wider value). **In-sample:** the same pair chose the values and tested them. It shows the old prior was wrong; it does not
prove the new values on an unseen flat.

## What I would do next
Segment rooms on a map shared across captures when more than one exists; regularise each room to its dominant rectangle scored on
full-height wall evidence; and collect tape ground truth so error is measured against reality and not against a second scan that
shares the same drift.
