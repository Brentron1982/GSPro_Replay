// 2D overlay drawn on a canvas so the exact same graphics end up in the MP4.
import * as THREE from 'three';
import { YD, scoreName } from './replay.js';

const FONT = '"Inter", "Segoe UI", system-ui, -apple-system, Roboto, Helvetica, Arial, sans-serif';
const fade = (t, a, b, c, d) => Math.max(0, Math.min(1, (t - a) / (b - a), (d - t) / (d - c)));

function rr(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

function panel(ctx, x, y, w, h, r, alpha = 0.62) {
  rr(ctx, x, y, w, h, r);
  ctx.fillStyle = `rgba(12,18,24,${alpha})`;
  ctx.fill();
  ctx.strokeStyle = 'rgba(255,255,255,0.08)';
  ctx.lineWidth = 1;
  ctx.stroke();
}

function txt(ctx, s, x, y, size, color = '#fff', weight = 600, align = 'left', base = 'alphabetic') {
  ctx.font = `${weight} ${size}px ${FONT}`;
  ctx.fillStyle = color;
  ctx.textAlign = align;
  ctx.textBaseline = base;
  ctx.fillText(s, x, y);
  return ctx.measureText(s).width;
}

const fmt = (v, d = 0) => (v === undefined || v === null ? '–' : Number(v).toFixed(d));
const toParStr = (n) => (n === 0 ? 'E' : n > 0 ? `+${n}` : `${n}`);

export function drawHUD(ctx, W, H, st, replay, camera, data, opts = {}) {
  ctx.clearRect(0, 0, W, H);
  const k = H / 1080;
  const s = st.shot, h = st.hole;
  const pad = 28 * k;
  ctx.save();
  ctx.shadowColor = 'rgba(0,0,0,0.35)';

  if (opts.map) drawMapOverlay(ctx, W, H, st, replay, camera, k);

  // --- top-left hole panel ---------------------------------------------------
  {
    const x = pad, y = pad, w = 360 * k, hh = 112 * k;
    panel(ctx, x, y, w, hh, 16 * k);
    ctx.beginPath();
    ctx.arc(x + 56 * k, y + hh / 2, 38 * k, 0, Math.PI * 2);
    ctx.fillStyle = '#e8352c';
    ctx.fill();
    txt(ctx, String(h.number), x + 56 * k, y + hh / 2 + 1 * k, 40 * k, '#fff', 800, 'center', 'middle');
    txt(ctx, `PAR ${h.par}  ·  ${h.yards} YDS`, x + 108 * k, y + 44 * k, 22 * k, '#fff', 700);
    let line2 = '';
    if (s) {
      const atRest = st.phase === 'rest';
      if (atRest && s.holed) line2 = `Holed · ${h.strokes} strokes`;
      else if (atRest) line2 = `${fmt(s.dist_after)} yds to pin · ${s.lie_after}`;
      else line2 = `Stroke ${s.stroke} · ${fmt(s.dist_before)} yds to pin`;
    } else line2 = data.title;
    txt(ctx, line2, x + 108 * k, y + 78 * k, 19 * k, 'rgba(255,255,255,0.82)', 500);
  }

  // --- player / score -------------------------------------------------------
  {
    const done = replay.holes.filter((x) => x.t1 <= st.t + 1e-6 || (s && s.holed && st.phase === 'rest' && x === h));
    const last = done.at(-1);
    const label = last ? `${toParStr(last.toPar)}  thru ${done.length}` : 'E  thru 0';
    const x = pad, y = pad + 124 * k, w = 360 * k, hh = 46 * k;
    panel(ctx, x, y, w, hh, 12 * k, 0.5);
    txt(ctx, data.player || 'Player', x + 18 * k, y + 30 * k, 19 * k, '#fff', 600);
    txt(ctx, label, x + w - 18 * k, y + 30 * k, 19 * k, last && last.toPar < 0 ? '#ff6b6b' : '#fff', 700, 'right');
  }

  // --- minimap -----------------------------------------------------------------
  if (!opts.map) drawMinimap(ctx, W - pad - 250 * k, pad, 250 * k, 300 * k, st, replay, k);

  // --- shot card ---------------------------------------------------------------
  if (s && st.phase !== 'intro') {
    const a = Math.min(1, (st.t - s.t0) / 0.35, (s.t1 - st.t) / 0.35 + 0.0001);
    ctx.globalAlpha = Math.max(0, Math.min(1, a));
    const x = pad, w = 620 * k, hh = 132 * k, y = H - pad - hh - (opts.bottomInset || 0) * k;
    panel(ctx, x, y, w, hh, 16 * k);
    ctx.font = `800 ${18 * k}px ${FONT}`;
    const chipW = Math.max(168 * k, ctx.measureText(s.club.toUpperCase()).width + 30 * k);
    rr(ctx, x + 18 * k, y + 18 * k, chipW, 36 * k, 18 * k);
    ctx.fillStyle = s.color;
    ctx.fill();
    txt(ctx, s.club.toUpperCase(), x + 18 * k + chipW / 2, y + 37 * k, 18 * k, '#111', 800, 'center', 'middle');
    const sub = s.family === 'unrecorded' ? `Stroke ${s.stroke} · not measured by your launch monitor`
      : s.auto ? `Stroke ${s.stroke} · putt not tracked`
      : `Stroke ${s.stroke}${s.skipped ? ` · ${s.skipped} stroke${s.skipped > 1 ? 's' : ''} not recorded before this` : ''}${s.penalty ? ' · penalty' : ''}`;
    ctx.font = `500 ${19 * k}px ${FONT}`;
    let subTxt = sub;
    while (ctx.measureText(subTxt).width > w - 52 * k - chipW && subTxt.length > 10) subTxt = subTxt.slice(0, -2);
    if (subTxt !== sub) subTxt = subTxt.trimEnd() + '…';
    txt(ctx, subTxt, x + 34 * k + chipW, y + 43 * k, 19 * k, 'rgba(255,255,255,0.85)', 500);
    const tau = Math.max(0, st.tau);
    const cur = replay.ballAt(s, tau, new THREE.Vector3());
    const horiz = Math.hypot(cur.x - s.start.x, cur.z - s.start.z) / YD;
    const items = [];
    if (s.family === 'unrecorded') {
      items.push(['DISTANCE', st.phase === 'aim' ? '–' : fmt(st.phase === 'rest' ? s.stats.total : horiz, 0), 'yds']);
      items.push(['TO PIN', fmt(s.dist_before, 0), 'yds']);
    } else if (s.kind === 'putt') {
      items.push(['DISTANCE', fmt(st.phase === 'aim' ? 0 : horiz, 1), 'yds']);
      items.push(['FEET', fmt(st.phase === 'aim' ? 0 : horiz * 3, 0), 'ft']);
      if (s.stats.ball_speed) items.push(['BALL SPEED', fmt(s.stats.ball_speed, 1), 'mph']);
      items.push(['TO PIN', fmt(s.dist_before * 3, 0), 'ft']);
    } else {
      const landed = st.phase === 'roll' || st.phase === 'rest';
      items.push(['BALL SPEED', fmt(s.stats.ball_speed, 1), 'mph']);
      items.push(['LAUNCH', fmt(s.stats.vla, 1), '°']);
      items.push(['SPIN', s.stats.back_spin != null ? fmt(s.stats.back_spin) : fmt(s.stats.total_spin), 'rpm']);
      items.push(['CARRY', st.phase === 'aim' ? '–' : fmt(landed ? s.stats.carry : horiz, 0), 'yds']);
      items.push(['TOTAL', st.phase === 'rest' ? fmt(s.stats.total, 0) : st.phase === 'aim' ? '–' : fmt(horiz, 0), 'yds']);
    }
    const cw = (w - 36 * k) / items.length;
    items.forEach(([lab, val, unit], i) => {
      const cx = x + 18 * k + cw * i;
      txt(ctx, lab, cx, y + 84 * k, 13 * k, 'rgba(255,255,255,0.6)', 700);
      const vw = txt(ctx, val, cx, y + 116 * k, 30 * k, '#fff', 700);
      txt(ctx, unit, cx + vw + 4 * k, y + 116 * k, 15 * k, 'rgba(255,255,255,0.6)', 600);
    });
    ctx.globalAlpha = 1;

    // in-world label at the rest position
    if (!opts.map && s.kind !== 'putt' && st.phase === 'rest' && !s.holed) {
      const p = s.end.clone();
      p.y += 3;
      p.project(camera);
      if (p.z < 1 && Math.abs(p.x) < 1.1 && Math.abs(p.y) < 1.1) {
        const sx = (p.x + 1) / 2 * W, sy = (1 - p.y) / 2 * H;
        const label = `${fmt(s.stats.total)} yds`;
        ctx.font = `700 ${20 * k}px ${FONT}`;
        const tw = ctx.measureText(label).width + 24 * k;
        panel(ctx, sx - tw / 2, sy - 44 * k, tw, 34 * k, 17 * k, 0.7);
        txt(ctx, label, sx, sy - 21 * k, 20 * k, s.color, 700, 'center');
      }
    }
  }

  // --- hole intro card ---------------------------------------------------------
  if (st.phase === 'intro') {
    const seg = st.seg;
    const a = fade(st.t, seg.t0, seg.t0 + 0.6, seg.t1 - 0.6, seg.t1);
    ctx.globalAlpha = a;
    const w = 520 * k, hh = 170 * k, x = (W - w) / 2, y = H * 0.62;
    panel(ctx, x, y, w, hh, 20 * k, 0.6);
    txt(ctx, `HOLE ${h.number}`, W / 2, y + 82 * k, 64 * k, '#fff', 800, 'center');
    txt(ctx, `PAR ${h.par}   ·   ${h.yards} YARDS`, W / 2, y + 132 * k, 24 * k, 'rgba(255,255,255,0.85)', 600, 'center');
    if (h === replay.holes[0]) txt(ctx, data.title, W / 2, y - 22 * k, 30 * k, '#fff', 700, 'center');
    ctx.globalAlpha = 1;
  }

  // --- holed banner + scorecard ------------------------------------------------
  if (s && s.holed && st.phase === 'rest') {
    const a = fade(st.t, s.t_stop, s.t_stop + 0.4, s.t1 - 0.4, s.t1 + 0.001);
    ctx.globalAlpha = a;
    const name = scoreName(h.strokes, h.par);
    const col = h.strokes < h.par ? '#ff5d5d' : h.strokes === h.par ? '#ffffff' : '#7fc8ff';
    txt(ctx, name, W / 2, H * 0.36, 96 * k, col, 900, 'center');
    txt(ctx, `${h.strokes} on a par ${h.par}`, W / 2, H * 0.36 + 50 * k, 26 * k, '#fff', 600, 'center');
    drawScorecard(ctx, W, H, replay, h, k);
    ctx.globalAlpha = 1;
  }

  // attribution
  ctx.shadowColor = 'transparent';
  txt(ctx, (data.attribution || []).join('  ·  '), W - 12 * k, H - 10 * k, 12 * k, 'rgba(255,255,255,0.75)', 500, 'right');
  ctx.restore();
}

function drawScorecard(ctx, W, H, replay, curHole, k) {
  const holes = replay.holes;
  const cell = 48 * k;
  const w = cell * (holes.length + 3), hh = cell * 3;
  const x = (W - w) / 2, y = H * 0.36 + 80 * k;
  panel(ctx, x, y, w, hh, 12 * k, 0.72);
  const rows = ['HOLE', 'PAR', 'SCORE'];
  rows.forEach((r, i) => txt(ctx, r, x + cell, y + cell * (i + 0.62), 14 * k, 'rgba(255,255,255,0.7)', 700, 'center'));
  let tp = 0, ts = 0;
  holes.forEach((h, j) => {
    const cx = x + cell * (j + 2.5);
    const done = h.number <= curHole.number && holes.indexOf(h) <= holes.indexOf(curHole);
    txt(ctx, String(h.number), cx, y + cell * 0.62, 18 * k, '#fff', 700, 'center');
    txt(ctx, String(h.par), cx, y + cell * 1.62, 18 * k, 'rgba(255,255,255,0.8)', 600, 'center');
    if (done) {
      tp += h.par; ts += h.strokes;
      const d = h.strokes - h.par;
      const cy = y + cell * 2.5;
      ctx.strokeStyle = d < 0 ? '#ff5d5d' : '#7fc8ff';
      ctx.lineWidth = 2 * k;
      if (d < 0) { ctx.beginPath(); ctx.arc(cx, cy, 16 * k, 0, 7); ctx.stroke(); }
      if (d > 0) ctx.strokeRect(cx - 15 * k, cy - 15 * k, 30 * k, 30 * k);
      if (d > 1) ctx.strokeRect(cx - 19 * k, cy - 19 * k, 38 * k, 38 * k);
      txt(ctx, String(h.strokes), cx, y + cell * 2.62, 20 * k, '#fff', 800, 'center');
    }
  });
  const ex = x + w - cell * 0.5;
  txt(ctx, 'TOT', ex, y + cell * 0.62, 14 * k, 'rgba(255,255,255,0.7)', 700, 'center');
  txt(ctx, String(tp), ex, y + cell * 1.62, 18 * k, 'rgba(255,255,255,0.8)', 600, 'center');
  txt(ctx, `${ts}`, ex, y + cell * 2.62, 20 * k, '#fff', 800, 'center');
}

function drawMinimap(ctx, x, y, w, h, st, replay, k) {
  const hole = st.hole;
  const tee = hole.tee, pin = hole.pin;
  // rotate so tee is at the bottom and pin at the top
  const ang = Math.atan2(pin[0] - tee[0], -(pin[2] - tee[2]));
  const ca = Math.cos(-ang), sa = Math.sin(-ang);
  const rot = (px, pz) => { const dx = px - tee[0], dz = pz - tee[2]; return [dx * ca - dz * sa, dx * sa + dz * ca]; };
  const pts = hole.path.map((p) => rot(p[0], p[2]));
  for (const s of hole.shots) for (let i = 0; i < s.points.length; i += 4) pts.push(rot(s.points[i][1], s.points[i][3]));
  let minx = Infinity, maxx = -Infinity, minz = Infinity, maxz = -Infinity;
  for (const [a, b] of pts) { minx = Math.min(minx, a); maxx = Math.max(maxx, a); minz = Math.min(minz, b); maxz = Math.max(maxz, b); }
  const m = 22 * k;
  const sc = Math.min((w - 2 * m) / Math.max(30, maxx - minx), (h - 2 * m) / Math.max(30, maxz - minz));
  const cx = x + w / 2 - ((minx + maxx) / 2) * sc, cz = y + h / 2 - ((minz + maxz) / 2) * sc;
  const P = (px, pz) => { const [a, b] = rot(px, pz); return [cx + a * sc, cz + b * sc]; };
  panel(ctx, x, y, w, h, 16 * k, 0.5);
  ctx.save();
  rr(ctx, x, y, w, h, 16 * k);
  ctx.clip();
  // corridor
  ctx.lineCap = 'round'; ctx.lineJoin = 'round';
  ctx.strokeStyle = 'rgba(120,190,80,0.45)';
  ctx.lineWidth = 34 * sc * 1.0 + 6 * k;
  ctx.beginPath();
  hole.path.forEach((p, i) => { const [a, b] = P(p[0], p[2]); i ? ctx.lineTo(a, b) : ctx.moveTo(a, b); });
  ctx.stroke();
  const [gx, gz] = P(pin[0], pin[2]);
  ctx.fillStyle = 'rgba(150,220,100,0.9)';
  ctx.beginPath(); ctx.arc(gx, gz, Math.max(7 * k, 15 * sc), 0, 7); ctx.fill();
  // shots so far
  const cur = st.shot;
  for (const s of hole.shots) {
    if (!cur || s.index > cur.index) break;
    const lim = s === cur ? Math.max(0, st.tau) : Infinity;
    ctx.strokeStyle = s.color; ctx.lineWidth = 2.5 * k;
    ctx.beginPath();
    let started = false;
    for (const p of s.points) {
      if (p[0] > lim) break;
      const [a, b] = P(p[1], p[3]);
      started ? ctx.lineTo(a, b) : (ctx.moveTo(a, b), started = true);
    }
    ctx.stroke();
  }
  // pin + ball
  ctx.fillStyle = '#e8352c';
  ctx.fillRect(gx - 1.5 * k, gz - 14 * k, 3 * k, 14 * k);
  ctx.beginPath(); ctx.moveTo(gx + 1.5 * k, gz - 14 * k); ctx.lineTo(gx + 11 * k, gz - 10 * k); ctx.lineTo(gx + 1.5 * k, gz - 6 * k); ctx.fill();
  const [bx, bz] = P(st.ball.x, st.ball.z);
  ctx.fillStyle = '#fff';
  ctx.beginPath(); ctx.arc(bx, bz, 4.5 * k, 0, 7); ctx.fill();
  ctx.strokeStyle = '#000'; ctx.lineWidth = 1; ctx.stroke();
  ctx.restore();
}


// ---------------------------------------------------------------------------
// Top-down map overlay: yardage rings, shot lines, stroke markers, labels.
function drawMapOverlay(ctx, W, H, st, replay, camera, k) {
  const h = st.hole, cur = st.shot;
  const v = new THREE.Vector3();
  const P = (x, y, z) => { v.set(x, y, z).project(camera); return [(v.x + 1) / 2 * W, (1 - v.y) / 2 * H]; };
  const mPerPx = (camera.right - camera.left) / W;
  const pin = P(h.pin[0], h.pin[1], h.pin[2]);
  ctx.save();
  ctx.lineCap = 'round'; ctx.lineJoin = 'round';

  // yardage rings from the pin, labelled where they cross the hole's centre line
  const holeLen = Math.hypot(h.tee[0] - h.pin[0], h.tee[2] - h.pin[2]) / YD;
  ctx.setLineDash([8 * k, 9 * k]);
  for (const yd of [50, 100, 150, 200, 250, 300]) {
    if (yd > holeLen - 15) break;
    const r = yd * YD / mPerPx;
    ctx.strokeStyle = 'rgba(255,255,255,0.55)';
    ctx.lineWidth = 1.6 * k;
    ctx.beginPath(); ctx.arc(pin[0], pin[1], r, 0, Math.PI * 2); ctx.stroke();
    // label on the centre line
    let best = null;
    for (let i = 0; i < h.path.length - 1 && !best; i++) {
      const a = h.path[i], b = h.path[i + 1];
      for (let f = 0; f <= 1; f += 0.02) {
        const x = a[0] + (b[0] - a[0]) * f, z = a[2] + (b[2] - a[2]) * f;
        if (Math.abs(Math.hypot(x - h.pin[0], z - h.pin[2]) / YD - yd) < 3) { best = P(x, a[1], z); break; }
      }
    }
    if (best) {
      ctx.setLineDash([]);
      const lab = String(yd);
      ctx.font = `700 ${15 * k}px ${FONT}`;
      const tw = ctx.measureText(lab).width + 12 * k;
      rr(ctx, best[0] - tw / 2, best[1] - 11 * k, tw, 22 * k, 11 * k);
      ctx.fillStyle = 'rgba(255,255,255,0.85)'; ctx.fill();
      txt(ctx, lab, best[0], best[1] + 1 * k, 15 * k, '#1d2b14', 700, 'center', 'middle');
      ctx.setLineDash([8 * k, 9 * k]);
    }
  }
  ctx.setLineDash([]);

  // tee marker
  const tee = P(h.tee[0], h.tee[1], h.tee[2]);
  ctx.fillStyle = '#ffffff'; ctx.strokeStyle = '#1b1b1b'; ctx.lineWidth = 2 * k;
  rr(ctx, tee[0] - 9 * k, tee[1] - 9 * k, 18 * k, 18 * k, 4 * k); ctx.fill(); ctx.stroke();

  // shots
  const tags = [];
  for (const s of h.shots) {
    if (!cur || s.index > cur.index) break;
    const lim = s === cur ? Math.max(0, st.tau) : Infinity;
    if (s === cur && st.tau < 0) continue;
    const pts = [];
    for (const p of s.points) { if (p[0] > lim) break; pts.push(P(p[1], p[2], p[3])); }
    if (s === cur) { const b = replay.ballAt(s, lim, new THREE.Vector3()); pts.push(P(b.x, b.y, b.z)); }
    if (pts.length < 2) continue;
    const w = (s.kind === 'putt' ? 3 : 5) * k;
    for (const [col, lw] of [['rgba(0,0,0,0.55)', w + 4 * k], [s.color, w]]) {
      ctx.strokeStyle = col; ctx.lineWidth = lw;
      if (s.kind === 'putt') ctx.setLineDash([2 * k, 7 * k]); else if (s.family === 'unrecorded') ctx.setLineDash([10 * k, 8 * k]); else ctx.setLineDash([]);
      ctx.beginPath(); pts.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y))); ctx.stroke();
    }
    ctx.setLineDash([]);
    // landing dot for full shots
    if (s.kind !== 'putt' && (s !== cur || st.tau >= s.flight)) {
      const L = P(s.land.x, s.land.y, s.land.z);
      ctx.fillStyle = s.color; ctx.beginPath(); ctx.arc(L[0], L[1], 4 * k, 0, 7); ctx.fill();
    }
    const done = s !== cur || st.tau >= s.dur;
    if (done && !s.holed && s.kind !== 'putt') tags.push({ at: P(s.end.x, s.end.y, s.end.z), s });
  }
  // stroke number badges at each shot's start
  for (const s of h.shots) {
    if (!cur || s.index > cur.index) break;
    const a = P(s.start.x, s.start.y, s.start.z);
    const r = 11 * k;
    ctx.fillStyle = '#ffffff'; ctx.strokeStyle = s.color; ctx.lineWidth = 3 * k;
    ctx.beginPath(); ctx.arc(a[0], a[1], r, 0, 7); ctx.fill(); ctx.stroke();
    txt(ctx, String(s.stroke), a[0], a[1] + 1 * k, 13 * k, '#111', 800, 'center', 'middle');
  }
  // distance tags at rest positions
  for (const { at, s } of tags) {
    const lab = s.family === 'unrecorded' ? `Not recorded · ${Math.round(s.stats.total)} y` : `${s.club} · ${Math.round(s.stats.total)} y`;
    ctx.font = `700 ${14 * k}px ${FONT}`;
    const tw = ctx.measureText(lab).width + 16 * k;
    const x = at[0] + 14 * k, y = at[1] - 30 * k;
    rr(ctx, x, y, tw, 24 * k, 12 * k);
    ctx.fillStyle = 'rgba(12,18,24,0.78)'; ctx.fill();
    ctx.fillStyle = s.color; ctx.fillRect(x + 8 * k, y + 8 * k, 4 * k, 8 * k);
    txt(ctx, lab, x + 16 * k, y + 12.5 * k, 14 * k, '#fff', 700, 'left', 'middle');
  }

  // flag
  ctx.fillStyle = '#ffffff';
  ctx.beginPath(); ctx.arc(pin[0], pin[1], 5 * k, 0, 7); ctx.fill();
  ctx.fillStyle = '#e8352c';
  ctx.fillRect(pin[0] - 1.5 * k, pin[1] - 26 * k, 3 * k, 26 * k);
  ctx.beginPath(); ctx.moveTo(pin[0] + 1.5 * k, pin[1] - 26 * k); ctx.lineTo(pin[0] + 18 * k, pin[1] - 20 * k); ctx.lineTo(pin[0] + 1.5 * k, pin[1] - 14 * k); ctx.fill();

  // ball: grows with height so you can read the flight
  const holed = cur && cur.holed && st.tau >= cur.dur;
  if (!holed) {
    const b = P(st.ball.x, st.ball.y, st.ball.z);
    const g = replay.world.heightAt(st.ball.x, st.ball.z);
    const air = Math.max(0, st.ball.y - g);
    const sh = P(st.ball.x, g, st.ball.z);
    ctx.fillStyle = 'rgba(0,0,0,0.35)';
    ctx.beginPath(); ctx.arc(sh[0] + air * 0.12 * k, sh[1] + air * 0.12 * k, 6 * k, 0, 7); ctx.fill();
    const r = (6 + Math.min(8, air * 0.25)) * k;
    ctx.fillStyle = '#ffffff'; ctx.strokeStyle = '#111'; ctx.lineWidth = 2 * k;
    ctx.beginPath(); ctx.arc(b[0], b[1], r, 0, 7); ctx.fill(); ctx.stroke();
  }
  ctx.restore();
}
