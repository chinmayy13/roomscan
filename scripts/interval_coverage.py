"""
Calibration check on the repeat pair.

If each scan's wall-face error is N(0, sigma) independently, the gap between the same
face in two scans is N(0, sqrt(2)*sigma). A correct 95% interval therefore covers
|gap| <= 1.96 * sqrt(2) * sigma for about 95% of face pairs.

    python scripts/interval_coverage.py out/scan_A out/scan_B

Prints, for a few candidate sigmas, the share of matched face pairs the interval covers.

CAVEAT: this is IN-SAMPLE. The same pair is the evidence for choosing sigma and the test
of it, and both scans were walked by the same person in the same flat. It shows the old
prior was far too tight. It does not prove the new value is right on unseen flats.
"""
import sys

import numpy as np

sys.path.insert(0, ".")
sys.path.insert(0, "scripts")
from diagnose_repeatability import face_gaps

gaps, n_faces = face_gaps(sys.argv[1], sys.argv[2])
print(f"matched face pairs: {len(gaps)}  (of {n_faces} measured faces in A)")
need = np.percentile(gaps, 95) / (1.96 * np.sqrt(2))
print(f"sigma that covers 95% of these pairs: {need * 100:.1f} cm\n")
print("sigma per face   half-width of 95% gap interval   coverage of matched pairs")
for sigma in (0.005, 0.01, 0.02, 0.03, 0.035, 0.04, 0.05):
    half = 1.96 * np.sqrt(2) * sigma
    print(f"  {sigma * 100:4.1f} cm          +-{half * 100:5.1f} cm                        {np.mean(gaps <= half):5.0%}")

from roomscan import plan
half = 1.96 * np.sqrt(2) * plan.FACE_SIGMA
print(f"\nshipped plan.FACE_SIGMA = {plan.FACE_SIGMA * 100:.1f} cm -> +-{half * 100:.1f} cm, "
      f"covers {np.mean(gaps <= half):.0%} of matched face pairs (in-sample)")
