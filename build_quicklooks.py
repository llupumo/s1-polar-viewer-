#!/usr/bin/env python3
"""Reproject preprocessed Sentinel-1 EW GeoTIFFs to North Polar Stereographic
(EPSG:3413) PNG overlays and write site/data/index.json for the web viewer.

  python build_quicklooks.py /nird/datapeak/NS2993K/seachu/s1_preprocessed/2020/03 --jobs 8

Input layout (from your sample): uint8, 2 bands = band 1 backscatter (s0_nn, already
scaled 0-255), band 2 = validity mask (1 = valid). Georeferencing = a grid of
ModelTiepoints in a scene-specific oblique stereographic CRS.
Needs: tifffile numpy scipy opencv-python-headless pillow   (no GDAL required)
"""
import argparse, json, re
from datetime import datetime
from multiprocessing import Pool
from pathlib import Path

import cv2
import numpy as np
import tifffile
from PIL import Image
from scipy.interpolate import LinearNDInterpolator

NAME = re.compile(r"(S1[AB])_EW_GRDM_1S(\w\w)_(\d{8}T\d{6})_(\d{8}T\d{6})")


class Ellipsoid:
    def __init__(self, a, invf):
        self.a = a
        f = 1 / invf
        self.e = np.sqrt(f * (2 - f))

    def conformal(self, phi):
        s = np.sin(phi)
        return 2 * np.arctan(np.tan(np.pi / 4 + phi / 2) * ((1 - self.e * s) / (1 + self.e * s)) ** (self.e / 2)) - np.pi / 2

    def from_conformal(self, chi):
        phi = chi
        for _ in range(8):
            s = np.sin(phi)
            phi = 2 * np.arctan(np.tan(np.pi / 4 + chi / 2) * ((1 + self.e * s) / (1 - self.e * s)) ** (self.e / 2)) - np.pi / 2
        return phi


def oblique_stere_inverse(x, y, ell, lat0, lon0, k0):
    """Scene CRS (GeoTIFF CT_Stereographic) -> geodetic lat/lon, radians."""
    c1 = ell.conformal(lat0)
    m1 = np.cos(lat0) / np.sqrt(1 - ell.e ** 2 * np.sin(lat0) ** 2)
    rho = np.hypot(x, y)
    c = 2 * np.arctan(rho * np.cos(c1) / (2 * ell.a * k0 * m1))
    rho = np.where(rho == 0, 1e-12, rho)
    chi = np.arcsin(np.cos(c) * np.sin(c1) + y * np.sin(c) * np.cos(c1) / rho)
    lam = lon0 + np.arctan2(x * np.sin(c), rho * np.cos(c1) * np.cos(c) - y * np.sin(c1) * np.sin(c))
    return ell.from_conformal(chi), lam


def to_epsg3413(phi, lam, ell):
    """Geodetic -> NSIDC polar stereographic north (lat_ts 70, lon_0 -45)."""
    lc, l0 = np.radians(70), np.radians(-45)
    t = lambda p: np.tan(np.pi / 4 - p / 2) / (((1 - ell.e * np.sin(p)) / (1 + ell.e * np.sin(p))) ** (ell.e / 2))
    mc = np.cos(lc) / np.sqrt(1 - ell.e ** 2 * np.sin(lc) ** 2)
    r = ell.a * mc * t(phi) / t(lc)
    return r * np.sin(lam - l0), -r * np.cos(lam - l0)


