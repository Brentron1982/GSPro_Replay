"""Coordinate helpers.

Scene convention (matches three.js): x = east (m), y = up (m), z = south (m).
Internally in Python we work with 2D local coords (e, n) in metres around an
origin lat/lon using a local equirectangular projection, which is accurate to
well under a metre over a golf course sized area.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

R_EARTH = 6378137.0
YD = 0.9144  # metres per yard


@dataclass
class LocalFrame:
    lat0: float
    lon0: float

    @property
    def _k(self):
        return math.cos(math.radians(self.lat0))

    def to_local(self, lat, lon):
        lat = np.asarray(lat, dtype=float)
        lon = np.asarray(lon, dtype=float)
        e = np.radians(lon - self.lon0) * R_EARTH * self._k
        n = np.radians(lat - self.lat0) * R_EARTH
        return e, n

    def to_latlon(self, e, n):
        e = np.asarray(e, dtype=float)
        n = np.asarray(n, dtype=float)
        lat = self.lat0 + np.degrees(n / R_EARTH)
        lon = self.lon0 + np.degrees(e / (R_EARTH * self._k))
        return lat, lon


@dataclass
class BBox:
    south: float
    west: float
    north: float
    east: float

    def expand_m(self, m: float) -> "BBox":
        dlat = math.degrees(m / R_EARTH)
        dlon = math.degrees(m / (R_EARTH * math.cos(math.radians((self.south + self.north) / 2))))
        return BBox(self.south - dlat, self.west - dlon, self.north + dlat, self.east + dlon)

    @property
    def center(self):
        return (self.south + self.north) / 2, (self.west + self.east) / 2

    def overpass(self):
        return f"{self.south},{self.west},{self.north},{self.east}"

    @staticmethod
    def parse(s: str) -> "BBox":
        """Parse 'south,west,north,east'."""
        a = [float(x) for x in s.split(",")]
        if len(a) != 4:
            raise ValueError("bbox must be south,west,north,east")
        return BBox(*a)


# --- Web Mercator (slippy tiles) ---------------------------------------------

def merc_px(lat, lon, z):
    """Global pixel coords at zoom z (256px tiles)."""
    lat = np.clip(np.asarray(lat, dtype=float), -85.05112878, 85.05112878)
    lon = np.asarray(lon, dtype=float)
    n = 256.0 * (2 ** z)
    x = (lon + 180.0) / 360.0 * n
    s = np.sin(np.radians(lat))
    y = (0.5 - np.log((1 + s) / (1 - s)) / (4 * math.pi)) * n
    return x, y


# --- polygon helpers -----------------------------------------------------------

def polygon_area(ring):
    r = np.asarray(ring)
    x, y = r[:, 0], r[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def polygon_centroid(ring):
    r = np.asarray(ring, dtype=float)
    if len(r) > 1 and np.allclose(r[0], r[-1]):
        r = r[:-1]
    x, y = r[:, 0], r[:, 1]
    xs, ys = np.roll(x, -1), np.roll(y, -1)
    c = x * ys - xs * y
    a = c.sum() / 2
    if abs(a) < 1e-9:
        return r.mean(axis=0)
    return np.array([((x + xs) * c).sum() / (6 * a), ((y + ys) * c).sum() / (6 * a)])


def densify(ring, step):
    """Insert points so no edge is longer than `step` metres."""
    r = np.asarray(ring, dtype=float)
    out = []
    for a, b in zip(r[:-1], r[1:]):
        d = np.linalg.norm(b - a)
        k = max(1, int(math.ceil(d / step)))
        for i in range(k):
            out.append(a + (b - a) * (i / k))
    out.append(r[-1])
    return np.array(out)


def polyline_length(pts):
    p = np.asarray(pts, dtype=float)
    return float(np.linalg.norm(np.diff(p, axis=0), axis=1).sum())


def point_along(pts, dist):
    """Point at distance `dist` along a polyline (clamped)."""
    p = np.asarray(pts, dtype=float)
    seg = np.linalg.norm(np.diff(p, axis=0), axis=1)
    acc = 0.0
    for i, L in enumerate(seg):
        if acc + L >= dist and L > 0:
            return p[i] + (p[i + 1] - p[i]) * ((dist - acc) / L)
        acc += L
    return p[-1].copy()


def project_on_polyline(pts, q):
    """Return distance-along of the closest point on polyline to q."""
    p = np.asarray(pts, dtype=float)
    q = np.asarray(q, dtype=float)
    best, best_d, acc = 0.0, 1e18, 0.0
    for a, b in zip(p[:-1], p[1:]):
        ab = b - a
        L2 = float(ab @ ab)
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, float((q - a) @ ab) / L2))
        c = a + ab * t
        d = float(np.linalg.norm(q - c))
        if d < best_d:
            best_d, best = d, acc + t * math.sqrt(L2)
        acc += math.sqrt(L2)
    return best
