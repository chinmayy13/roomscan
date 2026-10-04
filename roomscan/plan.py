"""
From a gravity-aligned point cloud to a dimensioned floor plan.

Pipeline, in the order it runs:
  1. floor height       : biggest horizontal slab of points near the bottom
  2. Manhattan rotation : the yaw that makes walls line up with the grid axes
  3. 2D maps            : "wall" evidence (points 0.3-1.8 m above floor) and
                          "floor" evidence (points within 4 cm of the floor)
  4. rooms              : open space, eroded so doorways pinch shut, gives one
                          seed per room; seeds are grown back with a watershed
  5. walls              : each room rectangle side is snapped to the peak of the
                          wall-point histogram (sub-centimetre localisation)
  6. openings           : where two rooms touch, the touching span is a doorway
  7. ceiling            : per room, the strongest horizontal slab above 1.8 m

Coordinates in the output: metres, x/y in the Manhattan-rotated floor plane,
height measured up from the floor.
"""
import cv2
import numpy as np
from scipy import ndimage

RES = 0.02          # plan grid resolution, metres per cell
WALL_LO, WALL_HI = 0.30, 1.80   # height band used as wall evidence
DOOR_HALF = 0.50   # erosion radius: pinches shut doorways and openings up to ~1 m wide
MIN_ROOM_AREA = 1.5 # m^2, smaller blobs are clutter


# ----------------------------------------------------------------- 1. floor
def find_floor(points):
    y = points[:, 1]
    hist, edges = np.histogram(y, bins=np.arange(y.min(), y.max() + 0.01, 0.01))
    lower_half = hist[: len(hist) // 2 + 1]
    coarse = edges[np.argmax(lower_half)] + 0.005
    return refine_plane(y, coarse)


def refine_plane(heights, guess, window=0.03):
    """Median of points within +-3 cm of a coarse plane guess -> mm-level estimate."""
    near = heights[np.abs(heights - guess) < window]
    return float(np.median(near)) if len(near) else float(guess)


# ------------------------------------------------------- 2. Manhattan yaw
YAW_MODE = "refined"   # "legacy" restores the first-pass yaw search (--legacy-yaw), see fixloop/


def manhattan_yaw(xz):
    """Walls are axis aligned at the yaw (0-90 deg) where 1D histograms of wall points are spikiest.

    Coarse 0.25 deg search over ALL points, then a 0.02 deg search around the winner. Deterministic:
    no random subsample, so adding or dropping a handful of points (float noise, another numpy
    version) cannot flip a near-tie between two grid steps and rotate the whole plan.
    """
    if YAW_MODE == "legacy":
        return _manhattan_yaw_legacy(xz)

    def score(deg):
        r = np.deg2rad(deg)
        rot = xz @ np.array([[np.cos(r), -np.sin(r)], [np.sin(r), np.cos(r)]])
        return sum((np.bincount(((c - c.min()) / RES).astype(int)) ** 2).sum() for c in rot.T)

    coarse = np.arange(0, 90, 0.25)
    best = coarse[int(np.argmax([score(d) for d in coarse]))]
    fine = np.arange(best - 0.25, best + 0.2501, 0.02)
    return np.deg2rad(fine[int(np.argmax([score(d) for d in fine]))])


def _manhattan_yaw_legacy(xz):
    """First-pass version: 0.25 deg steps on a RANDOM 200k-point subsample. Kept only so the
    first-pass fix-loop numbers can be regenerated. It is not stable: see fixloop/FIX_DECLARATION.md."""
    best, best_score = 0.0, -1
    sample = xz[np.random.default_rng(0).choice(len(xz), min(len(xz), 200_000), replace=False)]
    for deg in np.arange(0, 90, 0.25):
        r = np.deg2rad(deg)
        rot = sample @ np.array([[np.cos(r), -np.sin(r)], [np.sin(r), np.cos(r)]])
        score = sum((np.bincount(((c - c.min()) / RES).astype(int)) ** 2).sum() for c in rot.T)
        if score > best_score:
            best, best_score = deg, score
    return np.deg2rad(best)


def rotate(xz, yaw):
    return xz @ np.array([[np.cos(yaw), -np.sin(yaw)], [np.sin(yaw), np.cos(yaw)]])


# ------------------------------------------------------------- 3. 2D maps
class Grid:
    def __init__(self, xy, pad=0.5):
        self.origin = xy.min(0) - pad
        self.shape = tuple((np.ptp(xy, 0) + 2 * pad) / RES + 1)[::-1]
        self.shape = (int(self.shape[0]), int(self.shape[1]))   # rows=y, cols=x

    def cells(self, xy):
        ij = ((xy - self.origin) / RES).astype(int)
        return ij[:, 1], ij[:, 0]

    def count(self, xy):
        img = np.zeros(self.shape, np.float32)
        r, c = self.cells(xy)
        np.add.at(img, (r, c), 1)
        return img

    def to_metric(self, col, row):
        return self.origin[0] + (col + 0.5) * RES, self.origin[1] + (row + 0.5) * RES


def disk(radius_m):
    r = int(round(radius_m / RES))
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))


