// Timeline model + shot tracers + ball.
import * as THREE from 'three';

export const CLUB_COLORS = {
  driver: '#ff5d5d', wood: '#ff9a3c', hybrid: '#ffd23f', iron: '#3fd0ff', wedge: '#b38cff', putter: '#ffffff', unrecorded: '#a7b0b8',
};

export const YD = 0.9144;

export function scoreName(strokes, par) {
  const d = strokes - par;
  if (strokes === 1) return 'HOLE IN ONE';
  return { '-3': 'ALBATROSS', '-2': 'EAGLE', '-1': 'BIRDIE', 0: 'PAR', 1: 'BOGEY', 2: 'DOUBLE BOGEY', 3: 'TRIPLE BOGEY' }[d] || (d > 0 ? `+${d}` : `${d}`);
}

function sampleAt(pts, tau, out) {
  const n = pts.length;
  if (tau <= pts[0][0]) return out.set(pts[0][1], pts[0][2], pts[0][3]);
  if (tau >= pts[n - 1][0]) return out.set(pts[n - 1][1], pts[n - 1][2], pts[n - 1][3]);
  let lo = 0, hi = n - 1;
  while (hi - lo > 1) { const m = (lo + hi) >> 1; if (pts[m][0] <= tau) lo = m; else hi = m; }
  const a = pts[lo], b = pts[hi], f = (tau - a[0]) / (b[0] - a[0] || 1);
  return out.set(a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f, a[3] + (b[3] - a[3]) * f);
}

function indexAt(pts, tau) {
  let lo = 0, hi = pts.length - 1;
  if (tau >= pts[hi][0]) return hi;
  while (hi - lo > 1) { const m = (lo + hi) >> 1; if (pts[m][0] <= tau) lo = m; else hi = m; }
  return lo;
}

