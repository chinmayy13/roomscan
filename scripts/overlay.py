"""Overlay scan B's room outlines (blue) on scan A's (red), after alignment, on A's wall points."""
import json, sys
import cv2, numpy as np
sys.path.insert(0, "."); sys.path.insert(0, "scripts")
from repeatability import align, load

a, wa = load(sys.argv[1]); b, wb = load(sys.argv[2])
R, t, _ = align(wb, wa)
ppm = 50; o = wa.min(0) - 0.5
size = (np.ptp(wa, 0) + 1) * ppm
img = np.full((int(size[1]), int(size[0]), 3), 255, np.uint8)
for x, y in ((wa - o) * ppm).astype(int):
    img[min(y, img.shape[0] - 1), min(x, img.shape[1] - 1)] = (150, 150, 150)
px = lambda P: ((np.array(P) - o) * ppm).astype(np.int32)
for r in a["rooms"]:
    cv2.polylines(img, [px(r["polygon"])], True, (0, 0, 220), 2)
    cv2.putText(img, "A" + r["id"], tuple(px(r["polygon"]).mean(0).astype(int) - [20, 8]), 0, 0.45, (0, 0, 200), 1)
for r in b["rooms"]:
    P = np.array(r["polygon"]) @ R.T + t
    cv2.polylines(img, [px(P)], True, (220, 0, 0), 2)
    cv2.putText(img, "B" + r["id"], tuple(px(P).mean(0).astype(int) + [0, 14]), 0, 0.45, (200, 0, 0), 1)
cv2.imwrite(sys.argv[3], img)
