import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { Muxer, ArrayBufferTarget, FileSystemWritableFileStreamTarget } from 'mp4-muxer';
import { World } from './world.js';
import { Replay, CLUB_COLORS } from './replay.js';
import { Director } from './director.js';
import { drawHUD } from './hud.js';
import { STYLES, STYLE_ORDER } from './styles.js';

const data = JSON.parse(document.getElementById('scene-data').textContent);
const app = document.getElementById('app');
const params = new URLSearchParams(location.search);
const exportMode = params.has('export');

// ---- renderer / scene ---------------------------------------------------------
const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true, powerPreference: 'high-performance' });
renderer.setPixelRatio(exportMode ? 1 : Math.min(2, devicePixelRatio));
renderer.outputColorSpace = THREE.SRGBColorSpace;
app.appendChild(renderer.domElement);
renderer.domElement.className = 'gl';
const hud = document.createElement('canvas');
hud.className = 'hud';
app.appendChild(hud);
const hctx = hud.getContext('2d');

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(50, 16 / 9, 0.3, 9000);
const world = new World(scene, data);
const replay = new Replay(scene, data, world);
const director = new Director(camera, replay, world);
const fog = world.fog;
const controls = new OrbitControls(camera, renderer.domElement);
controls.enabled = false;
controls.enableDamping = true;

let W = 0, H = 0;
function resize(w = innerWidth, h = innerHeight, pr = renderer.getPixelRatio()) {
  renderer.setPixelRatio(pr);
  renderer.setSize(w, h, !exportMode);
  hud.width = Math.round(w * pr);
  hud.height = Math.round(h * pr);
  hud.style.width = w + 'px';
  hud.style.height = h + 'px';
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  director.setAspect(w / h);
  W = hud.width; H = hud.height;
}

// ---- frame rendering (shared by playback and export) ---------------------------------
let uiVisible = !exportMode;
let showAll = false;
function renderAt(t, ctx = hctx, w = W, h = H) {
  const st = replay.state(t);
  director.apply(st);
  if (controls.enabled) controls.update();
  const map = director.mode === 'map';
  const cam = director.camera;
  scene.fog = map ? null : fog;
  scene.background = map ? world.mapBg : null;
  replay.update(st, cam, showAll, map);
  world.animate(t);
  renderer.render(scene, cam);
  const inset = uiVisible ? (document.querySelector('.bar')?.offsetHeight || 0) * renderer.getPixelRatio() / (h / 1080) : 0;
  drawHUD(ctx, w, h, st, replay, cam, data, { bottomInset: inset, map });
  return st;
}

// ---- export API (used by `gspro-replay export` through headless Chromium) ---------
const comp = document.createElement('canvas');
const cctx = comp.getContext('2d');
function exportFrame(t) {
  renderAt(t, hctx, W, H);
  comp.width = W; comp.height = H;
  cctx.drawImage(renderer.domElement, 0, 0, W, H);
  cctx.drawImage(hud, 0, 0);
  return comp;
}
function ranges(holes) {
  const hs = holes && holes.length ? replay.holes.filter((h) => holes.includes(h.number)) : replay.holes;
  return hs.map((h) => [h.t0, h.t1]);
}
window.replay = {
  ready: world.ready,
  duration: replay.duration,
  holes: replay.holes.map((h) => h.number),
  styles: STYLE_ORDER.filter((k) => world.available(k)),
  ranges,
  setup({ width = 1920, height = 1080, style = 'lowpoly', camera: cam = 'broadcast' } = {}) {
    uiVisible = false;
    document.body.classList.add('exporting');
    resize(width, height, 1);
    world.setStyle(style);
    director.mode = cam;
  },
  frame(t) { exportFrame(t); },
  grab(q = 0.92) { return comp.toDataURL('image/jpeg', q).split(',')[1]; },
};

// ---- interactive UI ----------------------------------------------------------------
let t = 0, playing = false, speed = 1, last = performance.now();

