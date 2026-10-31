"""Plain data containers shared by the pipeline stages."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .geo import LocalFrame

# Surface classes used for the low-poly mesh (index into viewer palette)
CLS_OUT, CLS_ROUGH, CLS_FAIRWAY, CLS_GREEN, CLS_TEE, CLS_BUNKER, CLS_WATER, CLS_WOOD, CLS_PATH, CLS_BUILDING = range(10)
CLASS_NAMES = ["out", "rough", "fairway", "green", "tee", "bunker", "water", "wood", "path", "building"]


@dataclass
class Feature:
    cls: int
    ring: np.ndarray            # (N,2) local e,n metres, closed
    holes: list = field(default_factory=list)  # inner rings
    tags: dict = field(default_factory=dict)


@dataclass
class Hole:
    number: int
    par: int
    path: np.ndarray            # (N,2) tee -> green centre line
    tee: np.ndarray             # (2,)
    pin: np.ndarray             # (2,)
    green: Optional[np.ndarray] = None  # ring
    yards: Optional[float] = None


@dataclass
class Tree:
    e: float
    n: float
    height: float
    radius: float
    kind: int = 0               # 0 broadleaf, 1 conifer


@dataclass
class DEM:
    """Regular grid in local metres. z[i, j] at (e0 + j*res, n0 + i*res)."""
    e0: float
    n0: float
    res: float
    z: np.ndarray

    def sample(self, e, n):
        e = np.asarray(e, dtype=float)
        n = np.asarray(n, dtype=float)
        fj = np.clip((e - self.e0) / self.res, 0, self.z.shape[1] - 1.001)
        fi = np.clip((n - self.n0) / self.res, 0, self.z.shape[0] - 1.001)
        j0 = np.floor(fj).astype(int)
        i0 = np.floor(fi).astype(int)
        tj, ti = fj - j0, fi - i0
        z = self.z
        return ((z[i0, j0] * (1 - tj) + z[i0, j0 + 1] * tj) * (1 - ti)
                + (z[i0 + 1, j0] * (1 - tj) + z[i0 + 1, j0 + 1] * tj) * ti)


@dataclass
class Imagery:
    """RGB image resampled to the local frame. Pixel (0,0) = (e_min, n_max)."""
    img: np.ndarray             # (H,W,3) uint8
    e_min: float
    e_max: float
    n_min: float
    n_max: float
    attribution: str = ""


@dataclass
class Course:
    name: str
    frame: LocalFrame
    extent: tuple               # (e_min, n_min, e_max, n_max)
    dem: DEM
    features: list
    holes: list
    trees: list = field(default_factory=list)
    imagery: Optional[Imagery] = None
    attribution: list = field(default_factory=list)
