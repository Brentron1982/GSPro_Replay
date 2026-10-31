// Static world: terrain, trees, buildings, flags, sky — restylable at runtime.
import * as THREE from 'three';
import { STYLES, BASE_PALETTE } from './styles.js';

export function b64(str, Type) {
  const bin = atob(str);
  const buf = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
  return new Type(buf.buffer);
}

export const PALETTE = BASE_PALETTE;
const SHADE_SPREAD = [0.13, 0.12, 0.07, 0.05, 0.05, 0.06, 0.08, 0.12, 0.04, 0.04];

function hash(i) {
  let x = (i | 0) * 374761393;
  x = (x ^ (x >>> 13)) * 1274126177;
  return ((x ^ (x >>> 16)) >>> 0) / 4294967295;
}

function toonGradient() {
  const t = new THREE.DataTexture(new Uint8Array([90, 170, 255]), 3, 1, THREE.RedFormat);
  t.minFilter = t.magFilter = THREE.NearestFilter;
  t.needsUpdate = true;
  return t;
}

export class World {
  constructor(scene, data) {
    this.scene = scene;
    this.data = data;
    this.group = new THREE.Group();
    scene.add(this.group);
    this._sky();
    this._lights();
    this._terrain();
    this._outlines();
    this._trees();
    this._buildings();
    this._flags();
    this._heightmap();
    this.cache = {};
    this.setStyle('lowpoly');
  }

  available(name) {
    const s = STYLES[name];
    if (!s) return false;
    if (s.needs === 'rgb') return !!this.data.terrain.rgb;
    if (s.needs === 'imagery') return !!this.data.imagery;
    return true;
  }

