"""Elevation sources.

* ``3dep``      USGS 3DEP 1 m bare-earth DEM (lidar-derived), US only.  Default.
* ``terrarium`` AWS/Mapzen Terrarium tiles, global, ~3-10 m.          Fallback.
* LAZ/LAS       Raw lidar point clouds: local files, or ``auto`` to pull the USGS
                3DEP LPC tiles covering the course.  Gives bare earth from ground
                returns AND real tree positions/heights from vegetation returns.
"""
from __future__ import annotations

import io
import math
import time
from pathlib import Path

import numpy as np
from scipy import ndimage

from . import net
from .geo import BBox, LocalFrame, merc_px
from .model import DEM, Tree

TDEP = "https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/exportImage"
TNM = "https://tnmaccess.nationalmap.gov/api/v1/products"
TERRARIUM = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"


def _grid(frame: LocalFrame, extent, res):
    e_min, n_min, e_max, n_max = extent
    W = int(math.ceil((e_max - e_min) / res)) + 1
    H = int(math.ceil((n_max - n_min) / res)) + 1
    ee = e_min + np.arange(W) * res
    nn = n_min + np.arange(H) * res
    E, N = np.meshgrid(ee, nn)
    lat, lon = frame.to_latlon(E, N)
    return E, N, lat, lon


def _fill_nodata(z, bad):
    if not bad.any():
        return z
    if bad.all():
        raise RuntimeError("elevation source returned no data for this area")
    idx = ndimage.distance_transform_edt(bad, return_distances=False, return_indices=True)
    return z[tuple(idx)]


def dem_3dep(bbox: BBox, frame: LocalFrame, extent, res=1.0) -> DEM:
    import tifffile
    s, w, n, e = bbox.south, bbox.west, bbox.north, bbox.east
    # request ~res metre pixels in geographic coords
    h_m = (n - s) * 111320
    w_m = (e - w) * 111320 * math.cos(math.radians((s + n) / 2))
    W = min(4000, int(w_m / res) + 1)
    H = min(4000, int(h_m / res) + 1)
    print(f"  3DEP DEM {W}x{H}px ...")
    raw = net.fetch(TDEP, {
        "bbox": f"{w},{s},{e},{n}", "bboxSR": 4326, "imageSR": 4326, "size": f"{W},{H}",
        "format": "tiff", "pixelType": "F32", "noData": -9999,
        "interpolation": "RSP_BilinearInterpolation", "f": "image"})
    if raw[:2] not in (b"II", b"MM"):
        raise RuntimeError("3DEP did not return a TIFF: " + raw[:200].decode("utf-8", "replace"))
    img = tifffile.imread(io.BytesIO(raw)).astype(np.float64)
    if img.ndim == 3:
        img = img[..., 0]
    img = _fill_nodata(img, (img < -1000) | ~np.isfinite(img))
    Hh, Ww = img.shape
    E, N, lat, lon = _grid(frame, extent, res)
    fx = (lon - w) / (e - w) * Ww - 0.5
    fy = (n - lat) / (n - s) * Hh - 0.5
    z = ndimage.map_coordinates(img, [fy.ravel(), fx.ravel()], order=1, mode="nearest").reshape(E.shape)
    return DEM(extent[0], extent[1], res, z)


