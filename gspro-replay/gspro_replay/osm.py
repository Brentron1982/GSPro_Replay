"""OpenStreetMap: find the course (Nominatim) and pull golf features (Overpass)."""
from __future__ import annotations

import re
import time
import urllib.parse

import numpy as np
from shapely.geometry import LineString, MultiPolygon, Polygon, Point
from shapely.ops import linemerge, polygonize, unary_union

from . import net
from .geo import BBox, LocalFrame, polygon_centroid
from .model import (CLS_BUILDING, CLS_BUNKER, CLS_FAIRWAY, CLS_GREEN, CLS_PATH, CLS_ROUGH,
                    CLS_TEE, CLS_WATER, CLS_WOOD, Feature, Hole, Tree)

NOMINATIM = "https://nominatim.openstreetmap.org/search"
OVERPASS = ["https://overpass-api.de/api/interpreter",
            "https://overpass.kumi.systems/api/interpreter"]


def _variants(query):
    name, _, near = query.partition(",")
    name, near = name.strip(), near.strip()
    names = [name]
    for a, b in (("Golf Club", "Golf Course"), ("Golf Course", "Golf Club"), ("Country Club", "Golf Club")):
        if a.lower() in name.lower():
            names.append(re.sub(a, b, name, flags=re.I))
    core = re.sub(r"\b(golf|club|course|country|links|the)\b", "", name, flags=re.I).strip(" ,&-")
    if core and core.lower() != name.lower():
        names += [f"{core} Golf Course", f"{core} Golf Club", core]
    out = []
    for n in names:
        if near:
            out.append(f"{n}, {near}")
    out += names
    return list(dict.fromkeys(out))


def find_course(query: str):
    """Return (display_name, BBox, osm_type, osm_id) for a golf course name."""
    tried = []
    for i, q in enumerate(_variants(query)):
        if i:
            time.sleep(1.1)  # Nominatim usage policy: max 1 request/second
        tried.append(q)
        try:
            res = net.fetch_json(NOMINATIM, {"q": q, "format": "jsonv2", "limit": 10, "countrycodes": ""})
        except Exception as e:  # noqa: BLE001
            print(f"  lookup failed for '{q}': {e}")
            continue
        golf = [r for r in res if r.get("type") == "golf_course" or (r.get("category") == "leisure" and "golf" in r.get("type", ""))]
        if golf:
            r = golf[0]
            s, n, w, e = map(float, r["boundingbox"])
            print(f"  course: {r['display_name']}")
            return r["display_name"], BBox(s, w, n, e), r.get("osm_type"), int(r.get("osm_id", 0))
    raise SystemExit(
        "Couldn't find that golf course on OpenStreetMap.\n  Tried: " + " | ".join(tried) +
        "\n  Check the exact name at https://www.openstreetmap.org (search the course), "
        "or use Advanced > Bounding box (south,west,north,east).")


def overpass(bbox: BBox):
    b = bbox.overpass()
    q = f"""[out:json][timeout:120];
(
  nwr["golf"]({b});
  nwr["leisure"="golf_course"]({b});
  nwr["natural"~"^(water|wood|scrub|tree_row|wetland|sand|beach)$"]({b});
  nwr["landuse"~"^(forest|reservoir|basin)$"]({b});
  nwr["water"]({b});
  way["waterway"~"^(stream|river|canal|ditch)$"]({b});
  node["natural"="tree"]({b});
  way["building"]({b});
  way["highway"~"^(path|service|footway|track)$"]["golf_cart"]({b});
);
out body;
>;
out skel qt;"""
    last = None
    for url in OVERPASS:
        try:
            return net.fetch_json(url, data="data=" + urllib.parse.quote(q))
        except Exception as e:  # noqa: BLE001
            last = e
    raise SystemExit(f"Overpass failed: {last}")


def _classify(tags):
    g = tags.get("golf")
    nat = tags.get("natural")
    if g in ("water_hazard", "lateral_water_hazard") or nat in ("water", "wetland") \
            or tags.get("water") or tags.get("landuse") in ("reservoir", "basin"):
        return CLS_WATER
    if g == "green":
        return CLS_GREEN
    if g == "tee":
        return CLS_TEE
    if g == "bunker" or nat in ("sand", "beach"):
        return CLS_BUNKER
    if g == "fairway":
        return CLS_FAIRWAY
    if g in ("rough", "driving_range", "practice"):
        return CLS_ROUGH
    if g in ("cartpath", "path") or tags.get("golf_cart"):
        return CLS_PATH
    if nat in ("wood", "scrub") or tags.get("landuse") == "forest":
        return CLS_WOOD
    if tags.get("building") or g == "clubhouse":
        return CLS_BUILDING
    if tags.get("leisure") == "golf_course":
        return CLS_ROUGH
    return None


def _first_int(s, default=None):
    m = re.search(r"\d+", str(s or ""))
    return int(m.group()) if m else default


