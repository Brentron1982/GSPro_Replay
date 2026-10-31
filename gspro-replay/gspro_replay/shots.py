"""Import shot data.

Accepted inputs
---------------
* CSV (GSPro practice/session export, launch-monitor exports, or your own sheet).
  Column names are matched loosely ("Ball Speed (mph)", "ballspeed", "Speed" ...).
  Useful columns: Hole, Club, Ball Speed, VLA/Launch Angle, HLA/Launch Direction,
  Back Spin, Side Spin, Spin Axis, Total Spin, Carry, Total, Offline,
  Distance To Pin (before the shot), End Lat/End Lon (if you have positions).
* JSONL written by ``gspro-replay record`` (GSPro Open Connect traffic).
* JSON list of shot objects using the canonical field names below.

If there is no Hole column, pass ``--scorecard 5,4,3,...`` (strokes per hole) and
shots are split in order. Holes that have fewer recorded shots than the
scorecard get "auto putts" (GSPro gimmes / auto-putting) appended.
"""
from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

FIELDS = {
    "hole": ["hole", "holenumber", "holeno", "holenum", "holeid"],
    "stroke": ["stroke", "shot", "shotnumber", "shotno", "strokenumber", "shotnum"],
    "global_shot": ["globalshotnumber", "globalshot", "roundshotnumber"],
    "club": ["club", "clubname", "clubtype", "clubid"],
    "ball_speed": ["ballspeed", "speed", "ballspd", "ballvelocity"],
    "vla": ["vla", "launchangle", "launchanglevla", "verticallaunchangle", "vlaunch", "launchv", "verticallaunch"],
    "hla": ["hla", "launchdirection", "launchdirectionhla", "horizontallaunchangle", "hlaunch", "launchh",
            "horizontallaunch", "azimuth", "launchdir"],
    "back_spin": ["backspin", "backspinrate"],
    "side_spin": ["sidespin", "sidespinrate"],
    "total_spin": ["totalspin", "spin", "spinrate"],
    "spin_axis": ["spinaxis", "axis", "spintilt", "tiltaxis"],
    "carry": ["carry", "carrydistance", "carrydist"],
    "total": ["total", "totaldistance", "totaldist", "distance"],
    "offline": ["offline", "offlinedistance", "side", "lateral", "carryside", "carrylateral", "offlinecarry"],
    "dist_to_pin": ["distancetopin", "distancetotarget", "disttopin", "topin", "distancetohole", "disttotarget",
                    "remaining", "yardstopin"],
    "end_lat": ["endlat", "landinglat", "restlat", "lat2", "endlatitude"],
    "end_lon": ["endlon", "endlng", "landinglon", "restlon", "lon2", "endlongitude"],
    "penalty": ["penalty", "penaltystrokes"],
    "peak_height": ["peakheight", "apex", "maxheight", "apexheight", "height"],
    "course_name": ["coursename", "course"],
    "round_date": ["rounddate", "date"],
}
UNIT_SUFFIX = re.compile(r"(mph|kmh|kph|ms|yds|yd|yards|meters|metres|m|rpm|deg|degrees|ft|feet)$")


@dataclass
class Shot:
    hole: Optional[int] = None
    club: str = ""
    ball_speed: Optional[float] = None   # mph
    vla: Optional[float] = None          # deg
    hla: Optional[float] = None          # deg, + = right
    back_spin: Optional[float] = None
    side_spin: Optional[float] = None    # + = curves right
    total_spin: Optional[float] = None
    spin_axis: Optional[float] = None    # + = curves right
    carry: Optional[float] = None        # yards
    total: Optional[float] = None        # yards
    offline: Optional[float] = None      # yards, + right
    dist_to_pin: Optional[float] = None  # yards, before the shot
    end_lat: Optional[float] = None
    end_lon: Optional[float] = None
    penalty: int = 0
    peak_height: Optional[float] = None  # yards
    stroke: Optional[int] = None
    global_shot: Optional[int] = None
    auto: bool = False                   # synthesised (gimme / auto putt)
    extra: dict = field(default_factory=dict)

    @property
    def is_putt(self):
        c = self.club.lower().strip()
        if c in ("pt", "putter", "putt", "pu") or "putt" in c:
            return True
        if not c and self.ball_speed is not None and self.ball_speed < 22 and (self.vla or 0) < 6:
            return True
        return False

    @property
    def code(self):
        """Normalise club codes: 'I9'/'9i'/'9 Iron' -> ('i', 9); 'W3' -> ('w', 3); 'DR' -> ('dr', None)."""
        c = self.club.lower().replace(" ", "").replace("-", "")
        m = re.match(r"^([iwh])(\d+)$", c) or re.match(r"^(\d+)([iwh])$", c)
        if m:
            a, b = m.groups()
            return (a, int(b)) if a.isalpha() else (b, int(a))
        m = re.match(r"^(\d+)(iron|wood|hybrid|rescue)$", c)
        if m:
            return {"iron": "i", "wood": "w", "hybrid": "h", "rescue": "h"}[m.group(2)], int(m.group(1))
        return c, None

    @property
    def family(self):
        if self.extra.get("unrecorded"):
            return "unrecorded"
        if self.is_putt:
            return "putter"
        c, n = self.code
        if c in ("dr", "1w", "driver", "d") or "driver" in c or (c == "w" and n == 1):
            return "driver"
        if c == "w" or "wood" in c:
            return "wood"
        if c == "h" or "hybrid" in c or "rescue" in c:
            return "hybrid"
        if c in ("pw", "gw", "aw", "sw", "lw", "uw") or "wedge" in c or re.match(r"^\d{2}(°|deg)?$", c):
            return "wedge"
        return "iron"

    @property
    def label(self):
        if self.extra.get("unrecorded"):
            return "Not recorded"
        names = {"dr": "Driver", "pt": "Putter", "pw": "P-Wedge", "gw": "G-Wedge", "sw": "S-Wedge",
                 "lw": "L-Wedge", "aw": "A-Wedge", "uw": "U-Wedge"}
        c, n = self.code
        if n is not None:
            return f"{n}-{ {'i': 'Iron', 'w': 'Wood', 'h': 'Hybrid'}[c] }"
        if c in names:
            return names[c]
        return self.club.strip() or ("Putter" if self.is_putt else "Shot")


