"""Adaptive low-poly terrain.

Vertices are sampled densely on greens/tees, medium on fairways, sparse in the
rough and outside the course; feature outlines are inserted as vertices so the
Delaunay facets follow fairway/green/bunker edges. Each facet gets one surface
class (flat-shaded colour in the viewer) and one averaged aerial-photo colour.
"""
from __future__ import annotations

import numpy as np
import shapely
from scipy.spatial import Delaunay
from shapely.geometry import Polygon
from shapely.ops import triangulate, unary_union

from .geo import densify
from .model import (CLS_BUILDING, CLS_BUNKER, CLS_FAIRWAY, CLS_GREEN, CLS_OUT, CLS_PATH, CLS_ROUGH,
                    CLS_TEE, CLS_WATER, CLS_WOOD, Course, Tree)

# class: (interior spacing m, outline step m)   detail multiplier applied on top
SPACING = {
    CLS_GREEN: (1.6, 1.2), CLS_TEE: (2.5, 1.6), CLS_FAIRWAY: (5.5, 2.5), CLS_BUNKER: (2.2, 1.2),
    CLS_WATER: (14, 3.0), CLS_WOOD: (11, 7), CLS_ROUGH: (8, 6), CLS_PATH: (None, 2.0), CLS_BUILDING: (None, None),
}
PRIORITY = [CLS_ROUGH, CLS_WOOD, CLS_FAIRWAY, CLS_TEE, CLS_GREEN, CLS_BUNKER, CLS_WATER, CLS_PATH, CLS_BUILDING]


def _poly(f):
    p = Polygon(f.ring, f.holes)
    return p if p.is_valid else p.buffer(0)


def _jitter_grid(bounds, step, rng):
    x0, y0, x1, y1 = bounds
    xs = np.arange(x0, x1 + step, step)
    ys = np.arange(y0, y1 + step, step)
    X, Y = np.meshgrid(xs, ys)
    # hex-ish offset + jitter keeps triangles well shaped but irregular
    X = X + (np.arange(len(ys))[:, None] % 2) * step * 0.5
    P = np.column_stack([X.ravel(), Y.ravel()])
    return P + rng.uniform(-0.3, 0.3, P.shape) * step


