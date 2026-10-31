// Deterministic camera director: camera pose is a pure function of time,
// so interactive playback, scrubbing and MP4 export all look identical.
import * as THREE from 'three';

const smooth = (a, b, x) => { const t = Math.min(1, Math.max(0, (x - a) / (b - a))); return t * t * (3 - 2 * t); };
const V = () => new THREE.Vector3();

function pathPoint(path, f, out) {
  // f in [0,1] by arc length over hole.path ([x,y,z] list)
  let L = 0;
  const seg = [];
  for (let i = 0; i < path.length - 1; i++) {
    const a = path[i], b = path[i + 1];
    const l = Math.hypot(b[0] - a[0], b[2] - a[2]);
    seg.push(l); L += l;
  }
  let d = Math.min(Math.max(f, 0), 1) * L;
  for (let i = 0; i < seg.length; i++) {
    if (d <= seg[i] || i === seg.length - 1) {
      const a = path[i], b = path[i + 1], u = seg[i] ? Math.min(1, d / seg[i]) : 0;
      return out.set(a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u, a[2] + (b[2] - a[2]) * u);
    }
    d -= seg[i];
  }
  return out.set(...path.at(-1));
}

export class Director {
  constructor(camera, replay, world) {
    this.cam = camera;
    this.replay = replay;
    this.world = world;
    this.mode = 'broadcast';
    this._p = V(); this._l = V(); this._a = V(); this._b = V(); this._c = V();
    this.ortho = new THREE.OrthographicCamera(-100, 100, 100, -100, 1, 4000);
    this.aspect = 16 / 9;
    this.frames = new Map();
  }

  get camera() { return this.mode === 'map' ? this.ortho : this.cam; }
  setAspect(a) { this.aspect = a; this.frames.clear(); }

  // ---- top-down map camera: tee on the left, green on the right ----------------
  _orient(h) {
    const dir = V().set(h.pin[0] - h.tee[0], 0, h.pin[2] - h.tee[2]);
    if (dir.lengthSq() < 1) dir.set(1, 0, 0);
    dir.normalize();
    const up = V().crossVectors(new THREE.Vector3(0, 1, 0), dir); // screen up
    return { dir, up };
  }

  _fit(h, pts, minHalf, padFrac, leftExtra) {
    const { dir, up } = this._orient(h);
    let u0 = Infinity, u1 = -Infinity, v0 = Infinity, v1 = -Infinity, ymax = -Infinity;
    for (const p of pts) {
      const u = p[0] * dir.x + p[2] * dir.z, v = p[0] * up.x + p[2] * up.z;
      u0 = Math.min(u0, u); u1 = Math.max(u1, u); v0 = Math.min(v0, v); v1 = Math.max(v1, v);
      ymax = Math.max(ymax, p[1]);
    }
    let hw = Math.max(minHalf, (u1 - u0) / 2 * (1 + padFrac) + 8), hh = Math.max(minHalf, (v1 - v0) / 2 * (1 + padFrac) + 8);
    const a = this.aspect;
    if (hw / hh < a) hw = hh * a; else hh = hw / a;
    // leave room for the HUD panels on the left
    const shift = hw * leftExtra;
    hw *= 1 + leftExtra; hh = hw / a;
    const cu = (u0 + u1) / 2 - shift, cv = (v0 + v1) / 2 + hh * 0.04;
    const center = V().addScaledVector(dir, cu).addScaledVector(up, cv);
    return { center, hw, hh, dir, up, y: ymax };
  }

  holeFrame(h) {
    const key = 'h' + h.number;
    if (!this.frames.has(key)) {
      const pts = [...h.path, h.tee, h.pin];
      for (const s of h.shots) for (let i = 0; i < s.points.length; i += 3) pts.push([s.points[i][1], s.points[i][2], s.points[i][3]]);
      this.frames.set(key, this._fit(h, pts, 40, 0.12, 0.14));
    }
    return this.frames.get(key);
  }

  greenFrame(h, s) {
    const key = 'g' + h.number + ':' + s.index;
    if (!this.frames.has(key)) {
      const pts = [h.pin, [s.start.x, s.start.y, s.start.z]];
      for (const x of h.shots) if (x.kind === 'putt') pts.push([x.start.x, x.start.y, x.start.z]);
      this.frames.set(key, this._fit(h, pts, 9, 0.9, 0.1));
    }
    return this.frames.get(key);
  }

  mapCam(st) {
    const h = st.hole, s = st.shot;
    const A = this.holeFrame(h);
    let F = A, z = 0;
    if (s && s.kind === 'putt') {
      const first = h.shots.find((x) => x.kind === 'putt');
      const t0 = first.t0;
      z = smooth(t0, t0 + 1.2, st.t);
      F = this.greenFrame(h, first);
    }
    const c = V().lerpVectors(A.center, F.center, z);
    const hw = A.hw + (F.hw - A.hw) * z, hh = A.hh + (F.hh - A.hh) * z;
    const o = this.ortho;
    o.left = -hw; o.right = hw; o.top = hh; o.bottom = -hh;
    o.position.set(c.x, A.y + 600, c.z);
    o.up.copy(A.up);
    o.lookAt(c.x, 0, c.z);
    o.near = 1; o.far = A.y + 1200;
    o.updateProjectionMatrix();
    o.updateMatrixWorld();
  }