KERNEL = "square"   # "disk" restores the pre-iteration-3 behaviour (--legacy-geometry), see fixloop/


def opener(radius_m):
    """Structuring element for the opening steps in room_rectangle, room_outline, segment_rooms."""
    return square(radius_m) if KERNEL == "square" else disk(radius_m)


def square(radius_m):
    """Axis-aligned square kernel. Unlike a disk, opening with it keeps right-angle corners exact.

    The plan is already rotated into the Manhattan frame, so rooms are axis-aligned and a disk
    would only round their corners (found by the synthetic test: a disk opening put room edges
    ~10 cm inside the real walls).
    """
    r = int(round(radius_m / RES))
    return np.ones((2 * r + 1, 2 * r + 1), np.uint8)


# ------------------------------------------------------------- 4. rooms
def wall_cells(points_xy, heights, grid, bottom=0.3, top=1.8, slab=0.10, min_fraction=0.5):
    """A cell is wall if points fill most of its height column.

    Beds, tables and sofas are short, so they only fill a few 10 cm slabs.
    Walls fill nearly all of them. Doorways have empty slabs below ~2 m, so
    they correctly come out as "not wall" and show up as gaps.
    """
    keep = (heights > bottom) & (heights < top)
    r, c = grid.cells(points_xy[keep])
    slab_id = ((heights[keep] - bottom) / slab).astype(int)
    n_slabs = int(np.ceil((top - bottom) / slab))
    occupied = np.zeros(grid.shape + (n_slabs,), bool)
    occupied[r, c, slab_id] = True
    coverage = occupied.sum(-1) / n_slabs
    return (coverage >= min_fraction).astype(np.uint8), coverage


def segment_rooms(walls, interior, cam_cells):
    """Split the interior into rooms. Returns (labels, free)."""
    walls = cv2.morphologyEx(walls, cv2.MORPH_CLOSE, disk(0.04))
    inside = cv2.morphologyEx(interior, cv2.MORPH_CLOSE, disk(0.5))
    inside = ndimage.binary_fill_holes(inside).astype(np.uint8)
    for r, c in cam_cells:                       # where we walked is free too
        cv2.circle(inside, (int(c), int(r)), int(0.3 / RES), 1, -1)
    free = inside & (1 - walls)
    free = cv2.morphologyEx(free, cv2.MORPH_OPEN, opener(0.06))

    # Erode so doorways pinch shut, then label one seed per room.
    seeds, n = ndimage.label(cv2.erode(free, disk(DOOR_HALF)))
    sizes = ndimage.sum(np.ones_like(seeds), seeds, range(1, n + 1)) * RES ** 2
    markers = np.zeros(seeds.shape, np.int32)
    k = 0
    for lab, area in enumerate(sizes, start=1):
        if area >= 0.4:                          # seed area after erosion
            k += 1
            markers[seeds == lab] = k

    labels = grow_labels(markers, free)
    return labels, free