def parse(data, frame: LocalFrame, course_osm=None):
    nodes = {}
    ways = {}
    rels = []
    for el in data["elements"]:
        t = el["type"]
        if t == "node":
            nodes[el["id"]] = el
        elif t == "way":
            ways[el["id"]] = el
        elif t == "relation":
            rels.append(el)

    def way_xy(w):
        ids = [i for i in w.get("nodes", []) if i in nodes]
        if len(ids) < 2:
            return None
        lat = [nodes[i]["lat"] for i in ids]
        lon = [nodes[i]["lon"] for i in ids]
        e, n = frame.to_local(lat, lon)
        return np.column_stack([e, n])

    features, holes_raw, pins, trees = [], [], [], []
    course_polys = []
    used_in_rel = set()

    for r in rels:
        tags = r.get("tags", {})
        cls = _classify(tags)
        if cls is None or tags.get("type") not in ("multipolygon", None):
            continue
        outer, inner = [], []
        for m in r.get("members", []):
            if m["type"] != "way" or m["ref"] not in ways:
                continue
            xy = way_xy(ways[m["ref"]])
            if xy is None:
                continue
            (inner if m.get("role") == "inner" else outer).append(LineString(xy))
            if not ways[m["ref"]].get("tags"):
                used_in_rel.add(m["ref"])
        polys = list(polygonize(linemerge(outer))) if outer else []
        holes = list(polygonize(linemerge(inner))) if inner else []
        for p in polys:
            p = p.difference(unary_union(holes)) if holes else p
            for g in (p.geoms if isinstance(p, MultiPolygon) else [p]):
                f = Feature(cls, np.asarray(g.exterior.coords), [np.asarray(i.coords) for i in g.interiors], tags)
                features.append(f)
                if tags.get("leisure") == "golf_course":
                    course_polys.append((g, tags, ("relation", r["id"])))

    for wid, w in ways.items():
        tags = w.get("tags", {})
        if not tags:
            continue
        xy = way_xy(w)
        if xy is None:
            continue
        if tags.get("golf") == "hole":
            holes_raw.append((tags, xy))
            continue
        if tags.get("natural") == "tree_row":
            line = LineString(xy)
            for d in np.arange(0, line.length, 7.0):
                p = line.interpolate(d)
                trees.append(Tree(p.x, p.y, 0.0, 0.0))
            continue
        cls = _classify(tags)
        if cls is None:
            continue
        closed = w["nodes"][0] == w["nodes"][-1] and len(xy) >= 4
        if closed and tags.get("waterway") is None:
            g = Polygon(xy)
            if not g.is_valid:
                g = g.buffer(0)
            for gg in (g.geoms if isinstance(g, MultiPolygon) else [g]):
                if gg.area < 1:
                    continue
                features.append(Feature(cls, np.asarray(gg.exterior.coords), [np.asarray(i.coords) for i in gg.interiors], tags))
                if tags.get("leisure") == "golf_course":
                    course_polys.append((gg, tags, ("way", wid)))
        else:
            # linear features -> thin polygons
            width = {CLS_PATH: 2.6, CLS_WATER: 3.0}.get(cls, 2.0)
            g = LineString(xy).buffer(width / 2, cap_style=2)
            for gg in (g.geoms if isinstance(g, MultiPolygon) else [g]):
                features.append(Feature(cls, np.asarray(gg.exterior.coords), [], tags))

    for nid, nd in nodes.items():
        tags = nd.get("tags") or {}
        if tags.get("golf") == "pin":
            e, n = frame.to_local(nd["lat"], nd["lon"])
            pins.append((np.array([float(e), float(n)]), tags))
        elif tags.get("natural") == "tree":
            e, n = frame.to_local(nd["lat"], nd["lon"])
            h = _first_int(tags.get("height"), 0)
            trees.append(Tree(float(e), float(n), float(h or 0), 0.0))

    # Restrict holes to the matched course if we know it (36-hole facilities)
    target = None
    if course_osm and course_polys:
        for g, tags, key in course_polys:
            if key == course_osm:
                target = g
    if target is None and course_polys:
        # if several courses, prefer the one with most holes inside
        def nh(g):
            return sum(1 for _, xy in holes_raw if g.buffer(30).contains(Point(xy[len(xy) // 2])))
        target = max((c[0] for c in course_polys), key=nh)
        if len(course_polys) > 1:
            print(f"  note: {len(course_polys)} golf courses in area; using the one with most holes "
                  f"({nh(target)}). Narrow with --bbox if this is the wrong one.")

    holes = build_holes(holes_raw, features, pins, target)
    return features, holes, trees


def build_holes(holes_raw, features, pins, course_poly=None):
    tees = [f for f in features if f.cls == CLS_TEE]
    greens = [f for f in features if f.cls == CLS_GREEN]
    tee_cent = [polygon_centroid(f.ring) for f in tees]
    green_polys = [Polygon(f.ring) for f in greens]
    by_num = {}
    for tags, xy in holes_raw:
        num = _first_int(tags.get("ref"))
        if num is None:
            continue
        if course_poly is not None and not course_poly.buffer(40).contains(Point(xy[len(xy) // 2])):
            continue
        if num in by_num:
            continue
        # tee: farthest-back tee box near path start (the tips)
        start = xy[0]
        tee = start
        cands = [c for c in tee_cent if np.linalg.norm(c - start) < 90]
        if cands:
            # choose the tee centroid nearest the start node
            tee = min(cands, key=lambda c: np.linalg.norm(c - start))
        # green containing / nearest the path end
        end = xy[-1]
        gi = None
        best = 1e9
        for i, gp in enumerate(green_polys):
            d = gp.distance(Point(end))
            if d < best:
                best, gi = d, i
        green = greens[gi].ring if gi is not None and best < 60 else None
        pin = end
        if green is not None:
            gp = green_polys[gi]
            inside = [p for p, _ in pins if gp.buffer(2).contains(Point(p))]
            pin = inside[0] if inside else np.array(gp.centroid.coords[0])
        path = np.vstack([tee, xy[1:-1], pin]) if len(xy) > 2 else np.vstack([tee, pin])
        by_num[num] = Hole(number=num, par=_first_int(tags.get("par"), 4), path=path,
                           tee=np.asarray(tee, float), pin=np.asarray(pin, float), green=green,
                           yards=_first_int(tags.get("dist") or tags.get("distance")))
    holes = [by_num[k] for k in sorted(by_num)]
    print(f"  holes found in OSM: {[h.number for h in holes] or 'none'}")
    return holes
