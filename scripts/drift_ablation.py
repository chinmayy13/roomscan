"""Drift ablation figure: stitched footprint with drift correction OFF (left) and ON (right).

    python scripts/drift_ablation.py out/scan_nodrift out/scan figure.png
"""
import json, sys
import cv2, numpy as np

def panel(run, ppm=50):
    w = np.load(f"{run}/wall_xy.npy"); p = json.load(open(f"{run}/plan.json"))
    o = w.min(0) - 0.5; size = ((np.ptp(w, 0) + 1) * ppm).astype(int)
    img = np.full((size[1], size[0], 3), 255, np.uint8)
    for x, y in ((w - o) * ppm).astype(int):
        img[min(y, size[1] - 1), min(x, size[0] - 1)] = (60, 60, 60)
    for r in p["rooms"]:
        cv2.polylines(img, [((np.array(r["polygon"]) - o) * ppm).astype(np.int32)], True, (40, 90, 200), 2)
    g = p["drift_correction"]
    label = "drift correction ON" if g["enabled"] else "drift correction OFF (poses as-is)"
    cv2.putText(img, f"{label}  footprint {p['footprint_m2']} m2", (10, 25), 0, 0.6, (0, 0, 0), 2)
    return img

a, b = panel(sys.argv[1]), panel(sys.argv[2])
h = max(a.shape[0], b.shape[0])
pad = lambda im: cv2.copyMakeBorder(im, 0, h - im.shape[0], 0, 10, cv2.BORDER_CONSTANT, value=(255, 255, 255))
cv2.imwrite(sys.argv[3], np.hstack([pad(a), pad(b)]))