// a tube along a polyline whose visible length can be clipped by segment index
function tracerGeometry(pts, isPutt) {
  const RS = 6;
  const n = pts.length;
  const pos = new Float32Array(n * RS * 3);
  const idx = [];
  const P = pts.map((p) => new THREE.Vector3(p[1], p[2], p[3]));
  const t = new THREE.Vector3(), nrm = new THREE.Vector3(), bin = new THREE.Vector3(), up = new THREE.Vector3(0, 1, 0);
  for (let i = 0; i < n; i++) {
    const a = P[Math.max(0, i - 1)], b = P[Math.min(n - 1, i + 1)];
    t.subVectors(b, a);
    if (t.lengthSq() < 1e-10) t.set(1, 0, 0);
    t.normalize();
    nrm.crossVectors(t, up);
    if (nrm.lengthSq() < 1e-6) nrm.set(1, 0, 0);
    nrm.normalize();
    bin.crossVectors(nrm, t).normalize();
    const d = P[i].distanceTo(P[0]), dEnd = P[i].distanceTo(P[n - 1]);
    const r = isPutt ? 0.03 : (0.035 + 0.17 * Math.min(1, d / 70)) * Math.min(1, 0.25 + dEnd / 30);
    for (let k = 0; k < RS; k++) {
      const a2 = (k / RS) * Math.PI * 2;
      const c = Math.cos(a2) * r, s = Math.sin(a2) * r;
      const o = (i * RS + k) * 3;
      pos[o] = P[i].x + nrm.x * c + bin.x * s;
      pos[o + 1] = P[i].y + nrm.y * c + bin.y * s + (isPutt ? 0.03 : 0);
      pos[o + 2] = P[i].z + nrm.z * c + bin.z * s;
    }
  }
  for (let i = 0; i < n - 1; i++) for (let k = 0; k < RS; k++) {
    const a = i * RS + k, b = i * RS + ((k + 1) % RS), c = (i + 1) * RS + k, d = (i + 1) * RS + ((k + 1) % RS);
    idx.push(a, c, b, b, c, d);
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  g.setIndex(idx);
  return { geo: g, perSeg: RS * 6 };
}

export class Replay {
  constructor(scene, data, world) {
    this.data = data;
    this.world = world;
    this.duration = data.timeline.duration;
    this.holes = data.holes;
    this.shots = [];
    this.segments = [];
    const intros = data.timeline.events.filter((e) => e.type === 'intro');
    this.group = new THREE.Group();
    scene.add(this.group);
    let par = 0, strokes = 0;
    this.holes.forEach((h, hi) => {
      h.intro = intros[hi];
      this.segments.push({ type: 'intro', hole: h, t0: h.intro.t0, t1: h.intro.t1 });
      h.shots.forEach((s, si) => {
        s.hole = h; s.index = si; s.stroke = s.stroke || (si + 1 + h.shots.slice(0, si).filter((x) => x.penalty).length);
        const pts = s.points;
        s.start = new THREE.Vector3(pts[0][1], pts[0][2], pts[0][3]);
        s.end = new THREE.Vector3(pts.at(-1)[1], pts.at(-1)[2], pts.at(-1)[3]);
        s.land = sampleAt(pts, s.land_t, new THREE.Vector3());
        const ref = s.kind === 'putt' ? s.end : s.land;
        s.dir = new THREE.Vector3(ref.x - s.start.x, 0, ref.z - s.start.z);
        if (s.dir.lengthSq() < 0.01) s.dir.set(h.pin[0] - s.start.x, 0, h.pin[2] - s.start.z);
        if (s.dir.lengthSq() < 0.01) s.dir.set(0, 0, -1);
        s.dir.normalize();
        s.flight = s.land_t;
        s.dur = pts.at(-1)[0];
        s.carryM = s.start.clone().setY(0).distanceTo(s.land.clone().setY(0));
        const color = CLUB_COLORS[s.family] || '#fff';
        s.color = color;
        const { geo, perSeg } = tracerGeometry(pts, s.kind === 'putt');
        s.perSeg = perSeg;
        s.mat = new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.92, depthWrite: false });
        s.baseOpacity = s.family === 'unrecorded' ? 0.55 : 1;
        s.mesh = new THREE.Mesh(geo, s.mat);
        s.mesh.frustumCulled = false;
        s.mesh.renderOrder = 2;
        this.group.add(s.mesh);
        // landing / rest marker
        const ring = new THREE.Mesh(new THREE.RingGeometry(0.55, 0.85, 20).rotateX(-Math.PI / 2),
          new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.85, depthWrite: false }));
        ring.position.copy(s.end).y += 0.06;
        ring.visible = false;
        s.ring = ring;
        this.group.add(ring);
        this.shots.push(s);
        this.segments.push({ type: 'shot', hole: h, shot: s, t0: s.t0, t1: s.t1 });
      });
      par += h.par; strokes += h.strokes;
      h.toPar = strokes - par; h.cumStrokes = strokes;
    });
    // ball + shadow
    this.ball = new THREE.Mesh(new THREE.SphereGeometry(0.11, 14, 10), new THREE.MeshBasicMaterial({ color: '#ffffff' }));
    this.ball.renderOrder = 3;
    scene.add(this.ball);
    this.shadow = new THREE.Mesh(new THREE.CircleGeometry(0.16, 16).rotateX(-Math.PI / 2),
      new THREE.MeshBasicMaterial({ color: '#000', transparent: true, opacity: 0.35, depthWrite: false }));
    scene.add(this.shadow);
    this.tmp = new THREE.Vector3();
  }

  segmentAt(t) {
    const S = this.segments;
    let lo = 0, hi = S.length - 1;
    if (t <= S[0].t0) return S[0];
    while (hi - lo > 1) { const m = (lo + hi) >> 1; if (S[m].t0 <= t) lo = m; else hi = m; }
    return S[hi].t0 <= t ? S[hi] : S[lo];
  }

  ballAt(s, tau, out) { return sampleAt(s.points, tau, out); }

  // state of the round at time t
  state(t) {
    const seg = this.segmentAt(t);
    const st = { t, seg, hole: seg.hole, shot: seg.shot || null, phase: seg.type };
    if (seg.type === 'shot') {
      const s = seg.shot;
      st.tau = t - s.t_launch;
      st.phase = st.tau < 0 ? 'aim' : st.tau < s.flight ? 'flight' : st.tau < s.dur ? 'roll' : 'rest';
      st.ball = this.ballAt(s, Math.max(0, st.tau), new THREE.Vector3());
    } else {
      const s0 = seg.hole.shots[0];
      st.ball = s0.start.clone();
    }
    return st;
  }

  update(st, camera, showAll = false, map = false) {
    if (map) {
      for (const s of this.shots) { s.mesh.visible = false; s.ring.visible = false; }
      this.ball.visible = false; this.shadow.visible = false;
      return;
    }
    const cur = st.shot;
    const holeNum = st.hole.number;
    for (const s of this.shots) {
      const sameHole = s.hole.number === holeNum;
      let vis = false, count = 0;
      if (sameHole && cur) {
        if (s.index < cur.index) { vis = true; count = Infinity; }
        else if (s === cur && st.tau > 0) { vis = true; count = (indexAt(s.points, st.tau) + 1) * s.perSeg; }
      } else if (showAll && s.t1 <= st.t) { vis = true; count = Infinity; }
      s.mesh.visible = vis;
      if (vis) s.mesh.geometry.setDrawRange(0, count);
      s.mat.opacity = (s === cur ? 0.95 : sameHole ? 0.6 : 0.35) * s.baseOpacity;
      s.ring.visible = !!(sameHole && cur && (s.index < cur.index - 1 || (s === cur && st.tau >= s.dur)) && s.kind !== 'putt' && !s.holed);
    }
    // ball (hidden once holed)
    const holed = cur && cur.holed && st.tau >= cur.dur;
    this.ball.visible = !holed;
    this.ball.position.copy(st.ball).y += 0.11;
    const d = camera.position.distanceTo(this.ball.position);
    const k = Math.max(1, d / 45);
    this.ball.scale.setScalar(k);
    const gy = this.world.heightAt(st.ball.x, st.ball.z);
    this.shadow.visible = this.ball.visible;
    this.shadow.position.set(st.ball.x, gy + 0.04, st.ball.z);
    const air = Math.max(0, st.ball.y - gy);
    this.shadow.scale.setScalar(k * (1 + air * 0.01));
    this.shadow.material.opacity = 0.35 * Math.max(0.15, 1 - air / 40);
  }
}