function buildUI() {
  const bar = document.createElement('div');
  bar.className = 'bar';
  bar.innerHTML = `
    <div class="row">
      <button data-a="prev" title="Previous shot (←)">⏮</button>
      <button data-a="play" class="play" title="Play / pause (space)">▶</button>
      <button data-a="next" title="Next shot (→)">⏭</button>
      <div class="track"><input type="range" min="0" max="${replay.duration}" step="0.01" value="0" class="scrub"><div class="ticks"></div></div>
      <span class="time">0:00 / 0:00</span>
    </div>
    <div class="row small">
      <div class="holes"></div>
      <label>Speed <select data-a="speed"><option>0.5</option><option selected>1</option><option>1.5</option><option>2</option><option>4</option></select></label>
      <label>Camera <select data-a="cam"><option value="broadcast">Broadcast</option><option value="follow">Follow</option><option value="overhead">Overhead</option><option value="map">Map (top-down)</option><option value="free">Free (drag)</option></select></label>
      <label>Look <select data-a="style">${STYLE_ORDER.filter((k) => world.available(k)).map((k) => `<option value="${k}" ${k === world.style ? 'selected' : ''}>${STYLES[k].label}</option>`).join('')}</select></label>
      <label class="chk"><input type="checkbox" data-a="all"> All tracers</label>
      <button data-a="export" class="export">Export MP4</button>
    </div>`;
  app.appendChild(bar);
  const ticks = bar.querySelector('.ticks');
  for (const h of replay.holes) {
    const d = document.createElement('div');
    d.className = 'tick';
    d.style.left = (h.t0 / replay.duration * 100) + '%';
    d.title = `Hole ${h.number}`;
    ticks.appendChild(d);
    const b = document.createElement('button');
    b.textContent = h.number;
    b.title = `Hole ${h.number} · par ${h.par} · ${h.strokes}`;
    b.className = 'hole ' + (h.strokes < h.par ? 'under' : h.strokes > h.par ? 'over' : 'even');
    b.onclick = () => seek(h.t0);
    bar.querySelector('.holes').appendChild(b);
  }
  const scrub = bar.querySelector('.scrub');
  scrub.oninput = () => seek(+scrub.value);
  bar.querySelector('[data-a=play]').onclick = toggle;
  bar.querySelector('[data-a=prev]').onclick = () => jumpShot(-1);
  bar.querySelector('[data-a=next]').onclick = () => jumpShot(1);
  bar.querySelector('[data-a=speed]').onchange = (e) => (speed = +e.target.value);
  bar.querySelector('[data-a=cam]').onchange = (e) => setCam(e.target.value);
  bar.querySelector('[data-a=style]').onchange = (e) => { world.setStyle(e.target.value); try { localStorage.setItem('gspro-replay-style', world.style); } catch (err) { /* no storage */ } };
  bar.querySelector('[data-a=all]').onchange = (e) => (showAll = e.target.checked);
  bar.querySelector('[data-a=export]').onclick = openExport;
  addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT' && e.target.type !== 'range') return;
    if (e.code === 'Space') { e.preventDefault(); toggle(); }
    if (e.code === 'ArrowRight') jumpShot(1);
    if (e.code === 'ArrowLeft') jumpShot(-1);
    if (e.key === 'h') { uiVisible = !uiVisible; document.body.classList.toggle('noui', !uiVisible); }
  });
  return { scrub, time: bar.querySelector('.time'), play: bar.querySelector('[data-a=play]') };
}

function setCam(mode) {
  director.mode = mode;
  controls.enabled = mode === 'free';
  if (controls.enabled) controls.target.copy(replay.ball.position);
}
const mmss = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
function seek(v) { t = Math.max(0, Math.min(replay.duration, v)); }
function toggle() { playing = !playing; if (t >= replay.duration) t = 0; }
function jumpShot(dir) {
  const starts = replay.segments.map((s) => s.t0);
  if (dir > 0) seek(starts.find((x) => x > t + 0.05) ?? replay.duration);
  else { const prev = starts.filter((x) => x < t - 0.6); seek(prev.length ? prev.at(-1) : 0); }
}

// ---- in-browser MP4 export (WebCodecs, Chrome/Edge) ---------------------------------------
function openExport() {
  playing = false;
  const dlg = document.createElement('div');
  dlg.className = 'modal';
  const holeOpts = replay.holes.map((h) => `<label class="chk"><input type="checkbox" value="${h.number}" checked> ${h.number}</label>`).join('');
  dlg.innerHTML = `<div class="card">
    <h2>Export MP4</h2>
    <div class="grid">
      <label>Resolution <select name="res"><option value="1280x720">720p</option><option value="1920x1080" selected>1080p</option><option value="2560x1440">1440p</option><option value="3840x2160">4K</option></select></label>
      <label>Frame rate <select name="fps"><option>24</option><option selected>30</option><option>60</option></select></label>
      <label>Speed <select name="speed"><option>1</option><option>1.5</option><option>2</option></select></label>
    </div>
    <div class="hole-pick">${holeOpts}</div>
    <p class="note">Uses the current camera mode and look. Rendering runs faster than real time on most GPUs; keep this tab in front.</p>
    <div class="progress"><div></div></div><p class="status"></p>
    <div class="btns"><button class="cancel">Close</button><button class="go">Render</button></div></div>`;
  document.body.appendChild(dlg);
  let cancel = false;
  dlg.querySelector('.cancel').onclick = () => { cancel = true; dlg.remove(); };
  dlg.querySelector('.go').onclick = async () => {
    const [w, h] = dlg.querySelector('[name=res]').value.split('x').map(Number);
    const fps = +dlg.querySelector('[name=fps]').value;
    const spd = +dlg.querySelector('[name=speed]').value;
    const holes = [...dlg.querySelectorAll('.hole-pick input:checked')].map((i) => +i.value);
    dlg.querySelector('.go').disabled = true;
    const bar = dlg.querySelector('.progress div'), status = dlg.querySelector('.status');
    try {
      await recordMP4({ w, h, fps, spd, holes, onProgress: (p, msg) => { bar.style.width = (p * 100).toFixed(1) + '%'; status.textContent = msg; }, isCancelled: () => cancel });
      status.textContent = 'Done!';
    } catch (e) {
      status.textContent = 'Export failed: ' + e.message + ' — try the command-line exporter (gspro-replay export).';
      console.error(e);
    }
    dlg.querySelector('.go').disabled = false;
  };
}

