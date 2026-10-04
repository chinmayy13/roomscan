"""
One capture in, one plan out.

    python -m roomscan path/to/capture.zip --out out/my_flat
    python -m roomscan path/to/capture.zip --out out/my_flat_nodrift --no-drift

Writes plan.json (the output contract) and plan.png (the rendered plan).
"""
import json
import os
import pickle
import time

import cv2
import numpy as np

from . import drift, plan
from .capture import Capture
from .cloud import build_chunks, merge, voxel_downsample

SCHEMA_VERSION = "0.1"
SNAP_MIN_HEIGHT = 1.10   # metres above floor


def load_chunks(path, cache_dir):
    """Fusing depth is the slow part (~1-2 min); cache it next to the output."""
    cache = os.path.join(cache_dir, "chunks.pkl")
    if os.path.exists(cache):
        with open(cache, "rb") as f:
            return pickle.load(f)
    chunks = build_chunks(Capture(path))
    with open(cache, "wb") as f:
        pickle.dump(chunks, f)
    return chunks


def wall_to_wall(edges, axis):
    """Distance between the two main opposite wall faces along one axis.

    `axis=0` means faces that are lines x = const, so the result is the room's
    x dimension. On each side of the room we take the measured face with the
    longest span: the real wall, not a cupboard edge or a doorway jamb.
    Returns (distance, True) or (None, False) if either side was not measured.
    """
    faces = [e for e in edges if e["axis"] == axis and e["measured"]]
    if len(faces) < 2:
        return None, False
    mid = np.mean([e["pos"] for e in edges if e["axis"] == axis])
    low = [e for e in faces if e["pos"] < mid]
    high = [e for e in faces if e["pos"] >= mid]
    if not low or not high:
        return None, False
    strongest = lambda group: max(group, key=lambda e: e["support"])
    return abs(strongest(high)["pos"] - strongest(low)["pos"]), True


def measure_room(k, mask, grid, wall_xy, room_heights, room_xy, room_dims="extent"):
    corners = plan.room_outline(mask)
    if corners is None:                       # fall back to a rectangle
        c0, c1, r0, r1 = plan.room_rectangle(mask)
        corners = [(c0, r0), (c1, r0), (c1, r1), (c0, r1)]
    pts = [grid.to_metric(c, r) for c, r in corners]

    # Rebuild the outline as alternating edges: each edge is a line x=const or y=const.
    n = len(pts)
    edges = []
    for i in range(n):
        p, q = pts[i], pts[(i + 1) % n]
        if abs(q[1] - p[1]) < abs(q[0] - p[0]):         # horizontal edge, y = const
            edges.append({"axis": 1, "pos": (p[1] + q[1]) / 2, "span": sorted([p[0], q[0]])})
        else:                                            # vertical edge, x = const
            edges.append({"axis": 0, "pos": (p[0] + q[0]) / 2, "span": sorted([p[1], q[1]])})

    # Snap every edge onto the real wall face. The search window (+-8 cm) is
    # smaller than any wall thickness, so we cannot jump to the next room's face.
    for e in edges:
        a, b = e["span"]
        e["pos"], e["measured"], e["support"] = plan.snap_face(e["pos"], wall_xy, e["axis"],
                                                 (a + 0.15, b - 0.15), search=0.08)

    # Corners are intersections of consecutive (snapped) edges.
    corners_m = []
    for i in range(n):
        prev, cur = edges[i - 1], edges[i]
        x = prev["pos"] if prev["axis"] == 0 else cur["pos"]
        y = prev["pos"] if prev["axis"] == 1 else cur["pos"]
        corners_m.append((x, y))

    walls = []
    for i, e in enumerate(edges):
        p, q = corners_m[i], corners_m[(i + 1) % n]
        length = float(np.hypot(q[0] - p[0], q[1] - p[1]))
        # each end of a wall is set by a neighbouring wall's face
        end_sig = [plan.FACE_SIGMA if edges[j]["measured"] else plan.OPEN_SIDE_SIGMA for j in (i - 1, (i + 1) % n)]
        sigma = np.sqrt(end_sig[0] ** 2 + end_sig[1] ** 2 + (plan.LIDAR_SCALE_ERR * length) ** 2)
        walls.append({
            "id": f"R{k}-W{i + 1}", "length_m": round(length, 3), "interval_95_m": plan.interval(length, sigma),
            "face_measured": bool(e["measured"]),
            "start": [round(p[0], 3), round(p[1], 3)], "end": [round(q[0], 3), round(q[1], 3)],
        })

    area = plan.polygon_area(corners_m)
    perimeter = sum(w["length_m"] for w in walls)
    # moving an edge of length L by sigma changes the area by L*sigma; edges are independent
    edge_terms = [w["length_m"] * (plan.FACE_SIGMA if e["measured"] else plan.OPEN_SIDE_SIGMA)
                  for w, e in zip(walls, edges)]
    sig_area = np.hypot(np.sqrt(np.sum(np.square(edge_terms))), 2 * plan.LIDAR_SCALE_ERR * area)

    ceil = plan.ceiling_height(room_heights, room_xy, area)
    if ceil is not None:
        sig_c = np.hypot(0.004, plan.LIDAR_SCALE_ERR * ceil)
        ceiling = {"height_m": round(ceil, 3), "interval_95_m": plan.interval(ceil, sig_c)}
    else:
        ceiling = {"height_m": None, "reason": "ceiling not captured in this scan"}

    xs, ys = zip(*corners_m)
    extent = {"x": max(xs) - min(xs), "y": max(ys) - min(ys)}
    span = {"x": wall_to_wall(edges, axis=0), "y": wall_to_wall(edges, axis=1)}
    if room_dims == "extent":      # the "before" behaviour, kept for the fix-loop rerun
        span = {"x": (extent["x"], False), "y": (extent["y"], False)}

    def dim(axis):
        value, measured = span[axis]
        if not measured:
            value = extent[axis]
        sig = np.hypot(plan.FACE_SIGMA * np.sqrt(2) if measured else plan.OUTLINE_SIGMA,
                       plan.LIDAR_SCALE_ERR * value)
        return {"value_m": round(value, 3), "interval_95_m": plan.interval(value, sig),
                "method": "wall_to_wall" if measured else "outline_extent"}

    return {
        "id": f"R{k}",
        "shape": "rectangle" if n == 4 else f"rectilinear_{n}_corners",
        "width_m": dim("x")["value_m"], "depth_m": dim("y")["value_m"],
        "dimensions": {"x": dim("x"), "y": dim("y")},
        "floor_area_m2": round(area, 2), "floor_area_interval_95_m2": plan.interval(area, sig_area),
        "ceiling": ceiling,
        "walls": walls,
        "polygon": [[round(x, 3), round(y, 3)] for x, y in corners_m],
    }


