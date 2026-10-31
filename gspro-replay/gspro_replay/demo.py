"""A synthetic 4-hole course + GSPro-style round, so everything can be tried
without network access. Same data structures as the real OSM/LiDAR pipeline."""
from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
from scipy import ndimage
from shapely.geometry import LineString, Point, Polygon

from .geo import LocalFrame
from .model import (CLS_BUILDING, CLS_BUNKER, CLS_FAIRWAY, CLS_GREEN, CLS_PATH, CLS_ROUGH, CLS_TEE,
                    CLS_WATER, CLS_WOOD, DEM, Course, Feature, Hole, Imagery)


def _ring(g):
    return np.asarray(g.exterior.coords)


def _blob(cx, cy, rx, ry, rot=0.0, wobble=0.12, seed=0, n=28):
    rng = np.random.default_rng(seed)
    a = np.linspace(0, 2 * np.pi, n, endpoint=False)
    k = 1 + wobble * (np.sin(3 * a + rng.uniform(0, 6)) + 0.5 * np.sin(5 * a + rng.uniform(0, 6)))
    x, y = rx * k * np.cos(a), ry * k * np.sin(a)
    c, s = np.cos(rot), np.sin(rot)
    pts = np.column_stack([cx + c * x - s * y, cy + s * x + c * y])
    return np.vstack([pts, pts[:1]])


HOLES = [  # number, par, path (tee -> pin), fairway start fraction
    (1, 4, [(-350, -220), (-150, -150), (-20, -40)], 0.45),
    (2, 3, [(40, -10), (190, 60)], None),
    (3, 5, [(220, 130), (180, 320), (-10, 420), (-165, 390)], 0.3),
    (4, 4, [(-260, 330), (-330, 120), (-300, -60)], 0.4),
]


def build_course(seed=11):
    rng = np.random.default_rng(seed)
    extent = (-480.0, -330.0, 360.0, 540.0)
    res = 2.0
    e0, n0, e1, n1 = extent
    W, H = int((e1 - e0) / res) + 1, int((n1 - n0) / res) + 1
    E, N = np.meshgrid(e0 + np.arange(W) * res, n0 + np.arange(H) * res)
    z = (8 * np.sin(E / 170 + 0.7) * np.cos(N / 210) + 5 * np.sin((E + N) / 95)
         + 14 * np.exp(-((E - 150) ** 2 + (N - 330) ** 2) / 2 / 160 ** 2)
         - 10 * np.exp(-((E + 120) ** 2 + (N - 180) ** 2) / 2 / 110 ** 2)
         + 0.012 * N + 60)
    z += ndimage.gaussian_filter(rng.normal(0, 1.6, z.shape), 6)
    feats, holes = [], []
    course_poly = Polygon([(-450, -300), (330, -300), (330, 510), (-450, 510)])
    feats.append(Feature(CLS_ROUGH, _ring(course_poly), [], {"leisure": "golf_course"}))
    play = []
    for num, par, path, fstart in HOLES:
        path = np.array(path, float)
        line = LineString(path)
        L = line.length
        pin = path[-1]
        tee = path[0]
        # tee box
        d = (path[1] - path[0]) / np.linalg.norm(path[1] - path[0])
        nrm = np.array([-d[1], d[0]])
        tb = [tee - d * 9 - nrm * 6, tee + d * 9 - nrm * 6, tee + d * 9 + nrm * 6, tee - d * 9 + nrm * 6]
        feats.append(Feature(CLS_TEE, np.vstack([tb, tb[:1]]), [], {"golf": "tee"}))
        # green
        dg = (path[-1] - path[-2]) / np.linalg.norm(path[-1] - path[-2])
        green = _blob(pin[0] + dg[0] * 2, pin[1] + dg[1] * 2, 17, 13, np.arctan2(dg[1], dg[0]), seed=num)
        feats.append(Feature(CLS_GREEN, green, [], {"golf": "green"}))
        # flatten-ish green surface + raise slightly
        gm = (E - pin[0]) ** 2 / 26 ** 2 + (N - pin[1]) ** 2 / 26 ** 2
        zp = ndimage.map_coordinates(z, [[(pin[1] - n0) / res], [(pin[0] - e0) / res]])[0]
        w = np.exp(-gm * 2)
        z = z * (1 - 0.7 * w) + (zp + 0.6 + 0.012 * (E - pin[0])) * 0.7 * w
        # fairway
        if fstart is not None:
            seg = LineString([line.interpolate(t * L) for t in np.linspace(fstart, 0.93, 30)])
            widths = 15 + 4 * np.sin(np.linspace(0, 6, 30) + num)
            fw = None
            for p, wd in zip(seg.coords, widths):
                c = Point(p).buffer(wd, 10)
                fw = c if fw is None else fw.union(c)
            fw = fw.simplify(0.8)
            feats.append(Feature(CLS_FAIRWAY, _ring(fw), [], {"golf": "fairway"}))
            play.append(fw)
            # fairway bunker
            bp = np.array(line.interpolate(0.62 * L).coords[0]) + nrm * 20 * (1 if num % 2 else -1)
            feats.append(Feature(CLS_BUNKER, _blob(bp[0], bp[1], 11, 6, rng.uniform(0, 3), seed=num + 10), [], {"golf": "bunker"}))
        # greenside bunkers
        for sgn in (1, -1):
            if rng.random() < 0.8:
                bp = pin + nrm * 21 * sgn - dg * 4
                feats.append(Feature(CLS_BUNKER, _blob(bp[0], bp[1], 7, 4.5, np.arctan2(dg[1], dg[0]), seed=num * 3 + sgn), [], {"golf": "bunker"}))
        play.append(Polygon(green))
        holes.append(Hole(num, par, path, tee, pin, green))
    # pond between hole 1 and 2
    pond = _blob(-40, -150, 55, 30, 0.4, seed=4)
    feats.append(Feature(CLS_WATER, pond, [], {"natural": "water"}))
    # creek in front of the 4th... use a lateral pond by hole 3
    feats.append(Feature(CLS_WATER, _blob(70, 340, 30, 50, 0.2, seed=8), [], {"golf": "lateral_water_hazard"}))
    # woods
    for i, (cx, cy, rx, ry) in enumerate([(-200, -270, 160, 30), (-420, 100, 40, 260), (-120, 220, 90, 70),
                                          (290, 300, 40, 160), (60, 160, 60, 40), (100, 480, 200, 35),
                                          (-180, 40, 50, 60)]):
        feats.append(Feature(CLS_WOOD, _blob(cx, cy, rx, ry, 0.0, 0.18, seed=20 + i, n=40), [], {"natural": "wood"}))
    # cart path + clubhouse
    cp = LineString([(-380, -260), (-300, -250), (-200, -190), (-80, -80), (20, -60), (120, 20), (230, 90)]).buffer(1.3, cap_style=2)
    feats.append(Feature(CLS_PATH, _ring(cp), [], {"golf": "cartpath"}))
    feats.append(Feature(CLS_BUILDING, np.array([(-430, -290), (-395, -290), (-395, -265), (-430, -265), (-430, -290)], float),
                         [], {"building": "yes", "building:levels": "2"}))
    dem = DEM(e0, n0, res, z)
    course = Course("Demo Links (synthetic)", LocalFrame(40.0, -75.0), extent, dem, feats, holes)
    course.imagery = _fake_imagery(course)
    course.attribution = ["Synthetic demo course"]
    return course