META = {}  # course_name / round_date found in the file


def _norm(h):
    return re.sub(r"[^a-z0-9]", "", h.lower())


def _num(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s or s in ("-", "--", "N/A", "na", "null", "None"):
        return None
    sign = 1.0
    up = s.upper()
    if re.search(r"\bL\b|^L|L$", up):
        sign = -1.0
    m = re.search(r"-?\d+(?:[.,]\d+)?", s)
    if not m:
        return None
    return sign * float(m.group().replace(",", "."))


def _map_headers(headers):
    mapping, units = {}, {}
    for h in headers:
        n = _norm(h)
        cands = [n]
        m = UNIT_SUFFIX.search(n)
        if m and len(n) > len(m.group()):
            cands.append(n[: -len(m.group())])
        for key, aliases in FIELDS.items():
            if key in mapping:
                continue
            if any(c in aliases for c in cands):
                mapping[key] = h
                units[key] = m.group() if m else ""
                break
    return mapping, units


def read_csv(path):
    text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    lines = text.splitlines()
    # some exports have a title row before the header: find the row with most known columns
    best_i, best_n = 0, -1
    for i, line in enumerate(lines[:15]):
        hdr = next(csv.reader([line]))
        n = len(_map_headers(hdr)[0])
        if n > best_n:
            best_i, best_n = i, n
    rows = list(csv.DictReader(lines[best_i:]))
    if not rows:
        raise SystemExit(f"{path}: no rows")
    mapping, units = _map_headers(rows[0].keys())
    print(f"  columns matched: {', '.join(f'{k}<-{v!r}' for k, v in mapping.items())}")
    shots = []
    for r in rows:
        s = Shot()
        for key, col in mapping.items():
            raw = r.get(col)
            if key == "club":
                s.club = (raw or "").strip()
            elif key in ("course_name", "round_date"):
                if raw:
                    META[key] = raw.strip()
            elif key in ("hole", "penalty"):
                v = _num(raw)
                setattr(s, key, int(abs(v)) if v is not None else (0 if key == "penalty" else None))
            elif key in ("stroke", "global_shot"):
                v = _num(raw)
                setattr(s, key, int(v) if v is not None else None)
            else:
                v = _num(raw)
                if v is not None:
                    u = units.get(key, "")
                    if key == "ball_speed" and u in ("kmh", "kph"):
                        v /= 1.609344
                    elif key == "ball_speed" and u == "ms":
                        v /= 0.44704
                    elif key in ("carry", "total", "offline", "dist_to_pin") and u in ("m", "meters", "metres"):
                        v /= 0.9144
                    elif key in ("carry", "total", "offline", "dist_to_pin") and u in ("ft", "feet"):
                        v /= 3.0
                    elif key == "peak_height" and u in ("ft", "feet"):
                        v /= 3.0
                    elif key == "peak_height" and u in ("m", "meters", "metres"):
                        v /= 0.9144
                setattr(s, key, v)
        if all(getattr(s, k) is None for k in ("ball_speed", "carry", "total", "end_lat")) and not s.club:
            continue
        shots.append(s)
    return shots


def read_jsonl(path):
    shots = []
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if "BallData" not in rec and "shot" in rec:
            rec = {**rec["shot"], "_player": rec.get("player") or {}}
        bd = rec.get("BallData") or {}
        if not bd or not rec.get("ShotDataOptions", {}).get("ContainsBallData", True):
            continue
        pl = rec.get("_player") or {}
        s = Shot(club=str(pl.get("Club") or rec.get("Club") or ""),
                 ball_speed=bd.get("Speed"), vla=bd.get("VLA"), hla=bd.get("HLA"),
                 back_spin=bd.get("BackSpin"), side_spin=bd.get("SideSpin"),
                 total_spin=bd.get("TotalSpin"), spin_axis=bd.get("SpinAxis"),
                 carry=bd.get("CarryDistance") or None, dist_to_pin=pl.get("DistanceToTarget"))
        if rec.get("hole"):
            s.hole = int(rec["hole"])
        shots.append(s)
    return shots


def read_json(path):
    data = json.loads(Path(path).read_text())
    if isinstance(data, dict):
        data = data.get("shots", [])
    keys = Shot.__dataclass_fields__.keys()
    return [Shot(**{k: v for k, v in d.items() if k in keys}) for d in data]


def load(path, scorecard=None, start_hole=1):
    p = Path(path)
    if p.suffix.lower() == ".jsonl":
        shots = read_jsonl(p)
    elif p.suffix.lower() == ".json":
        shots = read_json(p)
    else:
        shots = read_csv(p)
    print(f"  {len(shots)} shots read")
    return group_by_hole(shots, scorecard, start_hole)


def _fill_untracked(holes):
    """GSPro numbers every stroke but only exports the ones the launch monitor
    measured (no putts when the monitor can't putt, misreads, penalty drops).
    Use 'Shot Number' and 'Global Shot Number' to recover the true stroke count:
      * gaps before a recorded shot  -> strokes not recorded (penalty / misread)
      * strokes after the last one   -> untracked finishing strokes (usually putts)
    """
    if not all(s.stroke is not None for v in holes.values() for s in v):
        return
    start = {}
    for h, v in holes.items():
        g = [s.global_shot - s.stroke + 1 for s in v if s.global_shot is not None]
        if g:
            start[h] = min(g)
    nums = sorted(holes)
    for i, h in enumerate(nums):
        v = holes[h]
        prev = 0
        for s in v:
            if s.stroke - prev > 1:
                s.extra["skipped"] = s.stroke - prev - 1
            prev = s.stroke
        total = None
        nxt = nums[i + 1] if i + 1 < len(nums) else None
        if nxt == h + 1 and h in start and nxt in start:
            total = start[nxt] - start[h]
        if total is None or total < prev:
            continue  # unknown: layout falls back to its own estimate
        trailing = total - prev
        if trailing == 0:
            v[-1].extra["holed"] = True
        for k in range(trailing):
            v.append(Shot(club="", auto=True, stroke=prev + k + 1, extra={"unrecorded": True, "known": True}))


def group_by_hole(shots, scorecard=None, start_hole=1):
    if shots and all(s.stroke is not None and s.hole is not None for s in shots):
        shots = sorted(shots, key=lambda s: (s.hole, s.stroke))
    holes = {}
    if any(s.hole is not None for s in shots) and not scorecard:
        cur = None
        for s in shots:
            cur = s.hole if s.hole is not None else cur
            holes.setdefault(cur, []).append(s)
        for v in holes.values():
            if all(x.stroke is not None for x in v):
                v.sort(key=lambda x: x.stroke)  # GSPro exports newest-first
        holes = dict(sorted(holes.items()))
        _fill_untracked(holes)
        return holes

    if scorecard:
        i = 0
        for k, strokes in enumerate(scorecard):
            num = start_hole + k
            hs = []
            while i < len(shots) and len(hs) + sum(x.penalty for x in hs) < strokes:
                hs.append(shots[i]); i += 1
            pen = sum(s.penalty for s in hs)
            while len(hs) + pen < strokes:
                hs.append(Shot(club="PT", auto=True))
            holes[num] = hs
        if i < len(shots):
            print(f"  warning: {len(shots) - i} shots left over after applying scorecard")
        return holes

    # heuristic: a hole ends after the last putt in a run of putts, or when the
    # distance to the pin jumps up (new tee)
    num = start_hole
    cur = []
    for k, s in enumerate(shots):
        if cur:
            prev = cur[-1]
            jump = (s.dist_to_pin is not None and prev.dist_to_pin is not None
                    and s.dist_to_pin > prev.dist_to_pin + 30)
            if (prev.is_putt and not s.is_putt) or jump:
                holes[num] = cur; num += 1; cur = []
        cur.append(s)
    if cur:
        holes[num] = cur
    if len(holes) == 1 and len(shots) > 8:
        raise SystemExit("Could not split shots into holes. Add a 'Hole' column or pass --scorecard 4,5,3,...")
    return holes