def grow_labels(markers, free):
    """Grow each room seed one cell at a time, only through free space.

    This is a geodesic growth: a label can only travel through open floor,
    so it cannot leak through a wall. Where two rooms meet (a doorway) the
    growth fronts collide and stop, which is exactly the room boundary.
    """
    labels = markers.copy()
    while True:
        grown = ndimage.grey_dilation(labels, size=3)
        fill = (labels == 0) & (free > 0) & (grown > 0)
        if not fill.any():
            return labels
        labels[fill] = grown[fill]


# ------------------------------------------------------------- 5. walls
LIDAR_SCALE_ERR = 0.01   # ~1% ARKit LiDAR scale error (prior; not validated against ground truth)

# Calibrated on the repeat pair (floor-only vs with-ceiling scans of the same flat), IN-SAMPLE.
# See scripts/interval_coverage.py. Each value is the per-scan sigma such that a 95% interval on the
# gap between two scans covers 95% of matched pairs: sigma = p95(|gap|) / (1.96 * sqrt(2)).
FACE_SIGMA = 0.04        # wall face snapped to real wall points: p95 gap 11 cm -> 4.0 cm (n=31 faces)
OUTLINE_SIGMA = 0.23     # outline-extent dimension: p95 gap 57 cm -> 21 cm (63 cm -> 23 cm in the first pass); 23 kept, the wider value
OPEN_SIDE_SIGMA = 0.23   # a wall edge with no wall points behind it (scan stopped, not a wall)
# The earlier priors (5 mm face, 3-4 cm outline) covered only 15% of matched face pairs.


def room_rectangle(mask):
    """Axis-aligned rectangle covering the bulk of a room mask (in grid cells).

    Thin tails (a corridor stub, a doorway bulge) are opened away first, and
    the 1st-99th percentile is used so a few stray cells cannot stretch it.
    """
    body = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_OPEN, opener(0.30))
    if body.sum() == 0:
        body = mask.astype(np.uint8)
    rows, cols = np.nonzero(body)
    return (np.percentile(cols, 1), np.percentile(cols, 99),
            np.percentile(rows, 1), np.percentile(rows, 99))


def snap_face(coord, wall_xy, axis, span, search=0.25):
    """Move one rectangle side onto the actual wall surface.

    Take wall points whose `along` coordinate lies within the side's span and
    whose `axis` coordinate is within +-25 cm of the guess. The densest 5 mm
    bin is the wall face; the mean of points within 1.5 cm of it is the answer.
    Returns (position, found_wall, support) where support = number of points on the face.
    """
    a, b = span
    sel = wall_xy[(wall_xy[:, 1 - axis] > a) & (wall_xy[:, 1 - axis] < b) &
                  (np.abs(wall_xy[:, axis] - coord) < search)][:, axis]
    if len(sel) < 50:
        return coord, False, 0
    hist, edges = np.histogram(sel, bins=np.arange(coord - search, coord + search + 0.005, 0.005))
    peak = edges[np.argmax(hist)] + 0.0025
    near = sel[np.abs(sel - peak) < 0.015]
    return float(near.mean()), True, int(len(near))


def interval(value, sigma):
    """95% interval as [low, high]."""
    return [round(value - 1.96 * sigma, 3), round(value + 1.96 * sigma, 3)]