async function recordMP4({ w, h, fps, spd, holes, onProgress, isCancelled }) {
  if (!('VideoEncoder' in window)) throw new Error('this browser has no WebCodecs (use Chrome or Edge)');
  w -= w % 2; h -= h % 2;
  const codecs = ['avc1.640033', 'avc1.640028', 'avc1.4d0028', 'avc1.42003e'];
  let config = null;
  for (const codec of codecs) {
    const c = { codec, width: w, height: h, bitrate: Math.round(w * h * fps * 0.12), framerate: fps, avc: { format: 'avc' } };
    if ((await VideoEncoder.isConfigSupported(c)).supported) { config = c; break; }
  }
  if (!config) throw new Error('H.264 encoding not supported at this size');
  let target, fileStream = null;
  const name = `${(data.title || 'round').replace(/[^\w-]+/g, '_')}_replay.mp4`;
  if (window.showSaveFilePicker) {
    try {
      const handle = await showSaveFilePicker({ suggestedName: name, types: [{ description: 'MP4 video', accept: { 'video/mp4': ['.mp4'] } }] });
      fileStream = await handle.createWritable();
      target = new FileSystemWritableFileStreamTarget(fileStream);
    } catch (e) { if (e.name === 'AbortError') throw new Error('cancelled'); }
  }
  if (!target) target = new ArrayBufferTarget();
  const muxer = new Muxer({ target, video: { codec: 'avc', width: w, height: h, frameRate: fps }, fastStart: fileStream ? false : 'in-memory', firstTimestampBehavior: 'offset' });
  let encErr = null;
  const enc = new VideoEncoder({ output: (chunk, meta) => muxer.addVideoChunk(chunk, meta), error: (e) => (encErr = e) });
  enc.configure(config);
  const prevPR = renderer.getPixelRatio(), prevUI = uiVisible;
  uiVisible = false;
  document.body.classList.add('exporting');
  resize(w, h, 1);
  // keep the on-screen preview sized to the window
  renderer.domElement.style.width = '100%'; renderer.domElement.style.height = '100%';
  hud.style.width = '100%'; hud.style.height = '100%';
  const rs = ranges(holes);
  const total = rs.reduce((a, [t0, t1]) => a + (t1 - t0), 0) / spd;
  const nFrames = Math.ceil(total * fps);
  let i = 0;
  const t0 = performance.now();
  try {
    for (const [a, b] of rs) {
      for (let tt = a; tt < b; tt += spd / fps) {
        if (isCancelled()) throw new Error('cancelled');
        if (encErr) throw encErr;
        const c = exportFrame(tt);
        const vf = new VideoFrame(c, { timestamp: Math.round(i * 1e6 / fps), duration: Math.round(1e6 / fps) });
        enc.encode(vf, { keyFrame: i % (fps * 2) === 0 });
        vf.close();
        i++;
        if (enc.encodeQueueSize > 6) await new Promise((r) => setTimeout(r, 1));
        if (i % 15 === 0) {
          const el = (performance.now() - t0) / 1000;
          onProgress(i / nFrames, `Frame ${i} / ${nFrames} · ${(i / el).toFixed(0)} fps · ~${mmss((nFrames - i) / (i / el))} left`);
          await new Promise((r) => requestAnimationFrame(r));
        }
      }
    }
    await enc.flush();
    muxer.finalize();
    if (fileStream) await fileStream.close();
    else {
      const blob = new Blob([target.buffer], { type: 'video/mp4' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = name;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 60000);
    }
    onProgress(1, 'Saved');
  } finally {
    try { enc.close(); } catch (e) { /* closed */ }
    uiVisible = prevUI;
    document.body.classList.remove('exporting');
    resize(innerWidth, innerHeight, prevPR);
  }
}

// ---- boot -------------------------------------------------------------------------------
if (exportMode) {
  resize(1920, 1080, 1);
} else {
  resize();
  addEventListener('resize', () => resize());
  try { const saved = params.get('style') || localStorage.getItem('gspro-replay-style'); if (saved) world.setStyle(saved); } catch (err) { /* no storage */ }
  const ui = buildUI();
  const legend = document.createElement('div');
  legend.className = 'legend';
  legend.innerHTML = Object.entries(CLUB_COLORS).map(([k, c]) => `<span><i style="background:${c}"></i>${k}</span>`).join('');
  app.appendChild(legend);
  world.ready.then(() => {
    renderAt(0);
    function loop(now) {
      const dt = Math.min(0.1, (now - last) / 1000);
      last = now;
      if (playing) {
        t += dt * speed;
        if (t >= replay.duration) { t = replay.duration; playing = false; }
      }
      if (!document.body.classList.contains('exporting')) {
        renderAt(t);
        ui.scrub.value = t;
        ui.time.textContent = `${mmss(t)} / ${mmss(replay.duration)}`;
        ui.play.textContent = playing ? '❚❚' : '▶';
      }
      requestAnimationFrame(loop);
    }
    requestAnimationFrame(loop);
    playing = !params.has('paused');
  });
}
