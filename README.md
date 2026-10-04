# roomscan — LiDAR capture to dimensioned floor plan

Applied AI Engineer case study, Round 2. **Status: LiDAR tier only.** Photo and video tiers are
not implemented (see `COMPLIANCE_MATRIX.md` for exactly what is and is not done).

**Raw data:** the three Stray Scanner capture zips (`single_room`, `single_scan_floor_only`,
`single_scan_with_ceiling`) are attached to the [v1 release](https://github.com/chinmayy13/roomscan/releases/tag/v1).
Download them into one folder, then run `bash reproduce.sh <that folder>` to regenerate every
number in this repo.

## Run it

```bash
python -m venv .venv && source .venv/bin/activate      # Python 3.11+
pip install -r requirements.txt                         # numpy, scipy, opencv: no GPU, no weights
python -m roomscan path/to/capture.zip --out out/my_flat   # one command per capture
```

Input is the zip of a Stray Scanner capture folder (see `docs/CAPTURE_PROTOCOL.md`). The command
writes `out/my_flat/plan.json` (rooms, walls, ceiling, area, openings, adjacency, 95% intervals)
and `out/my_flat/plan.png` (rendered plan, viewed from above). A 4-minute whole-flat capture takes
about 2 minutes on a laptop CPU; reruns reuse the fused depth cache and take ~10 s.

Options: `--no-drift` (ablation: ARKit poses as-is), `--room-dims wall` (declared fix-loop attempt, failed),
`--legacy-geometry` (the code before follow-up 3, to regenerate its "before" run), `--legacy-yaw` (the unstable first-pass yaw search; first-pass numbers only).

Tests: `python tests/test_synthetic.py` builds a flat with known dimensions and checks the pipeline
recovers them and that the output validates against `plan.schema.json`. `python tests/test_determinism.py` checks the plan's rotation
does not move when a few points are dropped. Verified to give identical rooms on numpy 1.26 and numpy 2.4.

## Reproduce every reported number

```bash
bash reproduce.sh /path/to/raw_zips
```

## Layout

| Path                   | What it is                                                                                                                                     |
| ---------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| `roomscan/capture.py`  | Reads a Stray Scanner folder or zip; back-projects depth to world points                                                                       |
| `roomscan/cloud.py`    | Fuses frames into ~15 s time chunks (submaps), 2 cm voxels                                                                                     |
| `roomscan/drift.py`    | Plane-anchored floor alignment + submap-to-map 2D ICP; drift metric                                                                            |
| `roomscan/plan.py`     | Floor, Manhattan yaw, wall detection, room segmentation, outlines, ceiling, openings                                                           |
| `roomscan/pipeline.py` | Orchestration, JSON output contract, render                                                                                                    |
| `scripts/`             | Repeatability, fix-loop diagnosis, interval calibration, overlay and drift-ablation figures; `experiments/` holds the failed fix-loop attempts |
| `plan.schema.json`     | JSON Schema for `plan.json`                                                                                                                    |
| `tests/`               | synthetic known-geometry test                                                                                                                  |
| `fixloop/`             | Before/after runs and the fix declaration                                                                                                      |
| `docs/`                | Capture protocol, technical report, figures                                                                                                    |
