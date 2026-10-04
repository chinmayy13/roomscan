# Fix-loop experiment, kept for reproducibility. Run from the repo root: python scripts/experiments/NAME.py out/scan_A out/scan_B
import sys, json
import numpy as np, cv2
sys.path.insert(0,'.'); sys.path.insert(0,'scripts')
from repeatability import align, load, raster
from roomscan.drift import icp_2d
from scipy.spatial import cKDTree

def run(ra_dir, rb_dir):
    A, wa = load(ra_dir); B, wb = load(rb_dir)
    R, t, fit = align(wb, wa)
    wb_in_a = wb @ R.T + t
    treeA = cKDTree(wa)
    res = []
    for ra in A['rooms']:
        polyA = np.array(ra['polygon'])
        lo, hi = polyA.min(0)-0.3, polyA.max(0)+0.3
        selA = wa[(wa>lo).all(1)&(wa<hi).all(1)]
        selB = wb_in_a[(wb_in_a>lo).all(1)&(wb_in_a<hi).all(1)]
        if len(selA)<200 or len(selB)<200: continue
        Rl, tl, f = icp_2d(selB, cKDTree(selA), selA, iterations=40)
        res.append((ra['id'], np.linalg.norm(tl)*100, np.degrees(np.arctan2(Rl[1,0],Rl[0,0])), f))
    return fit, res
fit,res = run(sys.argv[1], sys.argv[2])
print('global fit', round(fit,2))
for r in res: print('%s local shift %.1f cm, rot %.2f deg, fit %.2f' % r)