def process(job):
    path, out, res = job
    m = NAME.search(path.name)
    if not m:
        return None
    with tifffile.TiffFile(path) as tf:
        page = tf.pages[0]
        gk = tf.geotiff_metadata
        img = page.asarray()
    tp = np.array(gk["ModelTiepoint"], float)  # col, row, 0, X, Y, 0
    if len(tp) < 6 or "ProjCenterLatGeoKey" not in gk:
        raise ValueError(f"{path.name}: expected a tiepoint grid + stereographic CRS; send gdalinfo output")
    ell = Ellipsoid(gk["GeogSemiMajorAxisGeoKey"], gk["GeogInvFlatteningGeoKey"])
    phi, lam = oblique_stere_inverse(tp[:, 3], tp[:, 4], ell,
                                     np.radians(gk["ProjCenterLatGeoKey"]),
                                     np.radians(gk["ProjCenterLongGeoKey"]),
                                     gk.get("ProjScaleAtNatOriginGeoKey", 1.0))
    X, Y = to_epsg3413(phi, lam, ell)

    # source pixel size from neighbouring tiepoints -> decimation factor
    cols = np.unique(tp[:, 0])
    row0 = tp[tp[:, 1] == tp[0, 1]]
    d = np.hypot(*(np.diff(np.c_[X, Y][: len(row0)], axis=0)).T).mean() / np.diff(row0[:, 0]).mean()
    f = max(1, int(round(res / d)))

    if img.ndim == 3:
        val, mask = img[..., 0].astype(np.float32), (img[..., -1] > 0).astype(np.float32)
    else:
        val, mask = img.astype(np.float32), (img > 0).astype(np.float32)
    # drop the saturated (255) border artefact: saturated pixels within ~80 px of the swath edge
    pad = cv2.copyMakeBorder(mask.astype(np.uint8), 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=0)  # image border counts as edge
    dist = cv2.distanceTransform(pad, cv2.DIST_L2, 3)[1:-1, 1:-1]
    mask[(dist <= 80) & (val >= 255)] = 0
    mask = cv2.erode(mask, np.ones((9, 9), np.uint8))
    H, W = val.shape
    h2, w2 = H // f, W // f
    num = cv2.resize(val * mask, (w2, h2), interpolation=cv2.INTER_AREA)
    den = cv2.resize(mask, (w2, h2), interpolation=cv2.INTER_AREA)
    small = np.where(den > 0, num / np.maximum(den, 1e-6), 0).astype(np.float32)

    # destination grid in EPSG:3413, then look up source (col,row) for each cell centre
    xmin, xmax, ymin, ymax = X.min(), X.max(), Y.min(), Y.max()
    w, h = int(np.ceil((xmax - xmin) / res)), int(np.ceil((ymax - ymin) / res))
    gx = xmin + (np.arange(w) + 0.5) * res
    gy = ymax - (np.arange(h) + 0.5) * res
    GX, GY = np.meshgrid(gx, gy)
    pts = np.c_[X, Y]
    col = LinearNDInterpolator(pts, tp[:, 0])(GX, GY)
    row = LinearNDInterpolator(pts, tp[:, 1])(GX, GY)
    inside = np.isfinite(col) & np.isfinite(row)
    mx = ((np.nan_to_num(col, nan=-1) + 0.5) / f - 0.5).astype(np.float32)
    my = ((np.nan_to_num(row, nan=-1) + 0.5) / f - 0.5).astype(np.float32)
    g = cv2.remap(small, mx, my, cv2.INTER_LINEAR, borderValue=0)
    a = cv2.remap(den, mx, my, cv2.INTER_LINEAR, borderValue=0)
    alpha = ((a > 0.5) & inside).astype(np.uint8) * 255

    rgba = np.dstack([np.clip(g, 0, 255).astype(np.uint8)] * 3 + [alpha])
    png = out / "data" / (path.stem + ".png")
    Image.fromarray(rgba, "RGBA").save(png, optimize=True)
    iso = lambda s: datetime.strptime(s, "%Y%m%dT%H%M%S").isoformat()
    return dict(file="data/" + png.name, sat=m[1], pol={"DH": "HH+HV", "DV": "VV+VH"}.get(m[2], m[2]), start=iso(m[3]), end=iso(m[4]),
                extent=[float(xmin), float(ymax - h * res), float(xmin + w * res), float(ymax)])


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("indir", type=Path)
    p.add_argument("--out", type=Path, default=Path(__file__).parent / "site")
    p.add_argument("--res", type=float, default=400, help="output pixel size in metres (source is ~80 m)")
    p.add_argument("--jobs", type=int, default=4)
    a = p.parse_args()
    (a.out / "data").mkdir(parents=True, exist_ok=True)
    files = sorted(a.indir.glob("*.tif*"))
    items = []
    with Pool(a.jobs) as pool:
        for i, r in enumerate(pool.imap_unordered(process, [(f, a.out, a.res) for f in files]), 1):
            if r:
                items.append(r)
            print(f"{i}/{len(files)}", end="\r", flush=True)
    items.sort(key=lambda r: r["start"])
    (a.out / "data" / "index.json").write_text(json.dumps(items))
    print(f"\n{len(items)} scenes -> {a.out}")