def _fake_imagery(course, res=0.6):
    """Paint a pseudo-aerial photo from the feature polygons (for the demo)."""
    from PIL import Image, ImageDraw, ImageFilter
    e0, n0, e1, n1 = course.extent
    W, H = int((e1 - e0) / res), int((n1 - n0) / res)
    img = Image.new("RGB", (W, H), (88, 112, 62))
    dr = ImageDraw.Draw(img)
    col = {CLS_ROUGH: (92, 128, 60), CLS_WOOD: (46, 70, 38), CLS_FAIRWAY: (118, 160, 70), CLS_TEE: (120, 165, 75),
           CLS_GREEN: (110, 170, 80), CLS_BUNKER: (222, 206, 160), CLS_WATER: (48, 82, 96), CLS_PATH: (170, 168, 160),
           CLS_BUILDING: (150, 120, 110)}
    order = [CLS_ROUGH, CLS_WOOD, CLS_FAIRWAY, CLS_TEE, CLS_GREEN, CLS_BUNKER, CLS_WATER, CLS_PATH, CLS_BUILDING]
    for c in order:
        for f in course.features:
            if f.cls == c:
                pts = [((x - e0) / res, (n1 - y) / res) for x, y in f.ring]
                dr.polygon(pts, fill=col[c])
    a = np.asarray(img).astype(np.float32)
    rng = np.random.default_rng(1)
    noise = ndimage.gaussian_filter(rng.normal(0, 1, (H, W)), 2) * 14 + ndimage.gaussian_filter(rng.normal(0, 1, (H, W)), 12) * 30
    a = np.clip(a + noise[..., None] * np.array([0.6, 0.8, 0.4]), 0, 255).astype(np.uint8)
    img = Image.fromarray(a).filter(ImageFilter.GaussianBlur(0.7))
    return Imagery(np.asarray(img), e0, e1, n0, n1, "synthetic")


ROUND = [
    # hole, club, speed, vla, hla, backspin, sidespin, carry, total, (putt only: total yds)
    (1, "DR", 152, 12.1, 1.8, 2650, 420, 241, 262),
    (1, "6i", 121, 15.5, -1.2, 5800, -350, 163, 169),
    (1, "PT", 7.4, 1.5, 0.4, 0, 0, None, 4.9),
    (1, "PT", 3.0, 1.0, 0.0, 0, 0, None, 1.5),
    (2, "7i", 116, 17.2, 2.4, 6400, 610, 157, 163),
    (2, "SW", 52, 31.0, -0.8, 6200, -150, 21, 26),
    (2, "PT", 4.6, 1.2, 0.0, 0, 0, None, 3.2),
    (3, "DR", 156, 11.0, -2.1, 2480, -380, 252, 278),
    (3, "3W", 141, 12.9, 0.5, 3300, 900, 214, 231),
    (3, "PW", 94, 27.0, 0.6, 8700, 120, 99, 101),
    (3, "PT", 6.8, 1.4, 1.0, 0, 0, None, 7.2),
    (3, "PT", 2.4, 1.0, 0.0, 0, 0, None, 0.9),
    (4, "DR", 149, 13.0, -0.6, 2900, 650, 233, 251),
    (4, "6i", 120, 15.8, -0.5, 5600, -220, 166, 172),
    (4, "GW", 68, 29.0, 0.4, 7600, 90, 24, 28),
    (4, "PT", 5.1, 1.2, 0.3, 0, 0, None, 3.8),
]


def write_round_csv(path):
    path = Path(path)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Hole", "Club", "Ball Speed (mph)", "VLA", "HLA", "Back Spin", "Side Spin", "Carry", "Total"])
        for r in ROUND:
            w.writerow(["" if v is None else v for v in r])
    return path