class Terrain:
    def __init__(self, course: Course, detail=1.0, seed=7):
        self.course = course
        rng = np.random.default_rng(seed)
        e0, n0, e1, n1 = course.extent
        geoms = {c: [] for c in PRIORITY}
        for f in course.features:
            if f.cls in geoms:
                g = _poly(f)
                if not g.is_empty:
                    geoms[f.cls].append(g)
        self.union = {c: unary_union(g) if g else None for c, g in geoms.items()}
        has_course = self.union[CLS_ROUGH] is not None and not self.union[CLS_ROUGH].is_empty
        self.background = CLS_OUT if has_course else CLS_ROUGH

        pts = [_jitter_grid(course.extent, 16 * detail, rng)]
        # extent border
        for t in np.linspace(0, 1, 60):
            pts.append(np.array([[e0 + t * (e1 - e0), n0], [e0 + t * (e1 - e0), n1],
                                 [e0, n0 + t * (n1 - n0)], [e1, n0 + t * (n1 - n0)]]))
        for cls, gl in geoms.items():
            sp_in, sp_edge = SPACING[cls]
            for g in gl:
                if sp_in:
                    cand = _jitter_grid(g.bounds, sp_in * detail, rng)
                    inside = shapely.contains_xy(g, cand[:, 0], cand[:, 1])
                    pts.append(cand[inside])
                if sp_edge:
                    for poly in getattr(g, "geoms", [g]):
                        for ring in [poly.exterior, *poly.interiors]:
                            pts.append(densify(np.asarray(ring.coords), sp_edge * detail)[:-1])
        for h in course.holes:
            pts.append(np.array([h.tee, h.pin]))
        P = np.vstack(pts)
        P[:, 0] = np.clip(P[:, 0], e0, e1)
        P[:, 1] = np.clip(P[:, 1], n0, n1)
        # de-duplicate near-coincident points
        key = np.round(P / 0.35).astype(np.int64)
        _, idx = np.unique(key, axis=0, return_index=True)
        P = P[np.sort(idx)]
        self.tri = Delaunay(P)
        self.P = P
        self.F = self.tri.simplices.astype(np.uint32)

        Z = course.dem.sample(P[:, 0], P[:, 1])
        # per-vertex classes for height edits
        if self.union[CLS_BUNKER] is not None:
            inner = self.union[CLS_BUNKER].buffer(-0.4)
            Z = Z - 0.5 * shapely.contains_xy(inner, P[:, 0], P[:, 1])
        if geoms[CLS_WATER]:
            for g in geoms[CLS_WATER]:
                ring = densify(np.asarray(g.exterior.coords), 3.0) if g.geom_type == "Polygon" else None
                if ring is None:
                    continue
                level = float(np.percentile(course.dem.sample(ring[:, 0], ring[:, 1]), 10)) - 0.5
                m = shapely.contains_xy(g.buffer(0.5), P[:, 0], P[:, 1])
                Z[m] = np.minimum(Z[m], level)
        self.Z = Z

        cent = P[self.F].mean(axis=1)
        cls = np.full(len(self.F), self.background, dtype=np.uint8)
        for c in PRIORITY:
            g = self.union[c]
            if g is not None and not g.is_empty:
                cls[shapely.contains_xy(g, cent[:, 0], cent[:, 1])] = c
        self.face_cls = cls

        self.face_rgb = None
        im = course.imagery
        if im is not None:
            H, W = im.img.shape[:2]
            acc = np.zeros((len(self.F), 3))
            # average of centroid + 3 points toward the vertices
            V = P[self.F]
            for wts in ([1 / 3] * 3, [0.6, 0.2, 0.2], [0.2, 0.6, 0.2], [0.2, 0.2, 0.6]):
                q = (V * np.array(wts)[None, :, None]).sum(axis=1)
                px = np.clip(((q[:, 0] - im.e_min) / (im.e_max - im.e_min) * W).astype(int), 0, W - 1)
                py = np.clip(((im.n_max - q[:, 1]) / (im.n_max - im.n_min) * H).astype(int), 0, H - 1)
                acc += im.img[py, px]
            self.face_rgb = (acc / 4).astype(np.uint8)

    # --- queries used to place shots -------------------------------------------------
    def height(self, e, n):
        e = np.atleast_1d(np.asarray(e, float))
        n = np.atleast_1d(np.asarray(n, float))
        q = np.column_stack([e, n])
        s = self.tri.find_simplex(q)
        out = self.course.dem.sample(e, n)
        ok = s >= 0
        if ok.any():
            T = self.tri.transform[s[ok]]
            b = np.einsum("ijk,ik->ij", T[:, :2], q[ok] - T[:, 2])
            bc = np.column_stack([b, 1 - b.sum(axis=1)])
            out[ok] = (self.Z[self.tri.simplices[s[ok]]] * bc).sum(axis=1)
        return out

    def surface(self, e, n):
        s = int(self.tri.find_simplex(np.array([[e, n]]))[0])
        return int(self.face_cls[s]) if s >= 0 else self.background

    # --- trees ----------------------------------------------------------------------
    def make_trees(self, lidar_trees=None, osm_trees=None, density=1.0, seed=3, cap=30000):
        rng = np.random.default_rng(seed)
        keepout = [self.union[c] for c in (CLS_GREEN, CLS_TEE, CLS_BUNKER, CLS_WATER, CLS_FAIRWAY, CLS_BUILDING)
                   if self.union[c] is not None]
        ko = unary_union(keepout).buffer(1.5) if keepout else None
        trees = []
        if lidar_trees:
            trees = list(lidar_trees)
        else:
            for t in osm_trees or []:
                trees.append(Tree(t.e, t.n, t.height or rng.uniform(9, 17), 0, int(rng.random() < 0.3)))
            wood = self.union[CLS_WOOD]
            if wood is not None and not wood.is_empty:
                cand = _jitter_grid(wood.bounds, 7.5 / np.sqrt(density), rng)
                cand = cand[shapely.contains_xy(wood, cand[:, 0], cand[:, 1])]
                for e, n in cand:
                    trees.append(Tree(e, n, rng.uniform(8, 19), 0, int(rng.random() < 0.35)))
        if not trees:
            return np.zeros((0, 6), np.float32)
        A = np.array([[t.e, t.n, t.height, t.radius, t.kind] for t in trees], float)
        if ko is not None:
            A = A[~shapely.contains_xy(ko, A[:, 0], A[:, 1])]
        e0, n0, e1, n1 = self.course.extent
        A = A[(A[:, 0] > e0) & (A[:, 0] < e1) & (A[:, 1] > n0) & (A[:, 1] < n1)]
        if len(A) > cap:
            A = A[rng.choice(len(A), cap, replace=False)]
        r = np.where(A[:, 3] > 0, A[:, 3], A[:, 2] * rng.uniform(0.22, 0.32, len(A)))
        if lidar_trees:
            kind = (r / np.maximum(A[:, 2], 1) < 0.24).astype(float)
        else:
            kind = A[:, 4]
        base = self.height(A[:, 0], A[:, 1])
        rot = rng.uniform(0, 2 * np.pi, len(A))
        return np.column_stack([A[:, 0], base, A[:, 1], A[:, 2], r, kind, rot]).astype(np.float32)

    # --- buildings -----------------------------------------------------------------------
    def buildings(self):
        out = []
        for f in self.course.features:
            if f.cls != CLS_BUILDING:
                continue
            g = _poly(f)
            if g.is_empty or g.area < 8:
                continue
            g = g.simplify(0.5)
            lv = f.tags.get("building:levels")
            try:
                h = float(f.tags.get("height") or (float(lv) * 3.2 + 1 if lv else 6.0))
            except ValueError:
                h = 6.0
            for poly in getattr(g, "geoms", [g]):
                ring = np.asarray(poly.exterior.coords)[:-1]
                base = float(self.height(ring[:, 0], ring[:, 1]).min())
                tris = [t for t in triangulate(poly) if poly.contains(t.representative_point())]
                roof = [np.asarray(t.exterior.coords)[:3].tolist() for t in tris]
                out.append({"ring": ring.round(2).tolist(), "base": round(base, 2), "h": round(h, 2), "roof": roof})
        return out