def run(path, out_dir, use_drift=True, room_dims="extent", legacy_geometry=False, legacy_yaw=False):
    """legacy_geometry=True restores the geometry from before fix-loop iteration 3 (disk-shaped
    openings that round room corners, and snapping evidence from 0.3 m up), so the 'before' run
    of that iteration can be regenerated."""
    global SNAP_MIN_HEIGHT
    saved = (plan.KERNEL, SNAP_MIN_HEIGHT, plan.YAW_MODE)
    if legacy_geometry:
        plan.KERNEL, SNAP_MIN_HEIGHT = "disk", 0.30
    if legacy_yaw:
        plan.YAW_MODE = "legacy"
    try:
        return _run(path, out_dir, use_drift, room_dims)
    finally:
        plan.KERNEL, SNAP_MIN_HEIGHT, plan.YAW_MODE = saved


def _run(path, out_dir, use_drift, room_dims):
    t_start = time.time()
    os.makedirs(out_dir, exist_ok=True)
    chunks = load_chunks(path, out_dir)

    floor = plan.find_floor(merge(chunks))
    drift_log = None
    if use_drift:
        before = drift.wall_consistency(chunks, floor)
        chunks, drift_log = drift.correct(chunks, floor)
        after = drift.wall_consistency(chunks, floor)

    points = merge(chunks)
    floor = plan.find_floor(points)
    heights = points[:, 1] - floor
    in_band = (heights > plan.WALL_LO) & (heights < plan.WALL_HI)

    yaw = plan.manhattan_yaw(points[in_band][:, [0, 2]])
    xy = plan.rotate(points[:, [0, 2]], yaw)
    cams = np.concatenate([c["cams"] for c in chunks])
    cam_xy = plan.rotate(cams[:, [0, 2]], yaw)

    grid = plan.Grid(xy)
    walls, _ = plan.wall_cells(xy, heights, grid)
    interior = (grid.count(xy[heights < 1.8]) > 0).astype(np.uint8)
    rows, cols = grid.cells(cam_xy)
    labels, free = plan.segment_rooms(walls, interior, list(zip(rows, cols)))

    wall_xy = xy[in_band]
    # Evidence for snapping a face onto a wall: only points above 1.1 m. Tables, beds and sofas stop
    # below that, so their edges cannot be mistaken for a wall face (the synthetic test caught a
    # table edge being reported as a measured wall).
    snap_xy = xy[(heights > SNAP_MIN_HEIGHT) & (heights < plan.WALL_HI)]
    pt_rows, pt_cols = grid.cells(xy)
    pt_label = labels[np.clip(pt_rows, 0, labels.shape[0] - 1), np.clip(pt_cols, 0, labels.shape[1] - 1)]

    rooms = []
    for k in range(1, labels.max() + 1):
        mask = labels == k
        if mask.sum() * plan.RES ** 2 < plan.MIN_ROOM_AREA:
            continue
        rooms.append(measure_room(k, mask, grid, snap_xy, heights[pt_label == k], xy[pt_label == k], room_dims))

    openings = []
    keep = {r["id"] for r in rooms}
    for o in plan.find_openings(labels):
        a, b = (f"R{o['rooms'][0]}", f"R{o['rooms'][1]}")
        if a in keep and b in keep:
            w = o["width_m"]
            openings.append({"type": "doorway_or_opening", "between": [a, b], "width_m": w,
                             "interval_95_m": plan.interval(w, 0.15)})   # 15 cm: width is a coarse label-contact span, unvalidated

    result = {
        "schema_version": SCHEMA_VERSION,
        "capture": os.path.basename(path),
        "tier": "lidar",
        "room_dims_method": room_dims,
        "units": "metres",
        "frame": "floor plane, Manhattan-aligned; height measured up from the floor",
        "drift_correction": {"enabled": use_drift, "wall_gap_before": before if use_drift else None,
                             "wall_gap_after": after if use_drift else None, "chunks": drift_log},
        "rooms": rooms,
        "openings": openings,
        "adjacency": [list(a) for a in sorted({tuple(o["between"]) for o in openings})],
        "footprint_m2": round(sum(r["floor_area_m2"] for r in rooms), 2),
        "damage_regions": [], "concealed_damage_flags": [], "scope_line_items": [],
        "not_implemented": ["damage detection", "concealed-damage rules", "scope line items",
                            "window detection", "non-rectangular room outlines"],
        "intervals_note": ("95% intervals. Wall-face (4 cm) and outline (23 cm) sigmas were fitted on one repeat pair of the same "
                           "flat, in-sample; ceiling (4 mm + 1%), scale (1%) and opening (15 cm) are priors. "
                           "None is calibrated against tape ground truth."),
        "runtime_s": round(time.time() - t_start, 1),
    }
    # wall points in the plan frame, used by the repeatability script to line up two scans
    np.save(os.path.join(out_dir, "wall_xy.npy"), voxel_downsample(wall_xy, 0.04))
    with open(os.path.join(out_dir, "plan.json"), "w") as f:
        json.dump(result, f, indent=2)
    render(os.path.join(out_dir, "plan.png"), grid, wall_xy, labels, rooms, openings)
    return result


