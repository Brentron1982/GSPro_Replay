"""gspro-replay command line.

  build   real course: OSM + lidar/DEM + imagery + your shots -> replay.html
  demo    synthetic course and round (no network needed)
  export  render a replay.html to .mp4 (headless Chromium + ffmpeg)
  record  log shots from GSPro Open Connect while you play
  gui     desktop app
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

STYLES = ["lowpoly", "realistic", "satellite", "photo", "toon", "yardage", "blueprint", "night", "sunset",
          "autumn", "winter", "links"]


def _parse_holes(s):
    if not s:
        return None
    out = set()
    for part in s.split(","):
        if "-" in part:
            a, b = part.split("-")
            out.update(range(int(a), int(b) + 1))
        else:
            out.add(int(part))
    return out


def cmd_build(a):
    from . import elevation, imagery, osm, shots
    from .geo import BBox, LocalFrame
    from .model import Course
    from .scene import build_scene, write_outputs

    # read shots first: GSPro's PlayerShots export names the course and date
    print("• shots ...")
    sc = [int(x) for x in a.scorecard.split(",")] if a.scorecard else None
    sh = shots.load(a.shots, sc, a.start_hole)
    keep = _parse_holes(a.holes)
    if keep:
        sh = {k: v for k, v in sh.items() if k in keep}
    if not a.course and not a.bbox and shots.META.get("course_name"):
        a.course = shots.META["course_name"]
        print(f"  course from file: {a.course}")
    if not a.title and shots.META.get("course_name"):
        date = shots.META.get("round_date", "").split("(")[0].strip()
        a.title = shots.META["course_name"] + (f" · {date}" if date else "")

    print("• locating course ...")
    course_key = None
    if a.bbox:
        bbox = BBox.parse(a.bbox)
        name = a.title or a.course or "Golf course"
    else:
        if not a.course:
            sys.exit("Give --course \"Course name, Town\" or --bbox south,west,north,east")
        if a.near:
            a.course = f"{a.course}, {a.near}"
        name, bbox, otype, oid = osm.find_course(a.course)
        name = a.title or name.split(",")[0]
        course_key = (otype, oid) if otype in ("way", "relation") else None
    bbox = bbox.expand_m(a.margin)
    frame = LocalFrame(*bbox.center)
    e0, n0 = frame.to_local(bbox.south, bbox.west)
    e1, n1 = frame.to_local(bbox.north, bbox.east)
    extent = (float(e0), float(n0), float(e1), float(n1))
    print(f"  area {extent[2] - extent[0]:.0f} x {extent[3] - extent[1]:.0f} m")

    print("• OpenStreetMap features ...")
    data = osm.overpass(bbox)
    feats, holes, osm_trees = osm.parse(data, frame, course_key)
    if not holes:
        sys.exit("No golf=hole ways found in OSM for this area. The course may be unmapped; "
                 "see README 'Courses missing from OSM'.")

    print("• elevation ...")
    lidar = a.lidar if a.lidar else None
    dem, lidar_trees = elevation.get_elevation(a.dem, bbox, frame, extent, a.res, lidar, a.lidar_epsg)

    attrib = ["Map data © OpenStreetMap contributors (ODbL)"]
    attrib.append("Elevation: USGS 3DEP" if (a.dem == "3dep" or lidar) else "Elevation: Mapzen/AWS Terrain Tiles")
    course = Course(name, frame, extent, dem, feats, holes, osm_trees, None, attrib)

    if not a.no_imagery:
        print("• aerial imagery ...")
        try:
            course.imagery = imagery.fetch_imagery(bbox, frame, extent, a.imagery_zoom, a.imagery_url)
        except Exception as e:  # noqa: BLE001
            print(f"  imagery failed ({e}); continuing without it")

    pins = None
    if a.pins:
        raw = json.loads(Path(a.pins).read_text())
        pins = {}
        for k, (lat, lon) in raw.items():
            e, n = frame.to_local(lat, lon)
            pins[int(k)] = np.array([float(e), float(n)])

    scene = build_scene(course, sh, a.detail, pins, a.pace, a.player, a.title,
                        lidar_trees or None, None, a.tree_density, not a.no_auto_putt)
    write_outputs(scene, a.out)
    print("Done. Open replay.html in Chrome/Edge, or run:  gspro-replay export", Path(a.out) / "replay.html")


def cmd_demo(a):
    from . import demo, shots
    from .scene import build_scene, write_outputs
    course = demo.build_course()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    csvp = demo.write_round_csv(out / "demo_round.csv")
    sh = shots.load(csvp)
    scene = build_scene(course, sh, a.detail, pace=a.pace, player=a.player or "Demo Player")
    write_outputs(scene, out)


def cmd_export(a):
    from .export import export
    export(a.replay, a.output, fps=a.fps, width=a.width, height=a.height, speed=a.speed,
           holes=_parse_holes(a.holes), crf=a.crf, preset=a.preset, style=a.style, camera=a.camera)


def cmd_record(a):
    from .recorder import run
    host, _, port = a.gspro.partition(":")
    run(a.listen, host or "127.0.0.1", int(port or 921), a.output)


def cmd_gui(a):
    from .gui import main as gui_main
    gui_main()


def main(argv=None):
    p = argparse.ArgumentParser(prog="gspro-replay", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="build a replay for a real course")
    b.add_argument("--course", help='course name for OSM lookup, e.g. "Bethpage Black, Farmingdale NY"')
    b.add_argument("--near", help='town/state to disambiguate the course name, e.g. "West Lafayette, IN"')
    b.add_argument("--no-auto-putt", action="store_true",
                   help="don't add putts to holes whose last recorded shot isn't a putt")
    b.add_argument("--bbox", help="south,west,north,east (overrides --course lookup)")
    b.add_argument("--shots", required=True, help="CSV / JSON / JSONL shot file")
    b.add_argument("--out", default="replay_out", help="output folder")
    b.add_argument("--scorecard", help="strokes per hole, comma separated (if shots have no Hole column)")
    b.add_argument("--start-hole", type=int, default=1)
    b.add_argument("--holes", help="only these holes, e.g. 1-9 or 1,2,18")
    b.add_argument("--pins", help='JSON {"1": [lat, lon], ...} with GSPro pin positions')
    b.add_argument("--dem", choices=["3dep", "terrarium"], default="3dep", help="elevation source (default 3dep, US)")
    b.add_argument("--lidar", nargs="+", help="LAZ/LAS files, or 'auto' to download USGS 3DEP point clouds")
    b.add_argument("--lidar-epsg", type=int, help="CRS EPSG code if the LAZ has none")
    b.add_argument("--res", type=float, default=1.0, help="elevation grid resolution (m)")
    b.add_argument("--no-imagery", action="store_true")
    b.add_argument("--imagery-zoom", type=int, default=18)
    b.add_argument("--imagery-url", help="custom XYZ tile URL template {z}/{x}/{y}")
    b.add_argument("--margin", type=float, default=70, help="metres of terrain around the course")
    b.add_argument("--detail", type=float, default=1.0, help="mesh spacing multiplier (<1 = more polys)")
    b.add_argument("--tree-density", type=float, default=1.0)
    b.add_argument("--pace", type=float, default=1.0, help="pause length multiplier between shots")
    b.add_argument("--player", help="name shown in the replay")
    b.add_argument("--title", help="course title shown in the replay")
    b.set_defaults(fn=cmd_build)

    d = sub.add_parser("demo", help="synthetic course + round, no downloads")
    d.add_argument("--out", default="demo_out")
    d.add_argument("--detail", type=float, default=1.0)
    d.add_argument("--pace", type=float, default=1.0)
    d.add_argument("--player")
    d.set_defaults(fn=cmd_demo)

    e = sub.add_parser("export", help="render replay.html to MP4")
    e.add_argument("replay", help="path to replay.html")
    e.add_argument("-o", "--output", default="round.mp4")
    e.add_argument("--fps", type=int, default=30)
    e.add_argument("--width", type=int, default=1920)
    e.add_argument("--height", type=int, default=1080)
    e.add_argument("--speed", type=float, default=1.0, help="playback speed multiplier")
    e.add_argument("--holes", help="only these holes, e.g. 1-9")
    e.add_argument("--style", choices=STYLES, default="lowpoly",
                   help="look: " + ", ".join(STYLES))
    e.add_argument("--camera", choices=["broadcast", "follow", "overhead", "map"], default="broadcast",
                   help="broadcast (TV-style), follow, overhead, or map (top-down shot tracker)")
    e.add_argument("--crf", type=int, default=20)
    e.add_argument("--preset", default="veryfast")
    e.set_defaults(fn=cmd_export)

    r = sub.add_parser("record", help="log shots from GSPro Open Connect while you play")
    r.add_argument("--listen", type=int, default=9211, help="port your connector should send to")
    r.add_argument("--gspro", default="127.0.0.1:921", help="GSPro Open Connect host:port")
    r.add_argument("-o", "--output", default="round.jsonl")
    r.set_defaults(fn=cmd_record)

    g = sub.add_parser("gui", help="open the desktop app")
    g.set_defaults(fn=cmd_gui)

    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