def dem_terrarium(bbox: BBox, frame: LocalFrame, extent, res=2.0, zoom=15) -> DEM:
    from PIL import Image
    x0, y0 = merc_px(bbox.north, bbox.west, zoom)
    x1, y1 = merc_px(bbox.south, bbox.east, zoom)
    tx0, ty0, tx1, ty1 = int(x0 // 256), int(y0 // 256), int(x1 // 256), int(y1 // 256)
    print(f"  terrarium tiles z{zoom}: {(tx1 - tx0 + 1) * (ty1 - ty0 + 1)}")
    mosaic = np.zeros(((ty1 - ty0 + 1) * 256, (tx1 - tx0 + 1) * 256), dtype=np.float64)
    for ty in range(ty0, ty1 + 1):
        for tx in range(tx0, tx1 + 1):
            png = net.fetch(TERRARIUM.format(z=zoom, x=tx, y=ty))
            a = np.asarray(Image.open(io.BytesIO(png)).convert("RGB")).astype(np.float64)
            hgt = a[..., 0] * 256 + a[..., 1] + a[..., 2] / 256 - 32768
            mosaic[(ty - ty0) * 256:(ty - ty0 + 1) * 256, (tx - tx0) * 256:(tx - tx0 + 1) * 256] = hgt
    E, N, lat, lon = _grid(frame, extent, res)
    px, py = merc_px(lat, lon, zoom)
    z = ndimage.map_coordinates(mosaic, [(py - ty0 * 256 - 0.5).ravel(), (px - tx0 * 256 - 0.5).ravel()],
                                order=3, mode="nearest").reshape(E.shape)
    # terrarium is coarse: soften stair-steps
    z = ndimage.gaussian_filter(z, 1.0)
    return DEM(extent[0], extent[1], res, z)


# --- raw lidar point clouds ---------------------------------------------------

def _project_of(item):
    u = item.get("downloadLazURL") or item.get("downloadURL") or ""
    if "/Projects/" in u:
        return u.split("/Projects/")[1].split("/")[0]
    t = item.get("title", "")
    return " ".join(w for w in t.split() if not any(c.isdigit() for c in w[-4:])) or t


def find_lpc_tiles(bbox: BBox):
    """Tiles of the single newest lidar survey that covers the course."""
    res = net.fetch_json(TNM, {"datasets": "Lidar Point Cloud (LPC)", "bbox": f"{bbox.west},{bbox.south},{bbox.east},{bbox.north}",
                               "prodFormats": "LAZ", "max": 200, "outputFormat": "JSON"})
    items = res.get("items", [])
    groups = {}
    for it in items:
        bb = it.get("boundingBox") or {}
        if bb and (bb.get("maxX", 180) < bbox.west or bb.get("minX", -180) > bbox.east
                   or bb.get("maxY", 90) < bbox.south or bb.get("minY", -90) > bbox.north):
            continue
        u = it.get("downloadLazURL") or it.get("downloadURL")
        if not u:
            continue
        g = groups.setdefault(_project_of(it), {"date": "", "urls": []})
        g["date"] = max(g["date"], it.get("publicationDate", "") or "")
        if u not in g["urls"]:
            g["urls"].append(u)
    if not groups:
        return []
    name, best = max(groups.items(), key=lambda kv: (kv[1]["date"], -len(kv[1]["urls"])))
    print(f"  lidar survey: {name} ({len(best['urls'])} tiles; {len(groups)} survey(s) cover this area)")
    return best["urls"]


def _vertical_scale(crs):
    try:
        subs = crs.sub_crs_list or [crs]
        for c in subs[::-1]:
            for ax in c.axis_info:
                if ax.direction in ("up", "down") or "height" in ax.name.lower():
                    return ax.unit_conversion_factor or 1.0
        # fall back: horizontal units (many US datasets are all-feet)
        ax = subs[0].axis_info[0]
        return ax.unit_conversion_factor or 1.0
    except Exception:  # noqa: BLE001
        return 1.0


def process_lidar(files, bbox: BBox, frame: LocalFrame, extent, res=1.0, epsg=None):
    """Grid ground returns into a DEM and detect trees from vegetation returns."""
    import laspy
    from pyproj import CRS, Transformer

    e_min, n_min, e_max, n_max = extent
    W = int(math.ceil((e_max - e_min) / res)) + 1
    H = int(math.ceil((n_max - n_min) / res)) + 1
    gsum = np.zeros(H * W)
    gcnt = np.zeros(H * W)
    vmax = np.full(H * W, -1e9)
    allmin = np.full(H * W, 1e9)

    for f in files:
        print(f"  lidar: {Path(f).name}")
        with laspy.open(f) as lf:
            crs = None
            try:
                crs = lf.header.parse_crs()
            except Exception:  # noqa: BLE001
                pass
            if epsg:
                crs = CRS.from_epsg(int(epsg))
            if crs is None:
                raise SystemExit(f"{f}: no CRS in file; pass --lidar-epsg")
            horiz = crs.sub_crs_list[0] if crs.is_compound else crs
            zscale = _vertical_scale(crs)
            tr = Transformer.from_crs(horiz, "EPSG:4326", always_xy=True)
            for pts in lf.chunk_iterator(4_000_000):
                x, y, z = np.asarray(pts.x), np.asarray(pts.y), np.asarray(pts.z) * zscale
                cls = np.asarray(pts.classification)
                lon, lat = tr.transform(x, y)
                ee, nn = frame.to_local(lat, lon)
                j = np.floor((ee - e_min) / res).astype(np.int64)
                i = np.floor((nn - n_min) / res).astype(np.int64)
                ok = (i >= 0) & (i < H) & (j >= 0) & (j < W) & (cls != 7) & (cls != 18)
                if not ok.any():
                    continue
                k = i[ok] * W + j[ok]
                zc, cc = z[ok], cls[ok]
                g = cc == 2
                np.add.at(gsum, k[g], zc[g])
                np.add.at(gcnt, k[g], 1)
                v = (cc >= 3) & (cc <= 5)
                np.maximum.at(vmax, k[v], zc[v])
                np.minimum.at(allmin, k, zc)

    if gcnt.sum() == 0:
        raise SystemExit("No ground-classified (class 2) lidar points inside the course area.")
    ground = np.where(gcnt > 0, gsum / np.maximum(gcnt, 1), np.nan).reshape(H, W)
    ground = _fill_nodata(np.nan_to_num(ground, nan=0), np.isnan(ground))
    ground = ndimage.median_filter(ground, 3)
    dem = DEM(e_min, n_min, res, ground)

    # canopy height model -> individual trees (local maxima)
    chm = np.where(vmax > -1e8, vmax.reshape(H, W) - ground, 0)
    chm = ndimage.gaussian_filter(np.clip(chm, 0, 60), 0.8 / res)
    win = max(3, int(round(5 / res)) | 1)
    peaks = (chm == ndimage.maximum_filter(chm, size=win)) & (chm > 4.0)
    ii, jj = np.nonzero(peaks)
    trees = []
    for i, j in zip(ii, jj):
        h = float(chm[i, j])
        trees.append(Tree(e_min + j * res, n_min + i * res, h, max(1.5, 0.22 * h + 0.8)))
    print(f"  lidar: DEM {W}x{H} @ {res} m, {len(trees)} trees detected")
    return dem, trees


def get_elevation(source, bbox, frame, extent, res, lidar_files=None, lidar_epsg=None, cache_dir=None):
    trees = []
    if lidar_files:
        files = list(lidar_files)
        try:
            if files == ["auto"]:
                urls = find_lpc_tiles(bbox)
                if not urls:
                    print("  no USGS lidar point clouds found here; using the 3DEP elevation model instead")
                    files = []
                else:
                    print(f"  downloading {len(urls)} USGS lidar tile(s) (cached after the first time)...")
                    cache_dir = Path(cache_dir or net.CACHE / "laz")
                    files = []
                    for i, u in enumerate(urls):
                        if i:
                            time.sleep(1.0)
                        files.append(net.download_file(u, cache_dir / u.split("/")[-1].split("?")[0]))
            if files:
                return process_lidar(files, bbox, frame, extent, res, lidar_epsg)
        except SystemExit:
            raise
        except Exception as e:  # noqa: BLE001
            print(f"  ! lidar point clouds failed ({e}).")
            print("  ! Falling back to the USGS 3DEP 1 m elevation model (trees will come from OpenStreetMap).")
            print("  ! Already-downloaded tiles are kept, so 'lidar' will resume next time.")
            source = "3dep"
    if source == "3dep":
        try:
            return dem_3dep(bbox, frame, extent, res), trees
        except Exception as e:  # noqa: BLE001
            print(f"  3DEP failed ({e}); using terrarium tiles")
    return dem_terrarium(bbox, frame, extent, max(res, 2.0)), trees
