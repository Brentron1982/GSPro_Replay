"""Assemble everything into scene.json and a self-contained replay.html."""
from __future__ import annotations

import base64
import io
import json
from datetime import date
from pathlib import Path

import numpy as np

from .geo import YD
from .layout import Placer, build_timeline
from .mesh import Terrain

VIEWER_DIR = Path(__file__).resolve().parent / "viewer_dist"


def b64(a):
    return base64.b64encode(np.ascontiguousarray(a).tobytes()).decode()


def build_scene(course, shot_holes, detail=1.0, pins=None, pace=1.0, player=None, title=None,
                lidar_trees=None, osm_trees=None, tree_density=1.0, auto_finish=True):
    print("• building low-poly terrain ...")
    T = Terrain(course, detail=detail)
    print(f"  {len(T.P):,} vertices, {len(T.F):,} facets")
    trees = T.make_trees(lidar_trees, osm_trees if osm_trees is not None else course.trees, tree_density)
    print(f"  {len(trees):,} trees")

    e0, n0, e1, n1 = course.extent
    ce, cn = (e0 + e1) / 2, (n0 + n1) / 2
    base = float(np.percentile(T.Z, 1)) - 1.0

    def S(e, h, n):
        return [round(float(e) - ce, 3), round(float(h) - base, 3), round(-(float(n) - cn), 3)]

    pos = np.column_stack([T.P[:, 0] - ce, T.Z - base, -(T.P[:, 1] - cn)]).astype(np.float32)

    # coarse heightmap for camera ground clamping
    hm = 256
    xs = np.linspace(e0, e1, hm)
    ns = np.linspace(n1, n0, hm)
    EE, NN = np.meshgrid(xs, ns)
    H = T.height(EE.ravel(), NN.ravel()).reshape(hm, hm).astype(np.float32) - base

    print("• placing shots ...")
    placer = Placer(T, auto_finish)
    holes_out = []
    by_num = {h.number: h for h in course.holes}
    for num, shots in shot_holes.items():
        if num not in by_num:
            print(f"  ! hole {num} not found on the course map - skipped")
            continue
        h = by_num[num]
        pin_override = (pins or {}).get(num)
        placed = placer.place_hole(h, shots, pin_override)
        pin = pin_override if pin_override is not None else h.pin
        for s in placed:
            s["points"] = [[round(p[0], 3), *S(p[1], p[2], p[3])] for p in s["points"]]
        yards = h.yards or round(float(np.linalg.norm(np.diff(h.path, axis=0), axis=1).sum()) / YD)
        holes_out.append(dict(
            number=num, par=h.par, yards=int(yards),
            tee=S(h.tee[0], T.height(*h.tee)[0], h.tee[1]),
            pin=S(pin[0], T.height(*pin)[0], pin[1]),
            path=[S(p[0], T.height(*p)[0], p[1]) for p in h.path],
            strokes=max(s["stroke"] for s in placed) + (sum(1 for s in placed if s.get("penalty"))
                                                         if all(x.stroke is None for x in shots) else 0),
            shots=placed))
    if not holes_out:
        raise SystemExit("No holes could be matched between your shots and the course map.")
    events, duration = build_timeline(holes_out, pace)

    img = None
    if course.imagery is not None:
        from PIL import Image
        im = course.imagery
        buf = io.BytesIO()
        Image.fromarray(im.img).save(buf, "JPEG", quality=86)
        img = dict(jpg=base64.b64encode(buf.getvalue()).decode(),
                   x0=im.e_min - ce, x1=im.e_max - ce, z0=-(im.n_max - cn), z1=-(im.n_min - cn))

    bld = []
    for b in T.buildings():
        bld.append(dict(ring=[[x - ce, -(y - cn)] for x, y in b["ring"]], base=b["base"] - base, h=b["h"],
                        roof=[[[x - ce, -(y - cn)] for x, y in t] for t in b["roof"]]))

    trees_s = trees.copy()
    if len(trees_s):
        trees_s[:, 0] -= ce
        trees_s[:, 1] -= base
        trees_s[:, 2] = -(trees_s[:, 2] - cn)

    scene = dict(
        version=1,
        title=title or course.name,
        player=player or "",
        date=str(date.today()),
        attribution=list(dict.fromkeys(course.attribution + ([course.imagery.attribution] if course.imagery else []))),
        extent=[e0 - ce, -(n1 - cn), e1 - ce, -(n0 - cn)],
        terrain=dict(positions=b64(pos), indices=b64(T.F.astype(np.uint32)), cls=b64(T.face_cls),
                     rgb=b64(T.face_rgb) if T.face_rgb is not None else None, count=int(len(T.F))),
        heightmap=dict(n=hm, x0=e0 - ce, x1=e1 - ce, z0=-(n1 - cn), z1=-(n0 - cn), data=b64(H)),
        imagery=img,
        trees=b64(trees_s.astype(np.float32)) if len(trees_s) else None,
        buildings=bld,
        holes=holes_out,
        timeline=dict(events=events, duration=duration),
    )
    return scene


def write_outputs(scene, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    js = (VIEWER_DIR / "viewer.js").read_text()
    css = (VIEWER_DIR / "viewer.css").read_text()
    data = json.dumps(scene, separators=(",", ":")).replace("</", "<\\/")
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{scene['title']} – Round Replay</title>
<style>{css}</style></head>
<body><div id="app"></div>
<script id="scene-data" type="application/json">{data}</script>
<script>{js}</script>
</body></html>"""
    p = out_dir / "replay.html"
    p.write_text(html, encoding="utf-8")
    (out_dir / "scene.json").write_text(json.dumps(scene, separators=(",", ":")))
    print(f"• wrote {p} ({p.stat().st_size / 1e6:.1f} MB)")
    return p
