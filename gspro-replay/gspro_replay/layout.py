"""Place each shot on the course and build the replay timeline."""
from __future__ import annotations

import math

import numpy as np

from .geo import YD, point_along, polyline_length, project_on_polyline
from .model import CLASS_NAMES, CLS_BUNKER, CLS_FAIRWAY, CLS_GREEN, CLS_WATER
from .physics import CLUB_DEFAULTS, carry_of, simulate
from .shots import Shot

FPS = 30.0
LIE = {CLS_GREEN: "Green", CLS_FAIRWAY: "Fairway", CLS_BUNKER: "Bunker", CLS_WATER: "Water"}


def _unit(v):
    n = np.linalg.norm(v)
    return v / n if n > 1e-9 else np.array([0.0, 1.0])


def _rot(v, deg_right):
    a = -math.radians(deg_right)  # clockwise from above
    c, s = math.cos(a), math.sin(a)
    return np.array([c * v[0] - s * v[1], s * v[0] + c * v[1]])


def _roll_path(start, direction, dist, ground, decel, t0, holed_at=None):
    """Ball rolling along the ground with constant deceleration."""
    dist = max(dist, 0.0)
    if dist < 0.05:
        return []
    # natural decel, but keep replays snappy: clamp roll time to [0.6, 5.5] s
    T = min(max(math.sqrt(2 * dist / decel), 0.6), 5.5)
    decel = 2 * dist / (T * T)
    v0 = decel * T
    n = max(2, int(T * FPS))
    out = []
    for k in range(1, n + 1):
        t = T * k / n
        s = v0 * t - 0.5 * decel * t * t
        p = start + direction * s
        out.append([t0 + t, p[0], float(ground(p[0], p[1])[0]), p[1]])
    if holed_at is not None:
        last = out[-1]
        out.append([last[0] + 0.25, last[1], last[2] - 0.12, last[3]])
    return out