  // ------------------------------------------------------------------ sky / light
  _sky() {
    const geo = new THREE.SphereGeometry(6000, 32, 16);
    this.skyU = { top: { value: new THREE.Color() }, mid: { value: new THREE.Color() }, bot: { value: new THREE.Color() } };
    const mat = new THREE.ShaderMaterial({
      side: THREE.BackSide, depthWrite: false, fog: false, uniforms: this.skyU,
      vertexShader: 'varying vec3 vP; void main(){ vP = normalize(position); gl_Position = projectionMatrix*modelViewMatrix*vec4(position,1.0);} ',
      fragmentShader: 'uniform vec3 top; uniform vec3 mid; uniform vec3 bot; varying vec3 vP; void main(){ float h=vP.y; vec3 c = h>0.0 ? mix(mid, top, pow(clamp(h*1.6,0.0,1.0),0.7)) : bot; c = mix(bot, c, smoothstep(-0.02,0.08,h)); gl_FragColor=vec4(c,1.0);\n#include <colorspace_fragment>\n}',
    });
    this.sky = new THREE.Mesh(geo, mat);
    this.sky.renderOrder = -1;
    this.scene.add(this.sky);
    this.fog = this.scene.fog = new THREE.Fog('#d6e6ef', 900, 3200);
    // stars for night
    const n = 1800, sp = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) {
      const u = hash(i * 3 + 1), v = hash(i * 3 + 2) * 0.95 + 0.05;
      const th = u * Math.PI * 2, ph = Math.acos(v);
      sp.set([Math.sin(ph) * Math.cos(th) * 5000, Math.cos(ph) * 5000, Math.sin(ph) * Math.sin(th) * 5000], i * 3);
    }
    const sg = new THREE.BufferGeometry();
    sg.setAttribute('position', new THREE.BufferAttribute(sp, 3));
    this.stars = new THREE.Points(sg, new THREE.PointsMaterial({ color: '#ffffff', size: 1.6, sizeAttenuation: false, fog: false, transparent: true, opacity: 0.85 }));
    this.stars.visible = false;
    this.scene.add(this.stars);
  }

  _lights() {
    this.hemi = new THREE.HemisphereLight('#dcecff', '#4d5b2f', 1.1);
    this.scene.add(this.hemi);
    this.sun = new THREE.DirectionalLight('#fff3dc', 2.9);
    this.sun.position.set(-700, 520, 380);
    this.scene.add(this.sun);
  }

  // ------------------------------------------------------------------ terrain
  _terrain() {
    const t = this.data.terrain;
    const P = (this.P = b64(t.positions, Float32Array));
    const I = (this.I = b64(t.indices, Uint32Array));
    this.C = b64(t.cls, Uint8Array);
    this.RGB = t.rgb ? b64(t.rgb, Uint8Array) : null;
    const n = (this.nF = I.length / 3);
    const pos = new Float32Array(n * 9);
    for (let f = 0; f < n; f++) for (let k = 0; k < 3; k++) {
      const v = I[f * 3 + k];
      pos[f * 9 + k * 3] = P[v * 3]; pos[f * 9 + k * 3 + 1] = P[v * 3 + 1]; pos[f * 9 + k * 3 + 2] = P[v * 3 + 2];
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    geo.computeVertexNormals();
    this.flatN = geo.getAttribute('normal').array.slice();
    // smooth normals from the indexed mesh
    const ig = new THREE.BufferGeometry();
    ig.setAttribute('position', new THREE.BufferAttribute(P, 3));
    ig.setIndex(new THREE.BufferAttribute(I, 1));
    ig.computeVertexNormals();
    const vn = ig.getAttribute('normal').array;
    this.smoothN = new Float32Array(n * 9);
    for (let i = 0; i < n * 3; i++) this.smoothN.set([vn[I[i] * 3], vn[I[i] * 3 + 1], vn[I[i] * 3 + 2]], i * 3);
    ig.dispose();
    geo.setAttribute('color', new THREE.BufferAttribute(new Float32Array(n * 9), 3));
    const im = this.data.imagery;
    if (im) {
      const uv = new Float32Array(n * 6);
      for (let i = 0; i < n * 3; i++) {
        uv[i * 2] = (pos[i * 3] - im.x0) / (im.x1 - im.x0);
        uv[i * 2 + 1] = 1 - (pos[i * 3 + 2] - im.z0) / (im.z1 - im.z0);
      }
      geo.setAttribute('uv', new THREE.BufferAttribute(uv, 2));
      const img = new Image();
      img.src = 'data:image/jpeg;base64,' + im.jpg;
      this.photoTex = new THREE.Texture(img);
      this.photoTex.colorSpace = THREE.SRGBColorSpace;
      this.photoTex.anisotropy = 8;
      this.ready = new Promise((res) => { img.onload = () => { this.photoTex.needsUpdate = true; res(); }; img.onerror = res; });
    } else this.ready = Promise.resolve();
    this.terrain = new THREE.Mesh(geo, new THREE.MeshLambertMaterial({ vertexColors: true }));
    this.group.add(this.terrain);
    // wireframe overlay (blueprint)
    this.wire = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ wireframe: true, transparent: true, depthWrite: false }));
    this.wire.visible = false;
    this.wire.renderOrder = 1;
    this.group.add(this.wire);
  }

  _faceColors(st) {
    const n = this.nF, C = this.C, RGB = this.RGB;
    const pal = st.palette.map((c) => new THREE.Color(c));
    const tint = st.tint ? new THREE.Color(...st.tint) : null;
    const out = new Float32Array(n * 9);
    const tmp = new THREE.Color(), sat = new THREE.Color();
    for (let f = 0; f < n; f++) {
      const c = C[f];
      if (st.color === 'satellite' && RGB) {
        tmp.setRGB(RGB[f * 3] / 255, RGB[f * 3 + 1] / 255, RGB[f * 3 + 2] / 255, THREE.SRGBColorSpace);
        if (c === 6) tmp.lerp(pal[6], 0.35);
        tmp.multiplyScalar(1.12);
      } else {
        tmp.copy(pal[c]).multiplyScalar(1 + (hash(f) - 0.5) * 2 * SHADE_SPREAD[c] * st.jitter);
        if (st.color === 'blend' && RGB) {
          sat.setRGB(RGB[f * 3] / 255, RGB[f * 3 + 1] / 255, RGB[f * 3 + 2] / 255, THREE.SRGBColorSpace).multiplyScalar(1.1);
          tmp.lerp(sat, c === 6 || c === 5 ? 0.25 : 0.5);
        }
      }
      if (tint) tmp.multiply(tint);
      for (let k = 0; k < 3; k++) out.set([tmp.r, tmp.g, tmp.b], f * 9 + k * 3);
    }
    if (st.shading !== 'smooth') return out;
    // average face colours per vertex for soft blending
    const nv = this.P.length / 3, acc = new Float32Array(nv * 4), I = this.I;
    for (let i = 0; i < n * 3; i++) {
      const v = I[i];
      acc[v * 4] += out[i * 3]; acc[v * 4 + 1] += out[i * 3 + 1]; acc[v * 4 + 2] += out[i * 3 + 2]; acc[v * 4 + 3] += 1;
    }
    for (let i = 0; i < n * 3; i++) {
      const v = I[i], w = acc[v * 4 + 3];
      out[i * 3] = acc[v * 4] / w; out[i * 3 + 1] = acc[v * 4 + 1] / w; out[i * 3 + 2] = acc[v * 4 + 2] / w;
    }
    return out;
  }

  _terrainMaterial(st) {
    const key = st.material + (st.color === 'photo' ? ':photo' : '');
    if (this.cache[key]) return this.cache[key];
    let m;
    if (st.color === 'photo') m = new THREE.MeshLambertMaterial({ map: this.photoTex });
    else if (st.material === 'toon') m = new THREE.MeshToonMaterial({ vertexColors: true, gradientMap: toonGradient() });
    else if (st.material === 'blueprint') m = new THREE.MeshBasicMaterial({ color: '#0e2c55', polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 });
    else if (st.material === 'contour') {
      m = new THREE.MeshLambertMaterial({ vertexColors: true });
      m.onBeforeCompile = (sh) => {
        sh.uniforms.uLine = { value: new THREE.Color('#7a6a4a') };
        sh.vertexShader = sh.vertexShader.replace('#include <common>', '#include <common>\nvarying vec3 vWPos;')
          .replace('#include <begin_vertex>', '#include <begin_vertex>\nvWPos = (modelMatrix * vec4(transformed, 1.0)).xyz;');
        sh.fragmentShader = sh.fragmentShader.replace('#include <common>', '#include <common>\nvarying vec3 vWPos;\nuniform vec3 uLine;')
          .replace('#include <color_fragment>', `#include <color_fragment>
            float h1 = vWPos.y; float w1 = fwidth(h1);
            float l1 = 1.0 - min(abs(fract(h1 - 0.5) - 0.5) / max(w1, 1e-4), 1.0);
            float h5 = vWPos.y / 5.0; float w5 = fwidth(h5);
            float l5 = 1.0 - min(abs(fract(h5 - 0.5) - 0.5) / max(w5 * 1.6, 1e-4), 1.0);
            diffuseColor.rgb = mix(diffuseColor.rgb, uLine, clamp(l1 * 0.35 + l5 * 0.7, 0.0, 0.8));`);
      };
    } else m = new THREE.MeshLambertMaterial({ vertexColors: true });
    this.cache[key] = m;
    return m;
  }

  // edges between faces of different surface class (fairway/green/bunker outlines)
  _outlines() {
    const I = this.I, C = this.C, P = this.P;
    const edges = new Map();
    const seg = [];
    for (let f = 0; f < this.nF; f++) for (let k = 0; k < 3; k++) {
      const a = I[f * 3 + k], b = I[f * 3 + ((k + 1) % 3)];
      const key = a < b ? a * 4294967296 + b : b * 4294967296 + a;
      const g = edges.get(key);
      if (g === undefined) edges.set(key, f);
      else if (C[g] !== C[f] && !((C[g] <= 1) && (C[f] <= 1))) {
        seg.push(P[a * 3], P[a * 3 + 1] + 0.08, P[a * 3 + 2], P[b * 3], P[b * 3 + 1] + 0.08, P[b * 3 + 2]);
      }
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(seg, 3));
    this.outline = new THREE.LineSegments(g, new THREE.LineBasicMaterial({ transparent: true }));
    this.outline.visible = false;
    this.group.add(this.outline);
  }

  // ------------------------------------------------------------------ trees
  _trees() {
    this.treeSets = [];
    if (!this.data.trees) return;
    const T = b64(this.data.trees, Float32Array);
    const n = T.length / 7;
    const broad = [], conif = [];
    for (let i = 0; i < n; i++) (T[i * 7 + 5] > 0.5 ? conif : broad).push(i);
    const m = new THREE.Matrix4(), q = new THREE.Quaternion(), s = new THREE.Vector3(), p = new THREE.Vector3();
    const up = new THREE.Vector3(0, 1, 0);
    this.treeMats = {
      low: new THREE.MeshLambertMaterial({ flatShading: true }),
      high: new THREE.MeshLambertMaterial(),
      toon: new THREE.MeshToonMaterial({ gradientMap: toonGradient() }),
      wire: new THREE.MeshBasicMaterial({ wireframe: true }),
    };
    const outlineMat = new THREE.MeshBasicMaterial({ color: '#1d2b14', side: THREE.BackSide });
    const mk = (kind, geos, list, place) => {
      if (!list.length) return;
      const im = new THREE.InstancedMesh(geos.low, this.treeMats.low, list.length);
      list.forEach((i, k) => {
        place(T[i * 7], T[i * 7 + 1], T[i * 7 + 2], T[i * 7 + 3], T[i * 7 + 4], p, s);
        q.setFromAxisAngle(up, T[i * 7 + 6]);
        m.compose(p, q, s);
        im.setMatrixAt(k, m);
        im.setColorAt(k, new THREE.Color());
      });
      im.instanceMatrix.needsUpdate = true;
      // outline hull for the cartoon style, sharing the instance transforms
      const ol = new THREE.InstancedMesh(geos.outline, outlineMat, list.length);
      ol.instanceMatrix = im.instanceMatrix;
      ol.visible = false;
      this.group.add(im, ol);
      this.treeSets.push({ kind, im, ol, geos, list });
    };
    const hull = (g, k) => { const h = g.clone(); h.scale(k, k * 0.97, k); return h; };
    const icoL = new THREE.IcosahedronGeometry(1, 0), icoH = new THREE.IcosahedronGeometry(1, 2);
    const coneL = new THREE.ConeGeometry(1, 1, 7, 1).translate(0, 0.5, 0), coneH = new THREE.ConeGeometry(1, 1, 16, 3).translate(0, 0.5, 0);
    const trL = new THREE.CylinderGeometry(0.6, 1, 1, 5).translate(0, 0.5, 0), trH = new THREE.CylinderGeometry(0.6, 1, 1, 10).translate(0, 0.5, 0);
    mk('broad', { low: icoL, high: icoH, outline: hull(icoL, 1.1) }, broad, (x, y, z, h, r, p, s) => { p.set(x, y + h * 0.6, z); s.set(r, h * 0.42, r); });
    mk('conifer', { low: coneL, high: coneH, outline: hull(coneL, 1.1) }, conif, (x, y, z, h, r, p, s) => { p.set(x, y + h * 0.12, z); s.set(r * 0.9, h * 0.9, r * 0.9); });
    mk('trunk', { low: trL, high: trH, outline: hull(trL, 1.25) }, broad.concat(conif), (x, y, z, h, r, p, s) => { p.set(x, y - 0.3, z); s.set(Math.max(0.18, r * 0.09), h * 0.45, Math.max(0.18, r * 0.09)); });
  }

  _styleTrees(st) {
    const col = new THREE.Color();
    for (const t of this.treeSets) {
      const pal = st.trees[t.kind] || BASE_PALETTE;
      t.list.forEach((i, k) => {
        col.set(pal[Math.floor(hash(i + 7) * pal.length)]).multiplyScalar(st.material === 'blueprint' ? 1 : 0.88 + hash(i) * 0.24);
        t.im.setColorAt(k, col);
      });
      t.im.instanceColor.needsUpdate = true;
      t.im.geometry = st.treeDetail === 'high' ? t.geos.high : t.geos.low;
      t.im.material = st.treeDetail === 'wire' ? this.treeMats.wire : st.material === 'toon' ? this.treeMats.toon
        : st.treeDetail === 'high' ? this.treeMats.high : this.treeMats.low;
      t.ol.visible = !!st.treeOutline;
    }
  }

  // ------------------------------------------------------------------ apply a style
  setStyle(name) {
    if (!this.available(name)) name = 'lowpoly';
    const st = STYLES[name];
    this.style = name;
    const geo = this.terrain.geometry;
    geo.getAttribute('normal').array.set(st.shading === 'smooth' ? this.smoothN : this.flatN);
    geo.getAttribute('normal').needsUpdate = true;
    if (st.color !== 'photo' && st.material !== 'blueprint') {
      const key = 'col:' + name;
      this.cache[key] = this.cache[key] || this._faceColors(st);
      geo.getAttribute('color').array.set(this.cache[key]);
      geo.getAttribute('color').needsUpdate = true;
    }
    this.terrain.material = this._terrainMaterial(st);
    // sky, fog, light
    this.skyU.top.value.set(st.sky.top); this.skyU.mid.value.set(st.sky.mid); this.skyU.bot.value.set(st.sky.bot);
    this.fog.color.set(st.sky.fog); this.fog.near = st.sky.near; this.fog.far = st.sky.far;
    this.hemi.intensity = st.light.hemi; this.hemi.color.set(st.light.hemiSky); this.hemi.groundColor.set(st.light.hemiGround);
    this.sun.intensity = st.light.sun; this.sun.color.set(st.light.sunColor); this.sun.position.set(...st.light.sunPos);
    this.stars.visible = !!st.stars;
    this.mapBg = new THREE.Color(st.material === 'blueprint' ? '#0e2c55' : st.palette[0]);
    if (st.tint) this.mapBg.multiply(new THREE.Color(...st.tint));
    // overlays
    this.wire.visible = !!st.wire;
    if (st.wire) { this.wire.material.color.set(st.wire.color); this.wire.material.opacity = st.wire.opacity; }
    this.outline.visible = !!st.outlines;
    if (st.outlines) { this.outline.material.color.set(st.outlines.color); this.outline.material.opacity = st.outlines.opacity; }
    this._styleTrees(st);
    for (const b of this.buildingMeshes) b.material.wireframe = st.material === 'blueprint';
    return name;
  }

  // ------------------------------------------------------------------ buildings, flags, height
  _buildings() {
    this.buildingMeshes = [];
    for (const b of this.data.buildings || []) {
      const wall = [], roof = [];
      const r = b.ring, y0 = b.base - 1, y1 = b.base + b.h;
      for (let i = 0; i < r.length; i++) {
        const a = r[i], c = r[(i + 1) % r.length];
        wall.push(a[0], y0, a[1], c[0], y0, c[1], c[0], y1, c[1], a[0], y0, a[1], c[0], y1, c[1], a[0], y1, a[1]);
      }
      for (const t of b.roof) for (const v of t) roof.push(v[0], y1, v[1]);
      for (const [arr, color] of [[wall, '#d8cbb8'], [roof, '#8a5a48']]) {
        const g = new THREE.BufferGeometry();
        g.setAttribute('position', new THREE.Float32BufferAttribute(arr, 3));
        g.computeVertexNormals();
        const mesh = new THREE.Mesh(g, new THREE.MeshLambertMaterial({ color, side: THREE.DoubleSide, flatShading: true }));
        this.group.add(mesh);
        this.buildingMeshes.push(mesh);
      }
    }
  }

  _flags() {
    this.flags = [];
    const poleGeo = new THREE.CylinderGeometry(0.035, 0.035, 2.4, 6).translate(0, 1.2, 0);
    const poleMat = new THREE.MeshLambertMaterial({ color: '#f4f4f4', emissive: '#333333' });
    const flagGeo = new THREE.BufferGeometry();
    flagGeo.setAttribute('position', new THREE.Float32BufferAttribute([0, 2.4, 0, 0, 1.85, 0, 0.75, 2.12, 0.0], 3));
    flagGeo.computeVertexNormals();
    const cupGeo = new THREE.RingGeometry(0.0, 0.11, 16).rotateX(-Math.PI / 2);
    const cupMat = new THREE.MeshBasicMaterial({ color: '#111' });
    const teeGeo = new THREE.SphereGeometry(0.12, 8, 6);
    const teeMat = new THREE.MeshLambertMaterial({ color: '#ffffff', emissive: '#444444' });
    for (const h of this.data.holes) {
      const g = new THREE.Group();
      g.position.set(...h.pin);
      g.add(new THREE.Mesh(poleGeo, poleMat));
      const fm = new THREE.Mesh(flagGeo, new THREE.MeshLambertMaterial({ color: '#e8352c', emissive: '#5a0d0a', side: THREE.DoubleSide }));
      g.add(fm);
      const cup = new THREE.Mesh(cupGeo, cupMat);
      cup.position.y = 0.03;
      g.add(cup);
      this.group.add(g);
      this.flags.push({ group: g, flag: fm, hole: h.number });
      const tdir = new THREE.Vector3(h.path[1][0] - h.tee[0], 0, h.path[1][2] - h.tee[2]).normalize();
      const side = new THREE.Vector3(-tdir.z, 0, tdir.x);
      for (const sgn of [-1, 1]) {
        const m = new THREE.Mesh(teeGeo, teeMat);
        m.position.set(h.tee[0] + side.x * 3 * sgn + tdir.x * 1.5, h.tee[1] + 0.1, h.tee[2] + side.z * 3 * sgn + tdir.z * 1.5);
        this.group.add(m);
      }
    }
  }

  animate(time) {
    for (const f of this.flags) f.flag.rotation.y = Math.sin(time * 1.7 + f.hole) * 0.35 + 0.4;
  }

  _heightmap() {
    const hm = this.data.heightmap;
    this.hm = { ...hm, z: b64(hm.data, Float32Array) };
  }

  heightAt(x, z) {
    const h = this.hm, n = h.n;
    const fx = Math.min(Math.max((x - h.x0) / (h.x1 - h.x0) * (n - 1), 0), n - 1.001);
    const fz = Math.min(Math.max((z - h.z0) / (h.z1 - h.z0) * (n - 1), 0), n - 1.001);
    const i = Math.floor(fz), j = Math.floor(fx), u = fx - j, v = fz - i;
    const a = h.z[i * n + j], b = h.z[i * n + j + 1], c = h.z[(i + 1) * n + j], d = h.z[(i + 1) * n + j + 1];
    return (a * (1 - u) + b * u) * (1 - v) + (c * (1 - u) + d * u) * v;
  }
}