def render(path, grid, wall_xy, labels, rooms, openings, px_per_m=60):
    """Top-down plan (as seen from above): grey wall points, room outlines with dimensions."""
    scale = px_per_m * plan.RES
    density = grid.count(wall_xy)
    bg = 255 - np.clip(density / max(np.percentile(density[density > 0], 90), 1) * 160, 0, 160)
    img = cv2.cvtColor(cv2.resize(bg.astype(np.uint8), None, fx=scale, fy=scale), cv2.COLOR_GRAY2BGR)
    # No flip: grid rows follow ARKit's z axis, which is exactly a view from
    # above. Flipping would mirror the flat.

    def px(x, y):
        return int((x - grid.origin[0]) * px_per_m), int((y - grid.origin[1]) * px_per_m)

    for r in rooms:
        poly = np.array([px(x, y) for x, y in r["polygon"]], np.int32)
        cv2.polylines(img, [poly], True, (40, 90, 200), 2)
        cx, cy = poly.mean(0).astype(int)
        lines = [r["id"], f"{r['width_m']:.2f} x {r['depth_m']:.2f} m", f"{r['floor_area_m2']:.1f} m2"]
        if r["ceiling"].get("height_m"):
            lines.append(f"ceil {r['ceiling']['height_m']:.2f} m")
        for i, text in enumerate(lines):
            cv2.putText(img, text, (cx - 45, cy - 20 + 18 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (20, 20, 20), 1, cv2.LINE_AA)
    cv2.imwrite(path, img)
