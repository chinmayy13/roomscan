# Technical report — roomscan (LiDAR tier)

## 1. Scope, stated plainly
This submission delivers the **LiDAR tier only**: one command turns a Stray Scanner capture into a
dimensioned multi-room plan (JSON + rendered PNG) with drift correction and a drift ablation.
**Not delivered:** photo and video tiers, damage detection, concealed-damage rules, scope line
items, window detection, ground truth, consumer-app head-to-head. Every gate needing ground truth is
unscored. I chose to make one tier work end to end, measure it honestly, and run a real fix loop.
The alternative was thin stubs across all tiers that would produce confident garbage.

## 2. Tier design and device matrix

| Tier | Hardware | Input | Status | Honest accuracy |
|---|---|---|---|---|
| LiDAR | iPhone 12 Pro+ / iPad Pro 2020+ (Pro-class) | Stray Scanner: depth 256×192, confidence, ARKit poses, intrinsics | implemented | wall faces repeat to ~4 cm (median) between captures; room dims do **not** repeat to the gate (median 33 cm, 1 of 10 within gate); absolute accuracy vs tape unmeasured |
| Video | any iPhone 15+ | handheld clip | not implemented | — |
| Photo | any iPhone 15+ | 2–8 stills per room folder | not implemented | — |

Planned design for the missing tiers, so it can be discussed at the defense: one shared geometric
core (gravity-aligned points in, plan out), with tier-specific front ends.
- **Video:** feed-forward reconstruction (e.g. VGGT or MASt3R-SfM) for poses, and a metric monocular
  depth model for scale.
- **Photo:** the same per room. Rooms are stitched by matching each doorway as photographed from both
  sides, then solving the layout under shared-wall and no-overlap constraints. The photo protocol would
  require one photo of every doorway from inside each room, to make this solvable.
- **Intervals:** widened per tier from measured residuals.

## 3. Architecture (LiDAR)

```
zip ─► capture.py ─► cloud.py ─────► drift.py ─────► plan.py ──────────────────► pipeline.py
      read frames   15 s submaps,   floor anchor +   floor, Manhattan yaw,       JSON + PNG
      back-project  2 cm voxels     2D ICP/submap    walls, rooms, outlines,
                                                     ceiling, openings
```

1. **Back-projection.** Only high-confidence depth (ARKit confidence 2) within 3.5 m is used. Pose
   convention was verified on the data, not assumed. With no axis flip, the floor appears as a sharp
   plane 1.40–1.47 m below the phone (hand height). With the usual ARKit flip, no floor exists.
2. **Floor.** Strongest 1 cm height bin in the lower half of the cloud, refined by the median of points
   within ±3 cm.
3. **Manhattan yaw.** Coarse search over 0–90° in 0.25° steps on **all** wall points, then a 0.02° refinement around the
   winner; pick the yaw where the 1D histograms of wall points are spikiest, i.e. walls stack into thin lines. Assumes right-angled
   rooms. Deterministic by design: the first version used a random subsample and was unstable (§6).
4. **Walls.** A 2 cm plan cell is "wall" if points fill at least 50% of its 10 cm height slabs between
   0.3 and 1.8 m. Beds and tables are short and fail this test. Doorways are empty below the lintel, so
   they show up as gaps automatically.
5. **Rooms.**
   - Interior = cells with anything below 1.8 m, closed, holes filled, plus the walked path.
   - Free space = interior minus walls.
   - Eroding free space by 0.5 m pinches doorways shut and leaves one seed per room.
   - Seeds are grown back through free space only (geodesic growth), so a label cannot cross a wall.
     Rooms therefore cannot overlap.
6. **Outlines.** Thin protrusions are removed with a **square**-kernel opening (a disk rounds corners:
   see §6). Then contour → Douglas-Peucker (15 cm) → each edge forced horizontal or vertical. Each edge
   is **snapped to the wall face**: the densest 5 mm bin of points within ±8 cm, using only points above
   1.1 m so tables and sofas cannot pass as walls. The window is smaller than any wall thickness, so a
   snap cannot jump to the next room's face.
7. **Ceiling.** The highest well-supported slab above 2.1 m that covers ≥ 25% of the room's floor
   area. The coverage test exists because a scan that never looked up still sees loft and wardrobe
   tops; without it the floor-only scan reported "ceilings" of 1.93–2.25 m. It now returns null with a
   reason.
8. **Openings.** Where two room labels touch, the touching span is a doorway; its length is the width.

## 4. Drift handling
ARKit drifts slowly, and revisited rooms show doubled walls. Each 15 s submap is corrected in walking
order, in two steps.
- **Vertical, plane-anchored:** the submap's floor is shifted onto the global floor (corrections up to 9 mm).
- **Horizontal:** 2D point-to-point ICP of its 0.3–1.8 m wall points against all submaps already placed.
  The match radius shrinks from 20 cm to 5 cm over the iterations.

A correction is accepted only if ≥ 30% of points overlap and the move is under 3° and 30 cm. Larger
moves indicate a wrong match, not drift, so they are rejected. On the 3.6-minute flat scan, 11 of 15
submaps were corrected.

**Ablation** (`docs/figures/drift_ablation.png`, ceiling scan):
- p90 wall gap between submaps: 5.91 → 5.01 cm; the median gap does not move (1.28 → 1.29 cm).
- Footprint: 64.06 → 65.23 m². Repeatability against the other capture, median room-dimension
  difference: 46.8 → 33.5 cm (partly because doubled walls otherwise merge rooms).
