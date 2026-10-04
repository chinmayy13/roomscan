import argparse
import json

from .pipeline import run


def main():
    p = argparse.ArgumentParser(description="Stray Scanner LiDAR capture -> dimensioned floor plan")
    p.add_argument("capture", help="capture folder or .zip exported from Stray Scanner")
    p.add_argument("--out", required=True, help="output folder")
    p.add_argument("--no-drift", action="store_true", help="ablation: use ARKit poses as-is")
    p.add_argument("--room-dims", choices=["extent", "wall"], default="extent",
                   help="'extent' = outline extent (default); 'wall' = wall-to-wall between "
                        "strongest opposite faces (the fix-loop attempt, measured worse, see fixloop/)")
    p.add_argument("--legacy-geometry", action="store_true",
                   help="regenerate the 'before' run of fix-loop iteration 3 (rounded corners, 0.3 m snap evidence)")
    p.add_argument("--legacy-yaw", action="store_true",
                   help="first-pass Manhattan yaw (random subsample, 0.25 deg steps). Unstable: only for regenerating first-pass numbers")
    a = p.parse_args()
    result = run(a.capture, a.out, use_drift=not a.no_drift, room_dims=a.room_dims,
                 legacy_geometry=a.legacy_geometry, legacy_yaw=a.legacy_yaw)
    print(json.dumps({k: result[k] for k in ("capture", "footprint_m2", "adjacency", "runtime_s")}, indent=1))
    for r in result["rooms"]:
        c = r["ceiling"].get("height_m")
        print(f"  {r['id']}: {r['width_m']:.2f} x {r['depth_m']:.2f} m, {r['floor_area_m2']:.1f} m2, ceiling {c}")


if __name__ == "__main__":
    main()
