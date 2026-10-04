"""
Synthetic ground truth: two rooms with known dimensions, a doorway, a ceiling, furniture and noise.

    python tests/test_synthetic.py

This is NOT a substitute for tape-measured ground truth: the geometry is perfectly rectilinear and
the noise is Gaussian, so it flatters the pipeline. It catches regressions and shows the
pipeline recovers known numbers when the world is clean.
"""
import os
import pickle
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from roomscan.pipeline import run

RNG = np.random.default_rng(7)
FLOOR_Y, H = -1.40, 2.60          # world y is up; floor sits 1.4 m below the "phone origin"
NOISE = 0.005


def plane(x0, x1, z0, z1, y0, y1, step=0.02):
    """Points on an axis-aligned box face; whichever dimension has zero extent is the normal."""
    xs = np.arange(x0, x1 + 1e-9, step) if x1 > x0 else np.array([x0])
    ys = np.arange(y0, y1 + 1e-9, step) if y1 > y0 else np.array([y0])
    zs = np.arange(z0, z1 + 1e-9, step) if z1 > z0 else np.array([z0])
    return np.array(np.meshgrid(xs, ys, zs)).reshape(3, -1).T


def build():
    A_w, A_d, B_w, B_d = 4.0, 3.0, 3.0, 3.0           # room A: x 0..4, room B: x 4..7, both z 0..3
    y_lo, y_hi = FLOOR_Y, FLOOR_Y + H
    P = [
        plane(0, A_w + B_w, 0, A_d, y_lo, y_lo),                    # floor
        plane(0, A_w + B_w, 0, A_d, y_hi, y_hi),                    # ceiling
        plane(0, 0, 0, A_d, y_lo, y_hi),                            # west wall
        plane(A_w + B_w, A_w + B_w, 0, A_d, y_lo, y_hi),            # east wall
        plane(0, A_w + B_w, 0, 0, y_lo, y_hi),                      # south wall
        plane(0, A_w + B_w, A_d, A_d, y_lo, y_hi),                  # north wall
    ]
    party = plane(A_w, A_w, 0, A_d, y_lo, y_hi)                     # wall between A and B
    door = (party[:, 2] > 1.0) & (party[:, 2] < 1.9) & (party[:, 1] < y_lo + 2.0)   # 0.9 m x 2.0 m door
    P.append(party[~door])
    P.append(plane(0.3, 1.5, 0.3, 1.0, y_lo, y_lo + 0.5))          # a low "sofa" in room A (must not become a wall)
    P.append(plane(5.0, 5.5, 2.4, 2.9, y_lo, y_lo + 0.9))          # a low "table" in room B
    pts = np.vstack(P) + RNG.normal(0, NOISE, (sum(len(p) for p in P), 3))
    # the walk: a loop through both rooms and the door, at 1.4 m above the floor
    path = [(0.6, 0.6), (3.4, 0.6), (3.4, 1.45), (4.6, 1.45), (6.4, 1.45), (6.4, 2.4), (4.6, 2.4), (3.4, 2.4), (0.6, 2.4), (0.6, 0.6)]
    cams = np.vstack([np.linspace(path[i], path[i + 1], 40) for i in range(len(path) - 1)])
    cams3 = np.column_stack([cams[:, 0], np.zeros(len(cams)), cams[:, 1]])
    # split into time chunks like the real pipeline (3 submaps); no drift in the synthetic world
    idx = np.array_split(RNG.permutation(len(pts)), 3)
    cam_idx = np.array_split(np.arange(len(cams3)), 3)
    return [{"points": pts[i].astype(np.float32), "cams": cams3[c], "t0": k, "t1": k + 1}
            for k, (i, c) in enumerate(zip(idx, cam_idx))]


def main():
    with tempfile.TemporaryDirectory() as out:
        with open(os.path.join(out, "chunks.pkl"), "wb") as f:
            pickle.dump(build(), f)
        plan = run("synthetic.zip", out)
    rooms = sorted(plan["rooms"], key=lambda r: -r["floor_area_m2"])
    print(f"rooms found: {len(rooms)}  openings: {[(o['between'], o['width_m']) for o in plan['openings']]}")
    truth = [("A", 4.0, 3.0), ("B", 3.0, 3.0)]
    ok = len(rooms) == 2
    for r, (name, w, d) in zip(rooms, truth):
        dx, dy = r["dimensions"]["x"]["value_m"], r["dimensions"]["y"]["value_m"]
        got = sorted([dx, dy]); want = sorted([w, d])
        err = [abs(g - t) * 100 for g, t in zip(got, want)]
        ceil = r["ceiling"].get("height_m")
        print(f"room {name}: dims {dx:.3f} x {dy:.3f} (truth {w} x {d}), errors {err[0]:.1f}/{err[1]:.1f} cm, ceiling {ceil}")
        ok &= max(err) <= 5.0 and ceil is not None and abs(ceil - H) <= 0.03
    ok &= len(plan["openings"]) == 1 and abs(plan["openings"][0]["width_m"] - 0.9) <= 0.15
    try:
        import json, jsonschema
        schema = json.load(open(os.path.join(os.path.dirname(__file__), "..", "plan.schema.json")))
        jsonschema.validate(plan, schema)
        print("plan.json validates against plan.schema.json")
    except ImportError:
        print("(jsonschema not installed; schema check skipped: pip install jsonschema)")
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
