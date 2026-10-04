"""
Drift correction: plane-anchored, submap-to-map 2D ICP.

ARKit's visual-inertial odometry drifts slowly. On a long walk that revisits
rooms, the second visit's walls land a few centimetres away from the first
visit's, and the plan shows doubled walls.

We fix it in two steps per time chunk (submap), in walking order:
  1. Vertical: shift the chunk so its floor plane matches the global floor.
  2. Horizontal: rigidly align the chunk's wall points (0.3-1.8 m band) to
     the walls of all chunks already placed, with 2D ICP (yaw + x/y shift).
A correction is only accepted if the chunk genuinely overlaps the map and the
correction is small (< 3 deg, < 30 cm). Big jumps mean a bad match, not drift,
so we leave those chunks alone rather than invent geometry.

Turn it off with --no-drift to get the "poses used as-is" ablation.
"""
import numpy as np
from scipy.spatial import cKDTree

from .cloud import voxel_downsample
from .plan import refine_plane

MAX_YAW_DEG, MAX_SHIFT_M = 3.0, 0.30
MIN_OVERLAP = 0.30


def wall_points_2d(points, floor, voxel=0.04):
    h = points[:, 1] - floor
    band = points[(h > 0.3) & (h < 1.8)][:, [0, 2]]
    return voxel_downsample(band, voxel)


def icp_2d(src, dst_tree, dst, iterations=30):
    """Rigid 2D ICP with shrinking match radius. Returns R (2x2), t (2,), inlier fraction."""
    R, t = np.eye(2), np.zeros(2)
    for it in range(iterations):
        radius = 0.20 if it < 10 else (0.10 if it < 20 else 0.05)
        moved = src @ R.T + t
        dist, idx = dst_tree.query(moved, distance_upper_bound=radius)
        ok = np.isfinite(dist)
        if ok.sum() < 30:
            return R, t, 0.0
        p, q = moved[ok], dst[idx[ok]]
        pc, qc = p.mean(0), q.mean(0)
        U, _, Vt = np.linalg.svd((p - pc).T @ (q - qc))
        dR = (U @ Vt).T
        if np.linalg.det(dR) < 0:
            Vt[-1] *= -1
            dR = (U @ Vt).T
        R, t = dR @ R, dR @ t + (qc - dR @ pc)
    dist, _ = dst_tree.query(src @ R.T + t, distance_upper_bound=0.05)
    return R, t, float(np.isfinite(dist).mean())


def apply_2d(points, R, t):
    out = points.copy()
    xz = out[:, [0, 2]] @ R.T + t
    out[:, 0], out[:, 2] = xz[:, 0], xz[:, 1]
    return out


def correct(chunks, floor):
    """Return (corrected_chunks, log). Does not modify the input."""
    fixed, log = [], []
    map_pts = None
    for k, ch in enumerate(chunks):
        pts = ch["points"].copy()
        entry = {"chunk": k, "dy": 0.0, "yaw_deg": 0.0, "shift_m": 0.0, "overlap": None, "accepted": False}

        # 1. vertical: plane-anchored to the global floor
        near_floor = pts[np.abs(pts[:, 1] - floor) < 0.10, 1]
        if len(near_floor) > 500:
            dy = floor - refine_plane(near_floor, floor, window=0.05)
            pts[:, 1] += dy
            entry["dy"] = round(float(dy), 4)

        # 2. horizontal: ICP against everything placed so far
        walls = wall_points_2d(pts, floor)
        if map_pts is not None and len(walls) > 100:
            R, t, overlap = icp_2d(walls, cKDTree(map_pts), map_pts)
            yaw = np.degrees(np.arctan2(R[1, 0], R[0, 0]))
            # size of the move at the chunk's own centre, not at the world origin
            centre = walls.mean(0)
            shift = np.linalg.norm(centre @ R.T + t - centre)
            entry.update(yaw_deg=round(float(yaw), 3), shift_m=round(float(shift), 4),
                         overlap=round(overlap, 3))
            if overlap >= MIN_OVERLAP and abs(yaw) < MAX_YAW_DEG and shift < MAX_SHIFT_M:
                pts = apply_2d(pts, R, t)
                walls = walls @ R.T + t
                entry["accepted"] = True

        map_pts = walls if map_pts is None else voxel_downsample(np.vstack([map_pts, walls]), 0.04)
        fixed.append({**ch, "points": pts})
        log.append(entry)
    return fixed, log


def wall_consistency(chunks, floor):
    """Drift metric: median gap (cm) between each chunk's walls and the other chunks' walls.

    Only overlapping walls count (pairs closer than 15 cm). A perfectly
    consistent map scores about the voxel noise (~1 cm); drift pushes it up.
    """
    walls = [wall_points_2d(c["points"], floor) for c in chunks]
    gaps = []
    for k, w in enumerate(walls):
        others = [o for j, o in enumerate(walls) if j != k and len(o)]
        if not others or not len(w):
            continue
        d, _ = cKDTree(np.vstack(others)).query(w, distance_upper_bound=0.15)
        gaps.append(d[np.isfinite(d)])
    gaps = np.concatenate(gaps)
    return {"median_cm": round(float(np.median(gaps)) * 100, 2),
            "p90_cm": round(float(np.percentile(gaps, 90)) * 100, 2)}
