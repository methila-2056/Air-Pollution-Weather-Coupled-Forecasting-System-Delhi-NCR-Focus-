"""Pure-NumPy helpers shared by the CTM adapters (no heavy optional deps)."""

import numpy as np


def idw_regrid(
    src_lat: np.ndarray,
    src_lon: np.ndarray,
    src_val: np.ndarray,
    dst_lat: np.ndarray,
    dst_lon: np.ndarray,
    power: float = 2.0,
    radius_deg: float = 0.25,
) -> np.ndarray:
    """Inverse-distance-weighted regrid of scattered values onto a grid.

    ``src_lat/src_lon/src_val`` are parallel 1-D arrays of the known points;
    ``dst_lat/dst_lon`` are flat 1-D arrays of the destination grid points.
    Points farther than ``radius_deg`` from every source contribute 0 (so a
    sparse HYSPLIT forecast never over-spreads beyond its footprint).
    """
    dst = np.zeros(dst_lat.size, dtype=float)
    for i in range(dst_lat.size):
        dlat = dst_lat[i] - src_lat
        dlon = dst_lon[i] - src_lon
        dlon = np.where(dlon > 180.0, dlon - 360.0, np.where(dlon < -180.0, dlon + 360.0, dlon))
        dist = np.hypot(dlat, dlon)
        w = np.where(dist == 0.0, 1.0, np.power(dist, power))
        mask = dist <= radius_deg
        if not mask.any():
            dst[i] = 0.0
            continue
        if (dist == 0.0).any():
            j = int(np.argmin(dist))
            dst[i] = src_val[j]
            continue
        w = np.where(mask, 1.0 / w, 0.0)
        dst[i] = float(np.sum(w * src_val) / np.sum(w))
    return dst


def mesh_to_flat(lat: np.ndarray, lon: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Meshgrid (lat, lon) vectors into two flat coordinate arrays."""
    mlat, mlon = np.meshgrid(lat, lon, indexing="ij")
    return mlat.ravel(), mlon.ravel()


def flat_to_mesh(flat: np.ndarray, lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    return np.asarray(flat).reshape(len(lat), len(lon))
