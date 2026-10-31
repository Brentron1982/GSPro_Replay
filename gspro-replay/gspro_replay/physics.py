"""Golf ball flight model (drag + Magnus lift, RK4).

Frame: x = forward along the start line, y = up, z = right.  Units SI.
The result is later calibrated to the carry/offline that GSPro reported, so the
model only needs to produce a realistic *shape* (apex, descent, curve).
"""
from __future__ import annotations

import math

import numpy as np

MPH = 0.44704
RHO = 1.225
MASS = 0.04593
RADIUS = 0.021335
AREA = math.pi * RADIUS ** 2
G = 9.81


def _accel(v, w):
    V = np.linalg.norm(v)
    if V < 1e-6:
        return np.array([0.0, -G, 0.0])
    W = np.linalg.norm(w)
    S = RADIUS * W / V
    cd = 0.235 + 0.17 * min(S, 0.4)
    cl = 0.54 * min(S, 0.5) ** 0.4 if S > 0 else 0.0
    k = 0.5 * RHO * AREA / MASS
    a = -k * cd * V * v
    if W > 0:
        m = np.cross(w, v)
        mn = np.linalg.norm(m)
        if mn > 0:
            a = a + k * cl * V * V * m / mn
    a[1] -= G
    return a


def simulate(ball_speed_mph, vla_deg, hla_deg=0.0, back_spin=3000.0, side_spin=0.0,
             spin_axis_deg=None, total_spin=None, dt=0.01, floor=-80.0):
    """Return (t, xyz) arrays. Flight continues below y=0 down to `floor` so the
    caller can intersect it with sloping terrain."""
    v0 = ball_speed_mph * MPH
    vla, hla = math.radians(vla_deg), math.radians(hla_deg)
    v = v0 * np.array([math.cos(vla) * math.cos(hla), math.sin(vla), math.cos(vla) * math.sin(hla)])
    if total_spin is not None and spin_axis_deg is not None:
        rpm, axis = float(total_spin), math.radians(spin_axis_deg)
    else:
        rpm = math.hypot(back_spin or 0, side_spin or 0)
        axis = math.atan2(side_spin or 0, back_spin or 1)
    wmag = rpm * 2 * math.pi / 60
    # spin axis: backspin about +z (lift up); positive tilt curves the ball right
    w0 = wmag * np.array([0.0, -math.sin(axis), math.cos(axis)])
    p = np.zeros(3)
    ts, ps = [0.0], [p.copy()]
    t = 0.0
    while t < 20:
        w = w0 * math.exp(-t / 25.0)
        k1v = _accel(v, w); k1p = v
        k2v = _accel(v + 0.5 * dt * k1v, w); k2p = v + 0.5 * dt * k1v
        k3v = _accel(v + 0.5 * dt * k2v, w); k3p = v + 0.5 * dt * k2v
        k4v = _accel(v + dt * k3v, w); k4p = v + dt * k3v
        v = v + dt / 6 * (k1v + 2 * k2v + 2 * k3v + k4v)
        p = p + dt / 6 * (k1p + 2 * k2p + 2 * k3p + k4p)
        t += dt
        ts.append(t); ps.append(p.copy())
        if p[1] < floor and v[1] < 0:
            break
    return np.array(ts), np.array(ps)


def carry_of(ts, ps):
    """Carry point (y crosses 0 on the way down)."""
    idx = np.nonzero((ps[1:, 1] < 0) & (ps[:-1, 1] >= 0))[0]
    if len(idx) == 0:
        return ts[-1], ps[-1]
    i = idx[-1]
    a, b = ps[i], ps[i + 1]
    f = a[1] / (a[1] - b[1])
    return ts[i] + f * (ts[i + 1] - ts[i]), a + f * (b - a)


# typical launch numbers per club family (used when a file only has distances)
CLUB_DEFAULTS = {
    "driver": (150, 11.5, 2700), "wood": (138, 12.5, 3500), "hybrid": (128, 14, 4300),
    "iron": (115, 18, 6000), "wedge": (95, 28, 8500), "putter": (6, 2, 0),
}
