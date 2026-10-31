// Visual styles. Each entry describes how the world should look; World.setStyle() applies it.
// palette order: out, rough, fairway, green, tee, bunker, water, wood, path, building

export const BASE_PALETTE = ['#7f9c56', '#5e8e3c', '#79b84a', '#93d65c', '#86c955', '#ecdcae', '#3f93bd', '#456f35', '#cfc8b6', '#b9a48f'];
const BASE_TREES = { broad: ['#4f8034', '#5c8f3b', '#3f6f2d', '#6a9a41'], conifer: ['#2e5a35', '#356640', '#2a4f30'], trunk: ['#6b4f35', '#5d4430'] };
const DAY_SKY = { top: '#3f7fd0', mid: '#9cc6ee', bot: '#dde9f0', fog: '#d6e6ef', near: 900, far: 3200 };
const DAY_LIGHT = { hemi: 1.1, hemiSky: '#dcecff', hemiGround: '#4d5b2f', sun: 2.9, sunColor: '#fff3dc', sunPos: [-700, 520, 380] };

const S = (o) => ({ shading: 'flat', color: 'palette', material: 'lambert', palette: BASE_PALETTE, trees: BASE_TREES,
  treeDetail: 'low', sky: DAY_SKY, light: DAY_LIGHT, outlines: null, wire: null, stars: false, treeOutline: false, jitter: 1, ...o });

export const STYLES = {
  lowpoly: S({ label: 'Low-poly' }),
  satellite: S({ label: 'Satellite facets', color: 'satellite', needs: 'rgb' }),
  photo: S({ label: 'Aerial photo', color: 'photo', shading: 'smooth', needs: 'imagery' }),
  realistic: S({ label: 'Realistic', shading: 'smooth', color: 'blend', treeDetail: 'high', jitter: 0.5,
    sky: { ...DAY_SKY, top: '#2f6fc4', near: 1200, far: 4500 } }),
  toon: S({ label: 'Cartoon', material: 'toon', jitter: 0.3, treeOutline: true,
    palette: ['#8cc63f', '#6abf3a', '#9be35a', '#bdf26d', '#a6e86a', '#ffe9a8', '#3fb6ff', '#4f9a3a', '#ffffff', '#ffb38a'],
    trees: { broad: ['#3fae3a', '#58c23c', '#2f9a34'], conifer: ['#1f7a3a', '#25884a'], trunk: ['#8a5a2b'] },
    outlines: { color: '#1d2b14', opacity: 0.75 },
    sky: { top: '#2e8bff', mid: '#8fd3ff', bot: '#e8f8ff', fog: '#d8f0ff', near: 1100, far: 3600 },
    light: { ...DAY_LIGHT, hemi: 1.2, sun: 2.2 } }),
  yardage: S({ label: 'Yardage book', material: 'contour', shading: 'smooth', jitter: 0,
    palette: ['#efe8d2', '#e6e5c6', '#cfe3a8', '#b4da8a', '#c4e09a', '#f6eccb', '#a9cfe0', '#c3cfa6', '#e8e1cc', '#d9cbb4'],
    trees: { broad: ['#9db57e', '#aac08a'], conifer: ['#86a46e', '#91ad78'], trunk: ['#a68f6f'] },
    outlines: { color: '#3d5a2a', opacity: 0.8 },
    sky: { top: '#f3eedd', mid: '#f3eedd', bot: '#f3eedd', fog: '#f3eedd', near: 1400, far: 5000 },
    light: { ...DAY_LIGHT, hemi: 2.2, hemiSky: '#ffffff', hemiGround: '#d8d0b8', sun: 0.9 } }),
  blueprint: S({ label: 'Blueprint', material: 'blueprint', jitter: 0, treeDetail: 'wire',
    trees: { broad: ['#5fc1ff'], conifer: ['#5fc1ff'], trunk: ['#3a8fd0'] },
    wire: { color: '#3fa9f5', opacity: 0.22 }, outlines: { color: '#e6f4ff', opacity: 0.95 },
    sky: { top: '#071a33', mid: '#0a2342', bot: '#0c2a4f', fog: '#0a2342', near: 900, far: 3000 },
    light: { ...DAY_LIGHT, hemi: 0.6, sun: 0.4 } }),
  night: S({ label: 'Night', stars: true, tint: [0.5, 0.56, 0.75],
    trees: { broad: ['#24402a', '#2b4a31'], conifer: ['#16301f', '#1b3824'], trunk: ['#2c241c'] },
    sky: { top: '#01040c', mid: '#07142b', bot: '#162944', fog: '#0b1628', near: 500, far: 2600 },
    light: { hemi: 0.55, hemiSky: '#6d8cc4', hemiGround: '#0a0f08', sun: 1.1, sunColor: '#bcd2ff', sunPos: [500, 700, -300] } }),
  sunset: S({ label: 'Golden hour', tint: [1.1, 1.0, 0.86],
    trees: { broad: ['#5a7a2c', '#6b8530', '#4c6a26'], conifer: ['#30502c', '#38592f'], trunk: ['#5d3f25'] },
    sky: { top: '#3b4f8f', mid: '#f29a5c', bot: '#ffd29a', fog: '#f4c08e', near: 700, far: 3000 },
    light: { hemi: 0.9, hemiSky: '#ffd7b0', hemiGround: '#4d3a2a', sun: 3.4, sunColor: '#ffb070', sunPos: [-900, 160, 300] } }),
  autumn: S({ label: 'Autumn',
    palette: ['#9a9c56', '#7f8d3c', '#7fb04a', '#8fcf5c', '#86c955', '#ecdcae', '#3f7fa0', '#7a5a2a', '#cfc8b6', '#b9a48f'],
    trees: { broad: ['#d9822b', '#c4501f', '#e3b23c', '#a8402a', '#8a9a3b'], conifer: ['#2e5a35', '#356640'], trunk: ['#4f3a28'] },
    sky: { ...DAY_SKY, top: '#5a86c8', mid: '#b9cfe6', bot: '#e9e6dc', fog: '#e2ddd0' } }),
  winter: S({ label: 'Winter',
    palette: ['#e9eef2', '#e1e8ed', '#cfdcd2', '#9cc58a', '#c6d8c4', '#f2f0ea', '#8fb3c8', '#d7dfe4', '#d8dde0', '#b9a48f'],
    trees: { broad: ['#7a6a5a', '#6d5f52'], conifer: ['#2f4f3a', '#e6edf1', '#3b5c45'], trunk: ['#5a4a3c'] },
    sky: { top: '#8aa6c4', mid: '#c9d6e2', bot: '#eef2f5', fog: '#e4eaef', near: 600, far: 2600 },
    light: { ...DAY_LIGHT, hemi: 1.3, sun: 2.0, sunColor: '#f4f7ff' } }),
  links: S({ label: 'Links (fescue)',
    palette: ['#b7a96a', '#a59a5e', '#8fb05a', '#9fcf68', '#9ac45f', '#e6d3a0', '#3f7f9c', '#6f7b4a', '#cfc8b6', '#b9a48f'],
    trees: { broad: ['#6f7b4a', '#7f8b52'], conifer: ['#4d5f3a'], trunk: ['#5d4430'] },
    sky: { ...DAY_SKY, top: '#5d7fa8', mid: '#b4c6d6', bot: '#e6eaea', fog: '#d9dfe2' } }),
};

export const STYLE_ORDER = ['lowpoly', 'realistic', 'satellite', 'photo', 'toon', 'yardage', 'blueprint', 'night', 'sunset', 'autumn', 'winter', 'links'];
