# Benchmark report

**Read this first:** no tape or laser ground truth was collected, so **no accuracy gate can be
scored**. Everything below is either a self-consistency measurement (two captures of the same
flat) or a raw output. All numbers regenerate with `bash reproduce.sh <raw_zips>`.

## Benchmark set (what exists)

| Required by brief | Have | Notes |
|---|---|---|
| Multi-room capture, 3+ rooms + connector | ✅ | `single_scan_floor_only`, `single_scan_with_ceiling`: whole flat, ~6 rooms + corridor |
| Furnished room with staged damage, 2 classes | ❌ | not captured |
| Same rooms at photo / video / LiDAR | ⚠️ LiDAR only | `rgb.mp4` exists inside each capture, but no photo or video pipeline |
| One room captured twice at the same tier | ✅ (whole flat twice) | the floor-only and with-ceiling scans |
| Laser or tape ground truth | ❌ | none |
| Consumer-app export (head-to-head) | ❌ | none |

## Gates (LiDAR tier)

| Gate | Result | Status |
|---|---|---|
| Opening widths ≤ 2 cm on ≥ 85% | no ground truth. On the synthetic flat a 0.90 m door reads 0.86 m (4 cm low), so the 2 cm gate would be missed even on clean data | not scorable; likely **FAIL** |
| Ceiling height ≤ 1.5 cm; spread ≤ 1 cm | real flat: 6 rooms measured, 2.28–3.08 m; floor-only scans correctly report "not captured". Only one capture saw the ceiling, so no spread. Synthetic: 2.60 m recovered exactly | not scorable on real data |
| Repeatability ≤ 1 cm / 0.5% per wall | **1/10 dims pass; median 33.5 cm, max 61.3 cm** (before the corner-bias fix: 40.0 cm, 0/10). Same wall faces agree to a median 4.1 cm (31 faces) | **FAIL** |
| Drift accountability | submap ICP + floor anchoring; ablation below and `docs/figures/drift_ablation.png` | implemented |
| Photo-tier whole-property stitch | not implemented | **FAIL** |

### Drift ablation (`single_scan_with_ceiling`, 3.6 min walk, 15 submaps)

| | poses as-is | drift corrected |
|---|---|---|
| Wall gap between submaps, p90 | 5.91 cm | 5.01 cm |
| Wall gap between submaps, median | 1.28 cm | 1.29 cm |
| Submaps corrected | 0 | 11 of 15 (4 rejected by safety limits) |
| Stitched footprint | 64.06 m² | 65.23 m² |
| Repeatability vs the other capture, median dim diff | 46.8 cm | 33.5 cm |

Read this with care. The median gap does not move, only the tail. The repeatability change is partly because uncorrected doubled
walls merge rooms during segmentation. On the other whole-flat scan (`single_scan_floor_only`, 4 of 8 submaps corrected) the effect is
negligible (p90 8.61 → 8.53 cm, footprint 58.81 → 59.40 m²). Drift correction helps where the walk revisits rooms and does little otherwise.

### Synthetic flat (ground truth known, `tests/test_synthetic.py`)
Two rooms 4.0×3.0 and 3.0×3.0 m, ceiling 2.60 m, a 0.90 m doorway, furniture, 5 mm noise. Recovered: dimensions within 0.0 cm,
ceiling 2.60 m, one doorway of 0.86 m. This is clean, perfectly rectilinear data with no drift; it shows the code is right on easy
input, not that real accuracy is good.

### Determinism and environment (`tests/test_determinism.py`)
Output used to depend on the numpy version: a random subsample in the yaw search let 0.24 µm of float noise flip a near-tie and move
one room by 36 cm. Fixed (all points plus 0.02° refinement). Verified identical rooms on all three captures under numpy 1.26.4 /
scipy 1.12 / OpenCV 4.8 and numpy 2.4.4 / scipy 1.17 / OpenCV 4.13, including a run from the raw zip with no cache.
The first-pass numbers (24.8 / 40.4 / 16.1 cm) are superseded; see `fixloop/FIX_DECLARATION.md`.

### Calibration of intervals (`scripts/interval_coverage.py`)
| per-face σ | share of the 31 matched face pairs covered by the 95% gap interval |
|---|---|
| 0.5 cm (original prior) | 10% |
| 4.0 cm (shipped) | 94% (in-sample) |
Ceiling (4 mm + 1%), scale (1%) and opening width (15 cm) intervals are priors, unvalidated.

### Footprint agreement between the two whole-flat captures
59.40 m² (floor-only) vs 65.23 m² (with ceiling): 9.4% apart. With the old geometry they were 60.25 vs 63.62 m² (5.4%). There is no ground
truth to say which is nearer. The floor-only scan covers less of some rooms, which accounts for part of the difference.

## Timing (laptop CPU, no GPU)

| Capture | Frames | Depth fusion (first run) | Plan (cached rerun) |
|---|---|---|---|
| single_room | 1,715 | ~29 s | ~2 s |
| single_scan_floor_only | 5,251 | ~74 s | ~6 s |
| single_scan_with_ceiling | 9,745 | ~126 s | ~10 s |

## Head-to-head vs consumer app
Not done: no consumer-app export was captured. **0% of shared dimensions compared.**
