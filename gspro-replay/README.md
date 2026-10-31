# GSPro Replay

Turns a round you played in GSPro into a **low-poly 3D recreation of the real course** with your shots flying over it, as an **interactive replay** (a single `replay.html` file) and an **MP4 video**.

```
your shots (CSV / JSONL) ─┐
OpenStreetMap golf data ──┼─► low-poly terrain + trees + flags ─► replay.html ─► round.mp4
USGS lidar / 3DEP DEM ────┤        + ball-flight physics
aerial imagery ───────────┘
```

## Quick start on Windows (desktop app)

1. Install **Python 3.12** from python.org and tick **"Add python.exe to PATH"** in the installer.
2. Unzip this folder somewhere, for example `C:\golf\gspro-replay`.
3. Double-click **`Install (run once).bat`**. This takes a few minutes and adds a **GSPro Replay** shortcut to your desktop.
4. Open **GSPro Replay**, then:
   - **Browse…** to the `PlayerShots_….csv` GSPro saved. The course name fills in automatically.
   - Type the **Town / state** (for example `West Lafayette, IN`).
   - Click **Build replay**. It opens in your browser when done.
   - Click **Export MP4** for the video, or tick *then make the MP4* before building.

Settings are remembered between sessions, and **Try the demo** works without your own data.

## Install from the command line (Windows, macOS or Linux, Python 3.9+)

```bash
cd gspro-replay
pip install -e .            # add [lidar] for raw point clouds:  pip install -e ".[lidar]"
python -m playwright install chromium     # only needed for command-line MP4 export
```

## Try it in 30 seconds (no downloads)

```bash
gspro-replay demo --out demo_out
# open demo_out/replay.html in Chrome or Edge
gspro-replay export demo_out/replay.html -o demo.mp4
```

## Your real round

```bash
gspro-replay build --course "Bethpage Black, Farmingdale NY" --shots my_round.csv --out bethpage --player "Brent"
gspro-replay export bethpage/replay.html -o bethpage.mp4
```

What `build` does:

1. **Finds the course** with OpenStreetMap Nominatim (or pass `--bbox south,west,north,east`).
2. **Downloads golf features** from Overpass: `golf=hole` lines (number, par, tee→green path), greens, tees, fairways, bunkers, water, woods, cart paths, buildings, pins.
3. **Elevation** (`--dem 3dep` by default): USGS 3DEP 1 m bare-earth DEM, which is derived from lidar. Outside the US it falls back to global Terrarium tiles automatically.
   **Raw lidar:** `--lidar auto` downloads the USGS 3DEP point-cloud (LAZ) tiles that cover the course, or pass your own `--lidar a.laz b.laz`. Ground returns give the terrain, and vegetation returns give real tree positions and heights. LAZ tiles are often 100 MB or more each.
4. **Aerial imagery**: OpenStreetMap has no satellite layer of its own, so this uses Esri World Imagery, the same layer the OSM editor offers (`--imagery-url` for another XYZ source, `--no-imagery` to skip).
5. **Builds the low-poly mesh**: dense facets on greens, medium on fairways, sparse in the rough. Feature outlines are built into the mesh, bunkers are dug in and water is flattened.
6. **Places every shot**: ball flight is simulated from speed, launch angles and spin (drag plus Magnus lift), then scaled to the carry and offline numbers you recorded, landed on the terrain, bounced and rolled. Shots aim down the hole's centreline (doglegs and lay-ups) and at the pin when it's in range. The last stroke on each hole finishes in the cup.

Everything downloaded is cached in `~/.cache/gspro-replay`.

## Shot data

**GSPro's PlayerShots CSV** (`PlayerShots_<date>.csv`) works directly:

```bash
gspro-replay build --shots PlayerShots_2026-10-29_16-47.csv --near "West Lafayette, IN" --player "Brent" --out coyote
```

It uses GSPro's *Shot Number* and *Global Shot Number* columns to work out every stroke you actually took, including ones GSPro counted but didn't export:
* **Putts:** GSPro doesn't export putts when your launch monitor can't putt. They're drawn from the green as white putts, labelled "putt not tracked".
* **Gaps mid-hole** (penalties or misreads) are counted, so stroke numbers and scores match GSPro.
* **An untracked shot from off the green** is drawn as a grey dashed "Not recorded" shot onto the green, never as a putt.
* **A hole with no strokes after your last recorded shot** means you holed it, and the replay shows it going in.

It also reads the course name and date from the file, sorts the shots (GSPro lists them newest first), and uses Peak Height to shape each flight. For files without shot numbers, holes whose last recorded shot isn't a putt are finished with estimated putts (turn this off with `--no-auto-putt`, or give exact scores with `--scorecard`). The HUD shows GSPro's own Carry/Total numbers.

Other ways to get shots in:

| Source | How |
|---|---|
| **Record while you play** (best) | `gspro-replay record -o round.jsonl`, then point your launch-monitor connector at port **9211** instead of 921. Each shot is logged with the club and distance-to-pin that GSPro reports, and the data still passes through to GSPro. |
| **Launch monitor / GSPro CSV** | Any CSV with columns like `Club, Ball Speed, VLA/Launch Angle, HLA/Launch Direction, Back Spin, Side Spin` or `Spin Axis + Total Spin, Carry, Total, Offline`. Headers are matched loosely, units like `(mph)`, `(m)`, `(km/h)` are converted, and `L 3.2` / `R 1.0` values are understood. |
| **Your own sheet** | Same CSV format plus a `Hole` column. Optional: `Distance To Pin` (before the shot), used to pin each ball position exactly. |

If the file has no `Hole` column, add `--scorecard 4,5,3,4,...` (strokes per hole) and shots are split in order. Missing strokes (gimmes, auto-putts) are added as "auto putts". Use `--start-hole 10` for back-nine starts and `--holes 1-9` to build only some holes.

**Pins:** OSM rarely knows the day's pin. Pass `--pins pins.json` with `{"1": [lat, lon], ...}` (see `examples/`), otherwise the green's centre is used.

## The replay viewer (`replay.html`)

A single self-contained file you can open in Chrome or Edge, share, or host. It needs no server or internet connection.

* **Play/pause** (space), **previous/next shot** (← →), scrubber with hole ticks, hole buttons (marked red if under par, blue if over).
* **Camera:**
  * *Broadcast*: aim, chase and landing cameras, with flyover intros.
  * *Map (top-down)*: flat shot-tracker view of each hole, tee on the left and green on the right. Shots are drawn in each club's colour with numbered stroke markers and club/distance labels, dashed yardage rings show 50–300 yds to the pin, and it zooms into the green for putting. Pair it with the *Yardage book* look for a classic yardage-book page.
  * *Follow*, *Overhead*, or *Free* (drag to orbit).
* **Look:** 12 styles, switchable live and used for MP4 export:
  * *Low-poly*: flat-shaded stylised surfaces.
  * *Realistic*: smooth terrain blended with aerial colours, with detailed trees.
  * *Satellite facets*: each facet takes the aerial photo's colour.
  * *Aerial photo*: the photo draped over the terrain.
  * *Cartoon*: cel-shaded, with outlined trees and feature edges.
  * *Yardage book*: paper colours with 1 m / 5 m elevation contours.
  * *Blueprint*: navy wireframe.
  * *Night*: moonlit, with stars.
  * *Golden hour*: low warm sunlight.
  * *Autumn*, *Winter* and *Links (fescue)*: seasonal and regional palettes.

  *Satellite facets* and *Aerial photo* only appear when the replay was built with aerial imagery.
* HUD: hole and par, distance to pin, live carry/total counter, shot stats, minimap, score name (Birdie, Par…) with a running scorecard, and tracers coloured by club.
* **Export MP4** button: encodes in the browser with WebCodecs (Chrome/Edge) and streams to a file you choose. You pick resolution up to 4K, 24/30/60 fps, speed, and which holes.

## Command-line MP4 export

```bash
gspro-replay export replay.html -o round.mp4 --width 1920 --height 1080 --fps 30 --style toon --camera map --holes 1-9 --speed 1.5
```

Runs headless Chromium (falls back to your installed Edge/Chrome) and pipes frames to ffmpeg (H.264, `-preset veryfast`). It produces the same pictures as the viewer, because the camera and HUD are pure functions of time. Rendering speed depends on your GPU. A full 18-hole round is roughly 12–20 minutes of video; use `--speed` to shorten it, or `--pace 0.6` at build time for shorter pauses.

## Options worth knowing

| Option | Effect |
|---|---|
| `--detail 0.7` | More polygons (smaller facets). `1.5` = chunkier low-poly. |
| `--tree-density 0.5` | Fewer trees in OSM woods (lidar mode uses real trees). |
| `--margin 150` | More scenery around the course. |
| `--res 2` | Coarser elevation grid (faster, for big properties). |
| `--lidar-epsg 6539` | CRS for LAZ files that don't declare one. |

## Troubleshooting

* **"No golf=hole ways found"**: the course isn't fully mapped in OSM. Check it on openstreetmap.org. Adding the holes yourself (tags `golf=hole`, `ref`, `par`, drawn tee→green) takes about 20 minutes in the iD editor and helps every golfer.
* **Wrong course at a 36-hole facility**: pass a tighter `--bbox`.
* **Shots look offset from GSPro**: GSPro course designers don't always match the real layout exactly. Use `--pins`, and record with `gspro-replay record` so distance-to-pin can correct each ball position.
* **Rebuilding the viewer** (only if you edit `viewer/src`): `cd viewer && npm install && ./build.sh`.

## Attribution

Map data © OpenStreetMap contributors (ODbL). Elevation: USGS 3DEP. Imagery: Esri, Maxar, Earthstar Geographics. These credits are drawn into every replay and video; keep them if you share.