class Placer:
    def __init__(self, terrain, auto_finish=True):
        self.T = terrain
        self.auto_finish = auto_finish
        self.ground = terrain.height

    def lie(self, p):
        c = self.T.surface(p[0], p[1])
        return LIE.get(c, "Rough" if CLASS_NAMES[c] in ("rough", "out", "wood", "path") else CLASS_NAMES[c].title())

    def place_hole(self, hole, shots, pins_override=None):
        pin = np.asarray(pins_override if pins_override is not None else hole.pin, float)
        pos = np.asarray(hole.tee, float)
        path = hole.path
        out = []
        shots = list(shots)
        k = -1
        prev_stroke = 0
        while k + 1 < len(shots):
            k += 1
            s = shots[k]
            final = k == len(shots) - 1
            # GSPro only exports shots the launch monitor measured. If we can't tell how the
            # hole finished (no stroke numbers), add an untracked finish; layout below decides
            # whether that is a putt (on/near the green) or a pitch (off the green).
            if final and self.auto_finish and not (s.is_putt or s.auto) and not s.extra.get("holed"):
                shots.append(Shot(auto=True, extra={"unrecorded": True, "known": False}))
                final = False
            last = final
            nxt = shots[k + 1] if not last else None
            to_pin = float(np.linalg.norm(pin - pos))
            # where the next shot says we should be (radial distance to the pin)
            target_r = nxt.dist_to_pin * YD if (nxt is not None and nxt.dist_to_pin) else None
            start = pos.copy()
            lie_before = self.lie(start)
            stroke = s.stroke or (prev_stroke + 1)
            prev_stroke = stroke
            untracked = s.auto
            known = s.extra.get("known", False)
            surf = self.T.surface(*pos)
            on_green = (surf == CLS_GREEN and to_pin < 45) or (to_pin < 12 and surf not in (CLS_BUNKER, CLS_WATER))
            remaining = len(shots) - k - 1

            if untracked and not on_green:
                # an untracked approach / bunker shot: a generic pitch onto the green
                if not known and last:
                    shots.append(Shot(auto=True, extra={"unrecorded": True, "known": False}))
                    last, remaining = False, 1
                if last:
                    target = pin.copy()
                else:
                    leave = 2.5 if remaining == 1 else 6.0
                    target = pin + _rot(_unit(pos - pin), 25) * min(leave, to_pin * 0.3)
                dist_yd = float(np.linalg.norm(target - pos)) / YD
                vla, spin, carry_f = (16, 5000, 0.9) if dist_yd > 150 else (24, 6500, 0.88) if dist_yd > 60 else (34, 7500, 0.8)
                s = Shot(club="", auto=True, ball_speed=24 + 0.5 * dist_yd, vla=vla, hla=0, back_spin=spin,
                         side_spin=0, carry=dist_yd * carry_f, total=dist_yd,
                         peak_height=float(np.clip(0.11 * dist_yd, 2.5, 30)),
                         extra={**s.extra, "unrecorded": True, "aim": target, "target": target})

            if s.is_putt or (untracked and on_green):
                d = _unit(pin - pos)
                if s.hla is not None and not last:
                    d = _rot(d, s.hla)
                if untracked and not last:
                    leave = max(0.45, 0.1 * to_pin) if remaining == 1 else max(1.5, 0.25 * to_pin)
                    d = _rot(d, 1.5)
                    dist = max(0.1, to_pin - leave)
                elif untracked and not known and to_pin > 2.5:
                    # unknown count: lag it close, then hole the next one
                    shots.append(Shot(auto=True, extra={"unrecorded": True, "known": False}))
                    last = False
                    d = _rot(d, 1.2)
                    dist = to_pin - max(0.5, 0.06 * to_pin)
                elif last:
                    dist = to_pin
                elif s.total:
                    dist = s.total * YD
                elif s.ball_speed:
                    dist = (s.ball_speed * 0.44704) ** 2 / (2 * 0.65)
                else:
                    dist = to_pin * 0.92
                if target_r is not None and not last:
                    short, long_ = max(0.1, to_pin - target_r), to_pin + target_r
                    dist = long_ if (s.total and abs(long_ - dist) < abs(short - dist)) else short
                end = pos + d * dist
                roll = _roll_path(pos, d, dist, self.ground, 0.65, 0.0, holed_at=pin if last else None)
                pts = [[0.0, pos[0], float(self.ground(*pos)[0]), pos[1]]] + roll
                rec = dict(kind="putt", launch_t=0.0, land_t=0.0, carry_m=0.0)
                pos = pin.copy() if last else end
            else:
                fam = s.family
                dsp, dvla, dspin = CLUB_DEFAULTS.get(fam, CLUB_DEFAULTS["iron"])
                speed = s.ball_speed or dsp
                vla = s.vla if s.vla is not None else dvla
                back = s.back_spin
                side = s.side_spin
                if back is None and s.total_spin is not None:
                    ax = math.radians(s.spin_axis or 0)
                    back, side = s.total_spin * math.cos(ax), s.total_spin * math.sin(ax)
                if back is None:
                    back, side = dspin, 0.0
                if side is None:
                    side = math.tan(math.radians(s.spin_axis or 0)) * back
                ts, ps = simulate(speed, vla, 0.0, back, side)
                tc, cp = carry_of(ts, ps)
                ts, ps = ts[::3], ps[::3]  # ~33 Hz is plenty for playback
                sim_carry = max(cp[0], 1.0)
                carry_m = (s.carry * YD) if s.carry else sim_carry
                kx = carry_m / sim_carry
                ky = kx
                if s.peak_height and ps[:, 1].max() > 0.3:
                    ky = s.peak_height * YD / ps[:, 1].max()
                lat_scale = 1.0
                if s.offline is not None and abs(cp[2]) > 0.5:
                    # offline is total lateral incl. start line; split: remove HLA part
                    hla_off = math.tan(math.radians(s.hla or 0)) * carry_m
                    lat_scale = (s.offline * YD - hla_off) / (cp[2] * kx) if abs(cp[2] * kx) > 0.5 else 1.0
                    lat_scale = float(np.clip(lat_scale, -3, 3))
                exp_total = (s.total * YD) if s.total else carry_m * (1.08 if fam in ("driver", "wood") else 1.04)
                # aim: follow the hole's centreline for layups/doglegs, else the pin
                s0 = project_on_polyline(path, pos)
                L = polyline_length(path)
                if s.extra.get("aim") is not None:
                    aim = np.asarray(s.extra["aim"], float)
                elif exp_total < to_pin - 18 and s0 + exp_total < L - 10:
                    aim = point_along(path, s0 + exp_total)
                else:
                    aim = pin
                d = _rot(_unit(aim - pos), s.hla or 0.0)
                right = np.array([d[1], -d[0]])
                z0 = float(self.ground(*pos)[0])
                pts = []
                land = None
                prev_above = True
                for t, p in zip(ts, ps):
                    q = pos + d * (p[0] * kx) + right * (p[2] * kx * lat_scale)
                    y = z0 + p[1] * ky
                    gy = float(self.ground(q[0], q[1])[0])
                    if t > 0.3 and y <= gy:
                        if prev_above:
                            pts.append([t, q[0], gy, q[1]])
                            land = (t, q)
                        break
                    pts.append([t, q[0], y, q[1]])
                if land is None:
                    t, q = pts[-1][0], np.array([pts[-1][1], pts[-1][3]])
                    land = (t, q)
                tl, ql = land
                # horizontal direction at landing
                if len(pts) > 3:
                    hv = _unit(np.array([pts[-1][1] - pts[-3][1], pts[-1][3] - pts[-3][3]]))
                else:
                    hv = d
                carried = float(np.linalg.norm(ql - pos))
                roll_d = max(0.0, exp_total - carry_m)
                surf = self.T.surface(ql[0], ql[1])
                if surf == CLS_WATER:
                    roll_d = 0.0
                # one small bounce then roll
                if roll_d > 3:
                    hop = min(roll_d * 0.4, 12.0)
                    hh = min(2.5, 0.25 * hop)
                    th = math.sqrt(8 * hh / 9.81)
                    n = max(4, int(th * FPS))
                    for k2 in range(1, n + 1):
                        f = k2 / n
                        q = ql + hv * hop * f
                        pts.append([tl + th * f, q[0], float(self.ground(*q)[0]) + 4 * hh * f * (1 - f), q[1]])
                    ql2 = ql + hv * hop
                    pts += _roll_path(ql2, hv, roll_d - hop, self.ground, 4.5, tl + th)
                else:
                    pts += _roll_path(ql, hv, roll_d, self.ground, 4.5, tl)
                end = np.array([pts[-1][1], pts[-1][3]])
                # reconcile with the next shot's reported distance-to-pin / holed out
                goal = None
                if last:
                    goal = pin
                elif s.extra.get("target") is not None:
                    goal = np.asarray(s.extra["target"], float)
                elif target_r is not None and target_r > 0.3:
                    goal = pin + _unit(end - pin) * target_r
                if goal is not None:
                    corr = goal - end
                    if np.linalg.norm(corr) < max(60, 0.35 * carried) or last or s.extra.get("target") is not None:
                        tend = pts[-1][0]
                        for r in pts:
                            f = (r[0] / tend) ** 1.5 if tend > 0 else 1
                            r[1] += corr[0] * f
                            r[3] += corr[1] * f
                            if r[0] >= tl:
                                r[2] = float(self.ground(r[1], r[3])[0])
                        if last:
                            pts.append([pts[-1][0] + 0.25, pin[0], float(self.ground(*pin)[0]) - 0.12, pin[1]])
                        end = goal
                rec = dict(kind="full", launch_t=0.0, land_t=tl, carry_m=carry_m,
                           apex_m=float(max(p[2] for p in pts) - z0))
                pos = end.copy()
                # water: drop at the last dry spot along the flight line
                if not last and self.T.surface(*pos) == CLS_WATER:
                    for r in reversed(pts):
                        if self.T.surface(r[1], r[3]) != CLS_WATER:
                            pos = np.array([r[1], r[3]]) - hv * 2
                            break
                    rec["penalty"] = True
            end_xy = np.array([pts[-1][1], pts[-1][3]])
            total_m = float(np.linalg.norm(end_xy - start))
            unrec = bool(s.extra.get("unrecorded"))
            if unrec and rec["kind"] == "putt":
                label, fam = "Putter", "putter"
            elif unrec:
                label, fam = "Not recorded", "unrecorded"
            else:
                label, fam = s.label, s.family
            rec.update(stroke=stroke, skipped=s.extra.get("skipped", 0),
                club=label, family=fam, auto=s.auto,
                stats={"total": round(total_m / YD, 1)} if unrec else {k: v for k, v in dict(
                    ball_speed=s.ball_speed, vla=s.vla, hla=s.hla, back_spin=s.back_spin,
                    side_spin=s.side_spin, total_spin=s.total_spin, spin_axis=s.spin_axis,
                    carry=round(rec["carry_m"] / YD, 1) if rec["carry_m"] else None,
                    total=round(s.total, 1) if s.total else round(total_m / YD, 1),
                    peak=s.peak_height).items() if v is not None},
                dist_before=round(to_pin / YD, 1),
                dist_after=0.0 if last else round(float(np.linalg.norm(pin - pos)) / YD, 1),
                lie_before=lie_before, lie_after="Holed" if last else self.lie(pos),
                points=pts, holed=last)
            out.append(rec)
        return out


def build_timeline(holes_out, pace=1.0):
    """Assign absolute times. Returns (events, duration)."""
    t = 0.0
    events = []
    for h in holes_out:
        intro = 5.0 * pace
        events.append(dict(type="intro", hole=h["number"], t0=t, t1=t + intro))
        t += intro
        for i, s in enumerate(h["shots"]):
            aim = (1.4 if s["kind"] == "putt" else 1.8) * pace
            dur = s["points"][-1][0]
            hold = (3.2 if s["holed"] else 1.6) * pace
            s["t0"] = t
            s["t_launch"] = t + aim
            s["t_land"] = t + aim + s["land_t"]
            s["t_stop"] = t + aim + dur
            s["t1"] = t + aim + dur + hold
            t = s["t1"]
        h["t0"] = events[-1]["t0"]
        h["t1"] = t
    return events, t
