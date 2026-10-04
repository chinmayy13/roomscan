"""
Repeatability: two captures of the same rooms at the same tier should give
the same plan. Gate: every matched wall within 1 cm or 0.5%.

    python scripts/repeatability.py out/scan_A out/scan_B

The two plans live in different frames (ARKit picks a new origin and heading
every session), so first we line them up: try the four 90-degree turns, run
2D ICP on the wall points, keep the best fit. Then rooms are matched by
overlap (IoU > 0.5) and their dimensions compared.
"""
import json
import sys

import cv2
import numpy as np
from scipy.spatial import cKDTree

sys.path.insert(0, ".")
from roomscan.drift import icp_2d


def load(run):
    plan = json.load(open(f"{run}/plan.json"))
    return plan, np.load(f"{run}/wall_xy.npy")


def align(src, dst):
    best = None
    tree = cKDTree(dst)
    for quarter in range(4):
        a = quarter * np.pi / 2
        R0 = np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])
        t0 = dst.mean(0) - src.mean(0) @ R0.T
        R, t, fit = icp_2d(src @ R0.T + t0, tree, dst, iterations=40)
        if best is None or fit > best[2]:
            best = (R @ R0, R @ t0 + t, fit)
    return best


def raster(poly, origin, shape, res=0.05):
    img = np.zeros(shape, np.uint8)
    cv2.fillPoly(img, [((np.array(poly) - origin) / res).astype(np.int32)], 1)
    return img


def dims(room, swap=False):
    """Room x/y dimensions as reported in plan.json; swap if the scans differ by 90 deg."""
    d = room["dimensions"]
    x, y = d["x"]["value_m"], d["y"]["value_m"]
    return (y, x) if swap else (x, y)


def main(run_a, run_b):
    plan_a, walls_a = load(run_a)
    plan_b, walls_b = load(run_b)
    R, t, fit = align(walls_b, walls_a)
    print(f"alignment: {fit:.0%} of B's wall points within 5 cm of A's")

    for r in plan_b["rooms"]:
        r["polygon_in_a"] = (np.array(r["polygon"]) @ R.T + t).tolist()
    allp = np.vstack([r["polygon"] for r in plan_a["rooms"]] + [r["polygon_in_a"] for r in plan_b["rooms"]])
    origin = allp.min(0) - 1
    shape = tuple((np.ptp(allp, 0) / 0.05 + 40).astype(int)[::-1])

    rows = []
    for ra in plan_a["rooms"]:
        ma = raster(ra["polygon"], origin, shape)
        best, best_iou = None, 0
        for rb in plan_b["rooms"]:
            mb = raster(rb["polygon_in_a"], origin, shape)
            iou = (ma & mb).sum() / max((ma | mb).sum(), 1)
            if iou > best_iou:
                best, best_iou = rb, iou
        if best is None or best_iou < 0.5:
            continue
        swap = abs(R[0, 0]) < 0.5          # B was turned 90 or 270 deg onto A
        da, db = dims(ra), dims(best, swap)
        for name, x, y in [("x-extent", da[0], db[0]), ("y-extent", da[1], db[1])]:
            diff = abs(x - y)
            ok = diff <= max(0.01, 0.005 * max(x, y))
            rows.append((ra["id"], best["id"], name, x, y, diff, ok, best_iou))

    print(f"\n{'A room':7}{'B room':7}{'dim':10}{'A (m)':>8}{'B (m)':>8}{'|diff| cm':>11}  gate  IoU")
    for a, b, n, x, y, d, ok, iou in rows:
        print(f"{a:7}{b:7}{n:10}{x:8.3f}{y:8.3f}{d * 100:11.1f}  {'PASS' if ok else 'FAIL'}  {iou:.2f}")
    if rows:
        diffs = np.array([r[5] for r in rows]) * 100
        print(f"\nmatched dims: {len(rows)}, pass {sum(r[6] for r in rows)}/{len(rows)}, "
              f"median |diff| {np.median(diffs):.1f} cm, max {diffs.max():.1f} cm")
    return rows


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
