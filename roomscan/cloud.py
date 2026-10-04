"""
Fuse depth frames into a point cloud, kept as time chunks ("submaps").

Why chunks: ARKit pose drift grows slowly with time. If we keep each ~15 s
slice of the walk as its own small cloud, the drift module can later nudge
each slice into agreement with the rest. Within one slice drift is negligible.
"""
import numpy as np


def voxel_downsample(points, size):
    """Keep one point per cubic voxel of `size` metres."""
    if len(points) == 0:
        return points
    keys = np.floor(points / size).astype(np.int64)
    _, first = np.unique(keys, axis=0, return_index=True)
    return points[first]


def build_chunks(capture, frame_step=5, chunk_seconds=15.0, voxel=0.02):
    """Return a list of submaps: {'points', 'cams', 't0', 't1'}."""
    chunks, current, cams = [], [], []
    t_start = capture.timestamp(0)

    def close_chunk(t_end):
        if current:
            chunks.append({
                "points": voxel_downsample(np.concatenate(current), voxel),
                "cams": np.array(cams),
                "t0": t_start, "t1": t_end,
            })

    for i in range(0, len(capture), frame_step):
        t = capture.timestamp(i)
        if t - t_start > chunk_seconds:
            close_chunk(t)
            current, cams, t_start = [], [], t
        current.append(capture.frame_points(i))
        cams.append(capture.pose(i)[:3, 3])
    close_chunk(capture.timestamp(len(capture) - 1))
    return chunks


def merge(chunks, voxel=0.02):
    return voxel_downsample(np.concatenate([c["points"] for c in chunks]), voxel)
