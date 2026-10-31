# GSPro_Replay

**Turn a round you played in [GSPro](https://gsprogolf.com) into a 3D recreation of the real course, with every shot flying over it. Watch it as an interactive replay, or export it as an MP4.**

![Broadcast-style replay of a drive](docs/images/hero.jpg)

GSPro Replay takes the shot data GSPro exports and combines it with:

- **OpenStreetMap** golf features: holes, greens, fairways, bunkers, water and trees.
- **USGS lidar terrain**: 1 m bare-earth elevation, or raw point clouds for real tree heights.
- **Aerial imagery** of the course.

It builds a low-poly version of the course, places each shot using ball-flight physics matched to your launch monitor numbers, and produces:

- a **single `replay.html` file** with a TV-style camera director, shot tracers, stats and a scorecard, which opens in any browser and needs no server, and
- an **MP4 video** of the whole round or the holes you choose.

It comes with a Windows desktop app, so you don't need the command line.

---

## Contents

- [Features](#features)
- [Quick start (Windows)](#quick-start-windows)
- [Command line](#command-line)
- [Your shot data](#your-shot-data)
- [Looks and cameras](#looks-and-cameras)
- [How it works](#how-it-works)
- [Options reference](#options-reference)
- [Troubleshooting](#troubleshooting)
- [Development](#development)
- [Data sources and attribution](#data-sources-and-attribution)

---

## Features

- **Real courses, found by name.** It looks up the course on OpenStreetMap and pulls all 18 holes with their par, tee-to-green routing and every surface. A 36-hole facility is narrowed to the course you named.
- **Lidar terrain.** By default it uses USGS 3DEP 1 m elevation. It can also download raw 3DEP point clouds instead, which gives true ground shape plus individual trees detected at their real height.
- **Adaptive low-poly mesh.** Greens get small facets, fairways medium and the rough large. Feature outlines are built into the mesh, bunkers are dug in and water is flattened.
- **Shot physics matched to your data.** Ball flight uses drag and lift, then is scaled to the carry, offline and peak height GSPro reported, landed on the actual terrain, bounced and rolled.
- **Every stroke accounted for.** GSPro's shot numbering is used to recover strokes it counted but didn't export (putts when your launch monitor can't putt, misreads, penalty drops), so scores match GSPro.
- **Broadcast camera director.** Each hole opens with a flyover, then each shot goes through an aim view, a chase camera and a landing camera, with a low camera for putts.
- **Map (top-down) camera.** A shot-tracker view with yardage rings, numbered strokes, club-coloured lines, and a zoom into the green for putting.
- **12 visual styles.** Low-poly, Realistic, Satellite, Aerial photo, Cartoon, Yardage book, Blueprint, Night, Golden hour, Autumn, Winter and Links. You can switch them live.
- **On-screen info.** Hole card, live carry/total counter, ball speed, launch angle and spin, minimap, score banners (Birdie, Par…) and a running scorecard.
- **MP4 export** two ways: from the command line (headless Chromium piped into ffmpeg), or inside the replay with the Export MP4 button (WebCodecs, Chrome/Edge), up to 4K/60.
- **Desktop app** with progress, cancel, remembered settings and a built-in demo.
- **Round recorder** that can log your shots live from GSPro Open Connect.

<table>
<tr>
<td width="50%"><img src="docs/images/map.jpg" alt="Map camera with the Yardage book style"><br><sub><b>Map camera</b> + Yardage book style: contours, yardage rings, stroke markers</sub></td>
<td width="50%"><img src="docs/images/gui.jpg" alt="Desktop app"><br><sub><b>Desktop app</b>: pick your CSV, build, export</sub></td>
</tr>
</table>

---

## Quick start (Windows)

1. Install **Python 3.10 or newer** from [python.org](https://www.python.org/downloads/). On the first installer screen, tick **"Add python.exe to PATH"**.
2. Download this repository (**Code → Download ZIP**), then right-click the zip and choose **Extract All…**. Don't run anything from inside the zip.
3. Double-click **`Install (run once).bat`**. It installs the Python libraries, downloads the browser used for video rendering, and creates a **GSPro Replay** shortcut on your desktop.
4. Open **GSPro Replay**:
   1. **Browse…** to the `PlayerShots_<date>.csv` file GSPro saved. The course name, date and output folder fill in automatically.
   2. Enter the course's **Town / state**, for example `West Lafayette, IN`.
   3. Click **Build replay**. The replay opens in your browser when it's ready.
   4. Pick a resolution, look and camera, then click **Export MP4**. Or tick *then make the MP4* before building to do both in one step.

Not ready to use your own data? Click **Try the demo** for a synthetic 4-hole course that needs no downloads.

> The first build of a course downloads map data, elevation and imagery, which takes a minute or two. Everything is cached in `%USERPROFILE%\.cache\gspro-replay`, so rebuilds are fast.

---

## Command line

Works on Windows, macOS and Linux with Python 3.9 or newer.

```bash
git clone https://github.com/<you>/gspro-replay.git
cd gspro-replay
pip install -e ".[lidar]"              # drop [lidar] if you won't use raw point clouds
python -m playwright install chromium  # only needed for command-line MP4 export
```

```bash
# Try it: synthetic course, no network needed
gspro-replay demo --out demo

# Build your round (course name and date are read from GSPro's CSV)
gspro-replay build --shots PlayerShots_2026-10-29_16-47.csv --near "West Lafayette, IN" \
                   --player "Brent" --out coyote

# Watch it
#   open coyote/replay.html in Chrome, Edge or Firefox

# Export a video
gspro-replay export coyote/replay.html -o coyote.mp4 --style realistic --camera broadcast
gspro-replay export coyote/replay.html -o front9_map.mp4 --style yardage --camera map --holes 1-9 --speed 1.5

# Open the desktop app
gspro-replay gui          # or: gspro-replay-gui
```

| Command | What it does |
|---|---|
| `build` | Builds a replay for a real course from your shots. |
| `export` | Renders a `replay.html` to MP4. |
| `demo` | Builds a synthetic course and round, with no downloads. |
| `record` | Logs shots from GSPro Open Connect while you play. |
| `gui` | Opens the desktop app. |

---

## Your shot data

### GSPro PlayerShots CSV (recommended)

GSPro's `PlayerShots_<date>.csv` works as it comes. GSPro lists shots newest first, and the importer sorts them. It reads these columns when present:

`Course Name`, `Round Date`, `Hole`, `Shot Number`, `Global Shot Number`, `Club Name`, `Ball Speed`, `VLA`, `HLA`, `Back Spin`, `Side Spin`, `Spin Axis`, `Total Spin`, `Carry Dist`, `Total Dist`, `Offline`, `Peak Height`

**Strokes GSPro didn't export.** GSPro numbers every stroke but only exports the ones your launch monitor measured. The importer uses `Shot Number` and `Global Shot Number` to recover the rest:

| In the export | Shown in the replay as |
|---|---|
| Strokes after your last recorded shot, with the ball on or near the green | **Putts**, labelled *putt not tracked* |
| An untracked stroke while the ball is off the green | A grey dashed **Not recorded** shot onto the green |
| A gap in shot numbers mid-hole (penalty or misread) | A counted stroke; the next shot's card says *1 stroke not recorded before this* |
| No strokes after the last recorded shot | That shot holes out |

Where the count can't be worked out (for example the last hole of the file, or a hole followed by a missing hole), the hole is finished with estimated putts. Turn that off with `--no-auto-putt`, or give exact scores with `--scorecard 4,5,3,...`.

### Other formats

- **Any launch-monitor CSV.** Column names are matched loosely (`Ball Speed (mph)`, `Launch Angle`, `Launch Direction`, …). Units like `(m)` and `(km/h)` are converted, and values like `3.2 L` / `R 1.0` are understood. Add a `Hole` column, or pass `--scorecard`.
- **Live recording.** Run `gspro-replay record -o round.jsonl`, then point your launch-monitor connector at port **9211** instead of 921. Shots pass through to GSPro unchanged and are logged together with the club and distance to target that GSPro reports.
- **JSON.** A list of shot objects using the importer's field names (`hole`, `club`, `ball_speed`, `vla`, `hla`, `carry`, `total`, …).

### Pins

OpenStreetMap rarely knows the day's pin positions, so the centre of each green is used. To set exact pins, pass `--pins pins.json`:

```json
{ "1": [40.74512, -73.45231], "2": [40.74688, -73.44970] }
```

---

## Looks and cameras

![All 12 styles](docs/images/styles.jpg)

| Look | Description |
|---|---|
| `lowpoly` | Flat-shaded stylised surfaces (default) |
| `realistic` | Smooth terrain blended with aerial colours, detailed trees |
| `satellite` | Each facet takes the aerial photo's colour |
| `photo` | Aerial photo draped over the terrain |
| `toon` | Cartoon: cel-shaded, with outlined trees and feature edges |
| `yardage` | Paper colours with 1 m / 5 m elevation contours |
| `blueprint` | Navy wireframe with white feature outlines |
| `night` | Moonlit, with stars; tracers stand out |
| `sunset` | Golden hour: low warm sun, orange sky |
| `autumn` / `winter` / `links` | Seasonal and regional palettes |

`satellite` and `photo` need the replay to be built with imagery (the default).

| Camera | Description |
|---|---|
| `broadcast` | Hole flyover, then aim, chase and landing cameras, and a low camera for putts (default) |
| `map` | Top-down shot tracker, tee on the left and green on the right, with yardage rings and a zoom into the green for putts |
| `follow` | Chase camera for the whole shot |
| `overhead` | High angled view framing the whole hole |
| `free` | Drag to orbit (interactive replay only) |

**Replay controls:** <kbd>Space</kbd> plays and pauses, <kbd>←</kbd> / <kbd>→</kbd> jump to the previous or next shot, and <kbd>H</kbd> hides the controls. The bar at the bottom also has hole buttons, speed, camera, look, *All tracers* and **Export MP4**.

---

## How it works

```
PlayerShots.csv ──► shots.py ──────► per-hole strokes (sorted, untracked strokes recovered)
                                              │
course name ──► osm.py (Nominatim + Overpass) │
                 holes, greens, fairways,     ▼
                 bunkers, water, woods ──► mesh.py ──► low-poly terrain, classes, trees
elevation.py ── 3DEP DEM / lidar LAZ ───────┘     │
imagery.py ──── aerial tiles ───────────────┘     ▼
                                          layout.py + physics.py
                                          shot placement and flight, timeline
                                                  │
                                                  ▼
                                   scene.py ──► replay.html (data + bundled viewer)
                                                  │
                         export.py ── headless Chromium ──► ffmpeg ──► round.mp4
```

- **Coordinates:** a local east/north metre frame around the course centre.
- **Mesh:** a Delaunay triangulation of adaptively sampled points. Each facet stores its surface class and an averaged aerial-photo colour.
- **Flight:** RK4 integration with drag and Magnus lift and spin decay. The trajectory is rescaled so carry, offline and peak height match your data, then intersected with the terrain.
- **Aiming:** each shot aims down the hole's centre line for lay-ups and doglegs, or at the pin when in range, then is rotated by its HLA.
- **Viewer:** three.js, bundled into one script. The camera and the on-screen info are pure functions of time, so playback, scrubbing and MP4 export produce identical frames.

```
gspro_replay/
  cli.py         command-line entry point
  gui.py         tkinter desktop app
  shots.py       CSV / JSON / JSONL import, untracked-stroke recovery
  osm.py         course lookup and golf feature parsing
  elevation.py   3DEP DEM, Terrarium tiles, LAZ point clouds
  imagery.py     aerial tile mosaic, warped to the local frame
  mesh.py        adaptive low-poly terrain, trees, buildings
  physics.py     ball-flight model
  layout.py      shot placement and timeline
  scene.py       scene assembly, replay.html writer
  export.py      MP4 export (Playwright + ffmpeg)
  recorder.py    GSPro Open Connect proxy recorder
  demo.py        synthetic course and round
  viewer_dist/   prebuilt viewer bundle (generated from viewer/src)
viewer/src/      three.js viewer source (world, replay, director, hud, styles)
examples/        sample shot files and a pins file
```

---

## Options reference

### `build`

| Option | Default | Description |
|---|---|---|
| `--shots FILE` | *required* | CSV / JSON / JSONL shot file |
| `--course NAME` | from CSV | Course name for the OpenStreetMap lookup |
| `--near "Town, ST"` | | Town and state, to pick the right course |
| `--bbox S,W,N,E` | | Exact area instead of a name lookup |
| `--out DIR` | `replay_out` | Output folder |
| `--player NAME`, `--title TEXT` | | Names shown in the replay |
| `--holes 1-9` | all | Only these holes |
| `--scorecard 4,5,3,…` | | Strokes per hole, if your file has no hole numbers |
| `--start-hole N` | 1 | First hole when splitting by scorecard |
| `--pins FILE` | green centres | Pin positions (JSON) |
| `--no-auto-putt` | | Don't add estimated putts to holes that can't be counted |
| `--dem 3dep\|terrarium` | `3dep` | Elevation source (`terrarium` for courses outside the US) |
| `--lidar auto` or `--lidar a.laz …` | | Raw lidar point clouds: real terrain and tree heights |
| `--lidar-epsg CODE` | | Coordinate system for LAZ files that don't declare one |
| `--res M` | 1.0 | Elevation grid resolution in metres |
| `--no-imagery` | | Skip aerial imagery |
| `--imagery-zoom Z` | 18 | Imagery detail level |
| `--imagery-url URL` | Esri World Imagery | Custom XYZ tile source `…/{z}/{x}/{y}` |
| `--margin M` | 70 | Metres of terrain around the course |
| `--detail X` | 1.0 | Facet size multiplier (smaller = more polygons) |
| `--tree-density X` | 1.0 | Tree density in OSM woods |
| `--pace X` | 1.0 | Length of the pauses between shots |

### `export`

| Option | Default | Description |
|---|---|---|
| `replay` | *required* | Path to `replay.html` |
| `-o FILE` | `round.mp4` | Output video |
| `--width`, `--height` | 1920×1080 | Resolution |
| `--fps` | 30 | Frame rate |
| `--style` | `lowpoly` | Look (see above) |
| `--camera` | `broadcast` | Camera (see above) |
| `--holes 1-9` | all | Only these holes |
| `--speed X` | 1.0 | Playback speed multiplier |
| `--crf N`, `--preset P` | 20, `veryfast` | H.264 quality and encoder speed |

---

## Troubleshooting

| Problem | Fix |
|---|---|
| The launcher's black window flashes and closes | You're running it from inside the zip. Extract the zip first, then run `Install (run once).bat`. |
| `'python' is not recognized` | Re-run the Python installer, choose **Modify**, and tick **Add python.exe to PATH**. |
| "Couldn't find that golf course" | Check the course's exact name on [openstreetmap.org](https://www.openstreetmap.org), add the town, or use **Advanced → Bounding box**. |
| "No golf=hole ways found" | The course isn't mapped hole by hole in OSM. Adding the holes in the iD editor (`golf=hole`, `ref`, `par`, drawn from tee to green) takes about 20 minutes and helps everyone. |
| Wrong course at a 36-hole facility | Pass a tighter `--bbox`. |
| `HTTP 429 Too Many Requests` while downloading lidar | It's retried automatically. If it keeps failing, the build falls back to the 3DEP elevation model, and tiles that already downloaded are reused next time. |
| `HTTP 502` from Overpass | Temporary; it's retried automatically. |
| Shots look offset from GSPro | GSPro course designs don't always match the real layout. Use `--pins` for exact pin positions. |
| The video is slow to render | Rendering uses your GPU through headless Chromium. Try `--speed 1.5`, fewer holes, or the in-replay **Export MP4** button. |

---

## Development

The Python package is ready to use. The viewer is prebuilt into `gspro_replay/viewer_dist/`, so Node is only needed if you change the viewer:

```bash
cd viewer
npm install
./build.sh        # bundles viewer/src with esbuild into gspro_replay/viewer_dist/
```

Then rebuild a replay (`gspro-replay demo --out demo`) to pick up the new viewer. The replay page exposes a small API (`window.replay.setup()`, `.frame(t)`, `.grab()`), which the exporter uses and which is handy for automated screenshots.

---

## Data sources and attribution

- **Map data** © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors, available under the ODbL. Course lookup uses [Nominatim](https://nominatim.org) and features come from [Overpass](https://overpass-api.de); please respect their usage policies.
- **Elevation and lidar:** [USGS 3D Elevation Program (3DEP)](https://www.usgs.gov/3d-elevation-program), public domain. Outside the US: [Terrain Tiles](https://registry.opendata.aws/terrain-tiles/) on AWS Open Data.
- **Aerial imagery:** Esri World Imagery (Esri, Maxar, Earthstar Geographics). Check Esri's terms before redistributing videos commercially.
- **3D:** [three.js](https://threejs.org) (MIT). **MP4 muxing:** [mp4-muxer](https://github.com/Vanilagy/mp4-muxer) (MIT).

These credits are drawn into every replay and video; keep them when you share.

GSPro Replay is an independent project and isn't affiliated with or endorsed by GSPro.

## License

_Add your license here (for example MIT) and include a `LICENSE` file._

