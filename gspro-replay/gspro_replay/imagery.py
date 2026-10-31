"""Aerial imagery tiles, stitched and warped onto the local metre grid.

OpenStreetMap itself has no satellite layer; OSM editors use third-party aerial
imagery. Default here is Esri World Imagery (the same layer offered in the OSM
iD editor). Any XYZ template can be passed with --imagery-url.
"""
from __future__ import annotations

import io
import math

import numpy as np
from scipy import ndimage

from . import net
from .geo import BBox, LocalFrame, merc_px
from .model import Imagery

PROVIDERS = {
    "esri": ("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
             "Imagery: Esri, Maxar, Earthstar Geographics"),
}


def fetch_imagery(bbox: BBox, frame: LocalFrame, extent, zoom=18, url=None, max_px=4096) -> Imagery:
    from PIL import Image
    tmpl, attrib = PROVIDERS["esri"] if not url else (url, "Imagery: custom source")
    x0, y0 = merc_px(bbox.north, bbox.west, zoom)
    x1, y1 = merc_px(bbox.south, bbox.east, zoom)
    tx0, ty0, tx1, ty1 = int(x0 // 256), int(y0 // 256), int(x1 // 256), int(y1 // 256)
    n_tiles = (tx1 - tx0 + 1) * (ty1 - ty0 + 1)
    if n_tiles > 900 and zoom > 15:
        return fetch_imagery(bbox, frame, extent, zoom - 1, url, max_px)
    print(f"  imagery z{zoom}: {n_tiles} tiles")
    mosaic = np.zeros(((ty1 - ty0 + 1) * 256, (tx1 - tx0 + 1) * 256, 3), dtype=np.uint8)
    for ty in range(ty0, ty1 + 1):
        for tx in range(tx0, tx1 + 1):
            try:
                b = net.fetch(tmpl.format(z=zoom, x=tx, y=ty), quiet=True)
                a = np.asarray(Image.open(io.BytesIO(b)).convert("RGB"))
                mosaic[(ty - ty0) * 256:(ty - ty0 + 1) * 256, (tx - tx0) * 256:(tx - tx0 + 1) * 256] = a[:256, :256]
            except Exception:  # noqa: BLE001
                pass
    e_min, n_min, e_max, n_max = extent
    span = max(e_max - e_min, n_max - n_min)
    res = max(span / max_px, 156543.03 * math.cos(math.radians(frame.lat0)) / 2 ** zoom)
    W = int((e_max - e_min) / res)
    H = int((n_max - n_min) / res)
    ee = e_min + (np.arange(W) + 0.5) * res
    nn = n_max - (np.arange(H) + 0.5) * res
    E, N = np.meshgrid(ee, nn)
    lat, lon = frame.to_latlon(E, N)
    px, py = merc_px(lat, lon, zoom)
    cy, cx = (py - ty0 * 256 - 0.5).ravel(), (px - tx0 * 256 - 0.5).ravel()
    out = np.stack([ndimage.map_coordinates(mosaic[..., c], [cy, cx], order=1, mode="nearest").reshape(H, W)
                    for c in range(3)], axis=-1).astype(np.uint8)
    return Imagery(out, e_min, e_max, n_min, n_max, attrib)
