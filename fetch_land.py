#!/usr/bin/env python3
"""Download Natural Earth land polygons (public domain) and write site/data/land.json
for the viewer's Land layer. Keeps only land north of --min-lat. Stdlib only.

  python fetch_land.py                 # 50m resolution (good default)
  python fetch_land.py --res 10m       # finer coastline, bigger file
  python fetch_land.py --input ne_50m_land.geojson   # if this machine cannot download
"""
import argparse, json, urllib.request
from pathlib import Path

URL = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_{res}_land.geojson"


def clip_north(ring, lat0):
    """Sutherland-Hodgman clip of a lon/lat ring to lat >= lat0."""
    out = []
    for i in range(len(ring)):
        a, b = ring[i - 1], ring[i]
        ina, inb = a[1] >= lat0, b[1] >= lat0
        if ina != inb:
            t = (lat0 - a[1]) / (b[1] - a[1])
            p = (a[0] + t * (b[0] - a[0]), lat0)
            if inb:
                out.append(p)
            else:
                out.append(p)
        if inb:
            out.append(b)
    # the loop above appends the entry point before b and the exit point alone; order is correct
    return out


def densify(ring, step=1.0):
    out = []
    for i in range(len(ring)):
        a, b = ring[i - 1], ring[i]
        n = int(max(abs(b[0] - a[0]), abs(b[1] - a[1])) // step)
        for k in range(1, n + 1):
            out.append((a[0] + (b[0] - a[0]) * k / (n + 1), a[1] + (b[1] - a[1]) * k / (n + 1)))
        out.append(b)
    return out


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--res", default="50m", choices=["10m", "50m", "110m"])
    p.add_argument("--min-lat", type=float, default=50)
    p.add_argument("--input", type=Path, help="local GeoJSON instead of downloading")
    p.add_argument("--out", type=Path, default=Path(__file__).parent / "site" / "data" / "land.json")
    a = p.parse_args()
    if a.input:
        gj = json.loads(a.input.read_text())
    else:
        url = URL.format(res=a.res)
        print("Downloading", url)
        try:
            gj = json.load(urllib.request.urlopen(url, timeout=120))
        except Exception as e:
            raise SystemExit(f"Download failed ({e}).\nOpen the URL above in a browser, save the file, then run:\n  python fetch_land.py --input <saved file>")
    rings = []
    for f in gj["features"]:
        g = f["geometry"]
        polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"] if g["type"] == "MultiPolygon" else []
        for poly in polys:
            for ring in poly:  # exterior + holes (drawn with even-odd fill)
                ring = [tuple(c[:2]) for c in ring]
                if ring[0] == ring[-1]:
                    ring = ring[:-1]
                ring = clip_north(ring, a.min_lat)
                if len(ring) < 3:
                    continue
                ring = densify(ring)
                rings.append([round(v, 3) for c in ring for v in c])
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps({"minLat": a.min_lat, "rings": rings}, separators=(",", ":")))
    print(f"{len(rings)} rings, {sum(map(len, rings)) // 2} points -> {a.out} ({a.out.stat().st_size / 1e6:.1f} MB)")
