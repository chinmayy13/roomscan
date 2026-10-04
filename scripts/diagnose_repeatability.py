"""
Fix-loop evidence: is the repeatability failure in WALL MEASUREMENT or in
ROOM SEGMENTATION?

Test: after aligning scan B onto scan A, take every wall face that was
actually measured (snapped to a point peak) in A, and find the same face in B
(same orientation, within 15 cm, spans overlap). If those faces agree to
~1 cm, the measurement is repeatable and the error must come from rooms
being outlined differently (different walls/doorways chosen as the boundary).

    python scripts/diagnose_repeatability.py out/scan_A out/scan_B
"""
import sys

import numpy as np

sys.path.insert(0, ".")
sys.path.insert(0, "scripts")
from repeatability import align, load


def faces(plan, R=np.eye(2), t=np.zeros(2)):
    out = []
    for room in plan["rooms"]:
        for w in room["walls"]:
            if not w["face_measured"]:
                continue
            p, q = np.array(w["start"]) @ R.T + t, np.array(w["end"]) @ R.T + t
            axis = 0 if abs(q[0] - p[0]) < abs(q[1] - p[1]) else 1      # 0: x=const
            out.append((axis, (p[axis] + q[axis]) / 2, sorted([p[1 - axis], q[1 - axis]])))
    return out


def face_gaps(run_a, run_b):
    """Gap (m) between each measured face of A and its match in B, after aligning B onto A."""
    plan_a, wa = load(run_a)
    plan_b, wb = load(run_b)
    R, t, fit = align(wb, wa)
    fa, fb = faces(plan_a), faces(plan_b, R, t)
    gaps = []
    for axis, pos, (s0, s1) in fa:
        cands = [abs(pos - p) for ax, p, (u0, u1) in fb
                 if ax == axis and abs(pos - p) < 0.15 and min(s1, u1) - max(s0, u0) > 0.3]
        if cands:
            gaps.append(min(cands))
    return np.array(gaps), len(fa)


if __name__ == "__main__":
    g, n = face_gaps(sys.argv[1], sys.argv[2])
    g = g * 100
    print(f"measured faces in A: {n}, found again in B: {len(g)}")
    print(f"face position difference: median {np.median(g):.1f} cm, "
          f"p75 {np.percentile(g, 75):.1f} cm, within 1 cm: {np.mean(g <= 1):.0%}, within 2 cm: {np.mean(g <= 2):.0%}")