- On the floor-only scan the effect is negligible (p90 8.61 → 8.53 cm). Correction helps where the walk
  revisits rooms.

Limitation: sequential alignment has no global loop closure, so error can still accumulate along a
long chain. Point-to-point ICP can also slide along corridors. A pose graph over all submap pairs,
with point-to-line residuals, is the next step.

## 5. Error budget and intervals
Per wall: σ² = σ_end1² + σ_end2² + (1%·L)². An end set by a wall face snapped to real points has
σ = 4 cm; an end with no wall behind it (the scan stopped) has σ = 23 cm. Dimensions taken from the
outline extent use σ = 23 cm. Ceiling: σ² = (4 mm)² + (1%·H)². Area propagates edge by edge
(an edge of length L moved by σ changes area by L·σ). Intervals are 95% (±1.96σ).

**Calibration analysis.** The 4 cm and 23 cm values were fitted on the one repeat pair: σ is chosen so
that a 95% interval on the *gap* between two scans covers 95% of matched pairs (σ = p95(gap)/(1.96√2)); on the corrected pipeline the outline formula gives 21 cm and the shipped 23 cm is the wider value.
The original 5 mm prior covered **10%** of the 31 matched face pairs; the shipped value covers **94%**
(`scripts/interval_coverage.py`). **This is in-sample**: it proves the old prior was wrong, not that the
new value holds on an unseen flat. Ceiling, scale and opening-width intervals are unvalidated priors,
and **nothing is calibrated against tape**, because no tape ground truth was collected.

## 6. Fix loop (full text and regenerable runs: `fixloop/FIX_DECLARATION.md`)
**A determinism bug changed my numbers mid-way.** Running on a second machine (numpy 1.26 vs 2.4) moved one room by 36 cm. Cause: the yaw search
used a random subsample on a 0.25° grid; 0.24 µm of float noise changed the subsample, flipped a near-tie (27.50° vs 27.75°) and rotated the
planning grid. Fixed (all points, 0.02° refinement), verified identical on both numpy versions for all three captures, and guarded by a test.
Part of my first-pass results was tie-break luck, so I re-ran everything. Corrected results (repeatability, 10 matched dimensions, gate 1 cm or 0.5%):

| Step | median \|diff\| | pass |
|---|---|---|
| Before (old geometry) | 40.0 cm | 0/10 |
| Declared fix: wall-to-wall dimensions | 37.9 cm | 0/10 |
| Follow-up 2: median-run "typical" dimensions | 36.0 cm | 0/10 |
| Follow-up 3: square kernels, snap evidence above 1.1 m | **33.5 cm** | **1/10** |

- **Declared fix** (first pass: predicted ≤ 4 cm, got 40.4 cm "worse"): on the corrected baseline it is almost neutral (40.0 → 37.9).
  It does not fix the problem because "opposite walls" is undefined when outlines differ.
- **Follow-up 3** (found by a synthetic known-geometry test): a disk-shaped opening rounded room corners and put edges ~10 cm inside the
  walls; a table edge passed as a wall. The synthetic error fell from 20 cm to 0. On real data the gain is a modest 40.0 → 33.5 cm.
- **Why the gate still fails:** wall faces repeat to a median 4.1 cm between scans (a floor under the 1 cm gate), only 3 of 10 dimensions have a
  wall at both ends in both scans (the rest end where the scan stopped, median gap 50.7 cm), and some rooms are segmented differently.
  Side effect: footprints of the two scans differ by 9.4% (were 5.4%).
- **Prediction accounting:** the first two predictions were wrong; follow-up 3's "hit" (16.1 cm) was first-pass luck, since the same fix gives 33.5 cm
  on the corrected pipeline. Predictions were written in notes before each run, not committed, so they cannot be timestamped.

## 7. Known failure modes
- **Wide openings merge rooms.** An opening wider than ~1 m (living room to corridor) is not pinched
  shut, so two spaces become one room (R4 in the ceiling scan, 29.4 m²).
- **Furniture in outlines.** Wardrobes taller than 1.1 m still pass the wall and snapping tests and can notch an outline.
- **Open sides.** Balconies and unscanned walls give outlines bounded by where the scan stopped, not by
  a wall.
- **Opening widths read narrow.** On the synthetic flat a 0.90 m door reads 0.86 m (the label-contact
  span loses cells next to the jambs), so the 2 cm opening gate would be missed even on clean data.
- **Two captures disagree on footprint by 9.4%** (59.40 vs 65.23 m²), partly from unscanned parts of rooms.
- **Numerical sensitivity.** Discontinuous steps (grid binning, argmax over near-tied scores) can turn tiny float noise into large changes. The yaw search was one case and is fixed; other thresholds (e.g. the 0.5 m erosion that separates rooms) were not stress-tested.
- **Windows** are not detected.
- **Mirrors and glass.** LiDAR returns through or into them create phantom space; confidence filtering
  helps only partly. The protocol tells the user to pass them at an angle. Untested.
- **Low light.** ARKit tracking degrades and drift grows. The protocol requires all lights on. Untested.
- **Wet-look surfaces.** These can drop depth returns. Untested.
- **Non-Manhattan rooms** (angled walls) get forced to 90°.