  clampGround(p, min = 1.2) {
    const g = this.world.heightAt(p.x, p.z) + min;
    if (p.y < g) p.y = g;
    return p;
  }

  apply(st) {
    if (this.mode === 'free') return;
    if (this.mode === 'map') return this.mapCam(st);
    const pos = this._p, look = this._l;
    if (st.phase === 'intro') this.intro(st, pos, look);
    else if (this.mode === 'overhead') this.overhead(st, pos, look);
    else this.shotCam(st, pos, look);
    this.clampGround(pos);
    this.cam.position.copy(pos);
    this.cam.lookAt(look);
  }

  intro(st, pos, look) {
    const h = st.hole, seg = st.seg;
    const u = (st.t - seg.t0) / (seg.t1 - seg.t0);
    const e = smooth(0, 1, u);
    const path = h.path;
    const tee = this._a.set(...h.tee), pin = this._b.set(...h.pin);
    const len = Math.hypot(pin.x - tee.x, pin.z - tee.z);
    const along = pathPoint(path, 0.05 + 0.62 * e, this._c);
    const ahead = pathPoint(path, Math.min(1, 0.45 + 0.55 * e), V());
    const back = V().subVectors(along, ahead).setY(0).normalize();
    const alt = Math.max(45, len * 0.16) * (1.25 - 0.45 * e);
    pos.copy(along).addScaledVector(back, 60).y += alt;
    look.copy(ahead).lerp(pin, e * 0.7);
  }

  overhead(st, pos, look) {
    const h = st.hole;
    const tee = this._a.set(...h.tee), pin = this._b.set(...h.pin);
    const mid = V().addVectors(tee, pin).multiplyScalar(0.5);
    const d = V().subVectors(pin, tee).setY(0);
    const len = d.length();
    d.normalize();
    pos.copy(mid).addScaledVector(d, -len * 0.62);
    pos.y = mid.y + len * 0.9 + 60;
    look.copy(mid).addScaledVector(d, len * 0.08);
    if (st.shot && st.shot.kind === 'putt') {
      // drop in closer for putting
      pos.copy(st.ball).addScaledVector(st.shot.dir, -10).y += 9;
      look.copy(pin);
    }
  }

  shotCam(st, pos, look) {
    const s = st.shot, R = this.replay;
    const dir = s.dir, side = this._c.set(-dir.z, 0, dir.x); // left of the line
    const tau = st.tau;
    if (s.kind === 'putt') {
      const back = 4.2, up = 1.3;
      const lag = R.ballAt(s, Math.max(0, tau - 0.5), V());
      if (tau <= 0) pos.copy(s.start).addScaledVector(dir, -back).y += up;
      else pos.copy(lag).addScaledVector(dir, -back).y += up;
      pos.addScaledVector(side, 0.6);
      if (s.holed) { const u = smooth(s.dur - 0.6, s.dur + 2.2, tau); pos.addScaledVector(dir, -5 * u).addScaledVector(side, 2.5 * u).y += 3.2 * u; }
      const pin = this._b.set(...s.hole.pin);
      look.copy(st.ball).lerp(pin, tau <= 0 ? 0.6 : 0.35);
      return;
    }
    const carry = s.carryM;
    const aimPos = V().copy(s.start).addScaledVector(dir, -7.5).addScaledVector(side, -0.8);
    aimPos.y += 2.1;
    const aimLook = V().copy(s.start).addScaledVector(dir, Math.min(60, carry * 0.5));
    aimLook.y = Math.max(aimLook.y, s.start.y) + 3;
    if (tau <= 0) {
      const u = smooth(s.t0, s.t_launch, st.t);
      pos.copy(aimPos).addScaledVector(dir, 1.5 * u);
      look.copy(aimLook);
      return;
    }
    const longShot = carry > 70 && this.mode === 'broadcast';
    const cut = longShot ? Math.min(2.4, s.flight * 0.45) : Infinity;
    if (tau < cut) {
      // chase: trail behind the ball with a short lag
      const lag = R.ballAt(s, Math.max(0, tau - 0.7), V());
      const chase = V().copy(lag).addScaledVector(dir, -10).addScaledVector(side, -1.2);
      chase.y += 3.2;
      const k = smooth(0, 0.6, tau);
      pos.copy(aimPos).lerp(chase, k);
      look.copy(aimLook).lerp(st.ball, smooth(0, 0.35, tau));
      if (!longShot) look.lerp(s.end, 0.25);
      return;
    }
    // landing cam: off to the side, ahead of the landing area, watching it come in
    const L = s.land;
    const off = Math.min(48, Math.max(20, carry * 0.16));
    const u = smooth(cut, s.dur + 1.5, tau);
    pos.copy(L).addScaledVector(dir, off * 0.55).addScaledVector(side, off * (1 + 0.15 * u));
    pos.y = Math.max(L.y, s.end.y) + 7 + off * 0.12;
    look.copy(st.ball).lerp(L, tau < s.flight ? 0.35 : 0.0);
  }
}
