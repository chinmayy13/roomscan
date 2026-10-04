"""
Determinism: the plan must not change because a few points more or fewer survive float rounding.

    python tests/test_determinism.py

History: the first-pass yaw search used a random subsample, so one extra point (another numpy
version, 0.24 micrometre of float noise) flipped a near-tie between 27.50 and 27.75 degrees and moved one
room by 36 cm. This test rotates the synthetic flat to an awkward angle (between two search
steps) and checks the yaw is recovered and does not move when points are removed.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from roomscan import plan
import test_synthetic as T


def main():
    pts = np.vstack([c["points"] for c in T.build()])
    truth = 27.6                                           # between the 27.50 and 27.75 grid steps
    a = np.deg2rad(truth)
    xz = pts[:, [0, 2]] @ np.array([[np.cos(a), np.sin(a)], [-np.sin(a), np.cos(a)]])
    band = (pts[:, 1] - T.FLOOR_Y > plan.WALL_LO) & (pts[:, 1] - T.FLOOR_Y < plan.WALL_HI)
    xz = xz[band]
    full = np.degrees(plan.manhattan_yaw(xz))
    rng = np.random.default_rng(3)
    results = [full]
    for n_drop in (1, 7, 50):
        keep = np.ones(len(xz), bool)
        keep[rng.choice(len(xz), n_drop, replace=False)] = False
        results.append(np.degrees(plan.manhattan_yaw(xz[keep])))
    print("yaw (deg) full / minus 1 / minus 7 / minus 50 points:", [round(float(r), 2) for r in results])
    spread = max(results) - min(results)
    err = min(abs(full - (90 - truth)), abs(full - truth))        # 90-degree symmetry
    print(f"spread {spread:.3f} deg, error vs truth {err:.3f} deg")
    ok = spread <= 0.05 and err <= 0.25   # 2 cm bins on a 7 m wall resolve ~0.16 deg
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