# ----------------------------------------------------------- 7. ceiling
def ceiling_height(heights, xy, room_area, min_coverage=0.25):
    """Floor-relative ceiling height for one room, or None if the scan never saw it.

    Two traps this avoids:
      * Lofts and cupboard tops (2.0-2.4 m in many Indian flats) are also
        horizontal slabs. So we take the HIGHEST well-supported slab, not the
        biggest one.
      * A scan that never looked up still sees those cupboard tops. So the slab
        must cover at least 25% of the room's floor area; a cupboard top
        does not. If nothing qualifies we return None rather than guess.
    """
    keep = heights > 2.1
    up, up_xy = heights[keep], xy[keep]
    if len(up) < 300:
        return None
    hist, edges = np.histogram(up, bins=np.arange(2.1, up.max() + 0.02, 0.01))
    for b in np.argsort(edges[:-1])[::-1]:           # highest bin first
        if hist[b] < 0.3 * hist.max():
            continue
        level = edges[b] + 0.005
        slab = np.abs(up - level) < 0.02
        cells = np.unique(np.floor(up_xy[slab] / 0.1).astype(int), axis=0)
        if len(cells) * 0.01 >= min_coverage * room_area:
            return refine_plane(up, level, window=0.02)
    return None


# ----------------------------------------------------------- 6. openings
def find_openings(labels, min_width=0.5):
    """Doorways: stretches where two different room labels touch."""
    found = {}
    for shift in [(0, 1), (1, 0)]:
        a = labels[: labels.shape[0] - shift[0], : labels.shape[1] - shift[1]]
        b = labels[shift[0]:, shift[1]:]
        touch = (a > 0) & (b > 0) & (a != b)
        for r, c in zip(*np.nonzero(touch)):
            key = tuple(sorted((int(a[r, c]), int(b[r, c]))))
            found.setdefault(key, []).append((r, c))
    openings = []
    for (ra, rb), cells in found.items():
        cells = np.array(cells)
        extent = np.ptp(cells, 0) * RES                    # rows, cols span
        width = float(max(extent)) + RES
        if width >= min_width:
            openings.append({"rooms": [ra, rb], "width_m": round(width, 3),
                             "center_cell": cells.mean(0).tolist()})
    return openings


def room_outline(mask, simplify=0.15):
    """Rectilinear outline of a room mask, as a list of (x_cell, y_cell) corners.

    1. trace the mask contour and simplify it (Douglas-Peucker, 15 cm)
    2. call each simplified edge horizontal or vertical, merge runs of the same kind
    3. set each edge at the median coordinate of the contour points it covers
    4. corners are where consecutive horizontal/vertical edges cross
    Rooms segmented from the same label image cannot overlap, so neither can
    these outlines (up to the 15 cm simplification).
    """
    body = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_OPEN, opener(0.20))
    contours, _ = cv2.findContours(body, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contours:
        return None
    contour = max(contours, key=cv2.contourArea)[:, 0, :].astype(float)
    approx = cv2.approxPolyDP(contour.astype(np.int32), simplify / RES, True)[:, 0, :].astype(float)
    if len(approx) < 4:
        return None

    edges = []   # (kind, coordinate)
    n = len(approx)
    for i in range(n):
        p, q = approx[i], approx[(i + 1) % n]
        kind = "h" if abs(q[0] - p[0]) >= abs(q[1] - p[1]) else "v"
        coord = (p[1] + q[1]) / 2 if kind == "h" else (p[0] + q[0]) / 2
        length = abs(q[0] - p[0]) + abs(q[1] - p[1])
        if edges and edges[-1][0] == kind:      # merge with previous same-kind edge
            k, c, L = edges[-1]
            edges[-1] = (k, (c * L + coord * length) / (L + length), L + length)
        else:
            edges.append((kind, coord, length))
    if len(edges) > 1 and edges[0][0] == edges[-1][0]:
        k, c, L = edges.pop()
        k0, c0, L0 = edges[0]
        edges[0] = (k, (c * L + c0 * L0) / (L + L0), L + L0)
    if len(edges) < 4 or len(edges) % 2:
        return None

    corners = []
    for i in range(len(edges)):
        a, b = edges[i - 1], edges[i]
        x = a[1] if a[0] == "v" else b[1]
        y = a[1] if a[0] == "h" else b[1]
        corners.append((x, y))
    return corners


def polygon_area(pts):
    x, y = np.array(pts).T
    return 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))
