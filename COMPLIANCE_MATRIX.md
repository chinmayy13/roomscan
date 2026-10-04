# Compliance matrix

Status key: ✅ done · ⚠️ partial · ❌ not done

| Requirement | File path | Artifact | Status |
|---|---|---|---|
| Capture route (stock app + one-page protocol) | `docs/CAPTURE_PROTOCOL.md` | Stray Scanner protocol | ✅ |
| Device matrix | `docs/TECHNICAL_REPORT.md` §2 | table | ⚠️ LiDAR row only measured |
| Photo tier (2–8 stills/room → stitched plan) | — | — | ❌ |
| Video tier (handheld clip) | — | — | ❌ |
| LiDAR tier | `roomscan/` | `python -m roomscan` | ✅ |
| One command per capture | `roomscan/__main__.py` | CLI | ✅ |
| Per-room walls with lengths | `roomscan/pipeline.py: measure_room` | `plan.json → rooms[].walls` | ✅ |
| Ceiling height per room | `roomscan/plan.py: ceiling_height` | `rooms[].ceiling` | ✅ (null + reason when not seen) |
| Floor area | `roomscan/plan.py: polygon_area` | `rooms[].floor_area_m2` | ✅ |
| Openings | `roomscan/plan.py: find_openings` | `openings[]` | ⚠️ doorways only, no windows |
| Stitched multi-room plan, adjacency | `roomscan/pipeline.py` | `plan.png`, `adjacency` | ⚠️ one scan = one stitched plan; wide openings merge rooms |
| No room overlaps | `roomscan/plan.py: segment_rooms` | label image | ✅ by construction |
| Confidence interval on every measurement | `roomscan/plan.py: interval` | `interval_95_*` | ⚠️ face/outline σ fitted in-sample on one repeat pair (coverage 10% → 94%); ceiling/scale/opening are priors; no tape calibration |
| Damage regions (class + metric extent) | — | `damage_regions: []` | ❌ |
| Concealed-damage flags with rule | — | `concealed_damage_flags: []` | ❌ |
| Scope line items keyed to surfaces | — | `scope_line_items: []` | ❌ |
| JSON to published schema | `plan.schema.json`, `scripts/validate_schema.py` | `results/plans/*.json` validate | ✅ (my own schema; none was published with the brief) |
| Rendered plan | `roomscan/pipeline.py: render` | `plan.png` | ✅ |
| Benchmark: multi-room capture | raw zips | 2 captures | ✅ |
| Benchmark: damage room | — | — | ❌ |
| Benchmark: same rooms at 3 tiers | — | — | ❌ |
| Benchmark: repeat capture | raw zips | floor-only vs with-ceiling | ✅ |
| Ground truth | — | — | ❌ |
| Repeatability table | `fixloop/iteration3_corner_bias/repeatability.txt` | table | ✅ (fails gate: 1/10, median 33.5 cm) |
| Drift handling + ablation | `roomscan/drift.py`, `docs/figures/drift_ablation.png` | on/off runs | ✅ |
| Head-to-head vs consumer app | — | — | ❌ |
| Fix loop: declaration, before, after, diff | `fixloop/`, `--room-dims`, `--legacy-geometry` flags | regenerable by `reproduce.sh` | ✅ declared fix ineffective (documented); follow-up 3 moved the gate 40.0 → 33.5 cm on the corrected pipeline, short of pass; first-pass numbers superseded after a determinism bug |
| Tests | `tests/test_synthetic.py`, `tests/test_determinism.py` | known-geometry flat, schema check, yaw stability | ✅ pass (clean data only) |
| Reproduction bundle | `reproduce.sh` | all numbers | ✅ |
| Technical report ≤ 6 pages | `docs/TECHNICAL_REPORT.md` | | ✅ |
| Mirrors / glass / low light covered | `docs/TECHNICAL_REPORT.md` §7 | | ⚠️ described, not tested |
