"""
Reading a Stray Scanner capture.

A capture is a folder (or a .zip of that folder) containing:
  odometry.csv   one row per frame: timestamp, frame, x y z, qx qy qz qw, fx fy cx cy
  depth/NNNNNN.png       16-bit depth in millimetres, 256x192
  confidence/NNNNNN.png  ARKit confidence per depth pixel: 0 low, 1 medium, 2 high
  rgb.mp4, imu.csv, camera_matrix.csv  (not needed for the LiDAR tier)

Important convention, checked on our own data: the poses are camera-to-world
with the camera in OpenCV convention (x right, y down, z forward), and the
world y axis points UP (ARKit is gravity aligned). If you apply the usual
ARKit flip diag(1,-1,-1) the floor disappears, so we do not flip.
"""
import io
import os
import zipfile

import cv2
import numpy as np
from scipy.spatial.transform import Rotation

DEPTH_W, RGB_W = 256, 1920   # intrinsics in odometry.csv are for the RGB image


class Capture:
    def __init__(self, path):
        self.path = path
        self.zip = zipfile.ZipFile(path) if path.endswith(".zip") else None
        self.prefix = self._find_prefix()
        self.odometry = np.genfromtxt(io.BytesIO(self._read("odometry.csv")),
                                      delimiter=",", skip_header=1)
        self.name = os.path.basename(path.rstrip("/")).replace(".zip", "")

    # --- file access that works the same for a folder or a zip -------------
    def _find_prefix(self):
        if self.zip is None:
            return self.path.rstrip("/") + "/"
        for name in self.zip.namelist():
            if name.endswith("odometry.csv"):
                return name[: -len("odometry.csv")]
        raise FileNotFoundError("odometry.csv not found in zip")

    def _read(self, rel):
        if self.zip is not None:
            return self.zip.read(self.prefix + rel)
        with open(self.prefix + rel, "rb") as f:
            return f.read()

    def _png(self, rel):
        try:
            raw = self._read(rel)
        except (KeyError, FileNotFoundError):
            return None
        return cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_UNCHANGED)

    # --- per-frame data ----------------------------------------------------
    def __len__(self):
        return len(self.odometry)

    def pose(self, i):
        """4x4 camera-to-world matrix for row i of odometry.csv."""
        row = self.odometry[i]
        T = np.eye(4)
        T[:3, :3] = Rotation.from_quat(row[5:9]).as_matrix()
        T[:3, 3] = row[2:5]
        return T

    def timestamp(self, i):
        return float(self.odometry[i, 0])

    def frame_points(self, i, max_depth=3.5, min_confidence=2):
        """Back-project one depth frame into world coordinates (metres)."""
        row = self.odometry[i]
        fid = int(row[1])
        depth = self._png(f"depth/{fid:06d}.png")
        conf = self._png(f"confidence/{fid:06d}.png")
        if depth is None or conf is None:
            return np.empty((0, 3), np.float32)

        scale = DEPTH_W / RGB_W
        fx, fy, cx, cy = row[9:13] * scale
        keep = (conf >= min_confidence) & (depth > 0) & (depth < max_depth * 1000)
        v, u = np.nonzero(keep)
        z = depth[v, u] / 1000.0
        cam = np.stack([(u + 0.5 - cx) / fx * z, (v + 0.5 - cy) / fy * z, z], axis=1)

        T = self.pose(i)
        return (cam @ T[:3, :3].T + T[:3, 3]).astype(np.float32)
