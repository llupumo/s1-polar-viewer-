# Sentinel-1 EW polar viewer

A small web viewer for preprocessed **Sentinel-1 EW GRDM** scenes in the **North Polar Stereographic projection (EPSG:3413)**. A Python script turns the GeoTIFFs into lightweight map overlays; a static web page lets you browse them by time period.

The viewer has no external dependencies (no CDN, no map library), so it works offline once built.

## Features

- Scenes reprojected to EPSG:3413 (NSIDC Sea Ice Polar Stereographic North: 70°N, 45°W)
- Choose a **period length in days** and slide it forward or back with arrows (e.g. 1–4 Mar → 2–5 Mar)
- Per-scene toggles, opacity slider, pan and zoom, live lat/lon and x/y readout
- Latitude/longitude graticule and an optional **land layer** (Natural Earth)

## Quick start

```bash
git clone <this repo> && cd <this repo>
pip install -r requirements.txt

# 1. Build overlays from your GeoTIFFs (writes site/data/*.png and site/data/index.json)
python build_quicklooks.py /path/to/s1_preprocessed/2020/03 --jobs 8

# 2. (Optional) Download land polygons for the Land layer (needs internet, once)
python fetch_land.py

# 3. Serve the site and open http://localhost:8000
python serve.py
```

Do not open `site/index.html` by double-clicking it: the page loads `data/index.json`, which browsers block for `file://` pages.

## Using the viewer

| Control | What it does |
|---|---|
| **Days** | Length of the period shown (1–60 days) |
| **Step** | How many days the arrows move. `1` = sliding window (1–4 Mar → 2–5 Mar); equal to *Days* = back-to-back blocks |
| ◀ / ▶ or ← / → keys | Previous / next period |
| Date box | Jump to a start date |
| Scene checkboxes | Show or hide individual scenes (kept as you slide) |
| **Fit** | Zoom to the scenes currently shown |
| Drag / scroll / double-click a scene | Pan / zoom / zoom to that scene |

## Expected input

The converter was written for scenes with this layout:

- File names like `S1A_EW_GRDM_1SDH_20200301T024911_20200301T025016_031476_039FDC_8FE8.tiff` (start/end times are read from the name)
- `uint8`, two bands: **band 1** backscatter already scaled to 0–255, **band 2** a validity mask (1 = valid)
- Georeferencing as a grid of GeoTIFF tiepoints in a scene-specific stereographic CRS

Other layouts may need changes in `build_quicklooks.py`. Inspect a file with `gdalinfo` if a scene fails.

## build_quicklooks.py options

| Option | Default | Meaning |
|---|---|---|
| `--res` | `400` | Output pixel size in metres (source is about 80 m). Larger = smaller files and less browser memory |
| `--jobs` | `4` | Parallel worker processes |
| `--out` | `./site` | Output folder |

For the full archive, run it as a batch job rather than on a login node.

## How it works

1. Tiepoints are converted from each scene's oblique stereographic CRS to latitude/longitude, then to EPSG:3413 (WGS84 ellipsoid formulas, implemented directly, no GDAL/PROJ needed).
2. Each scene is block-averaged, resampled onto a regular 3413 grid and saved as a transparent PNG; the bounding box goes into `site/data/index.json`.
3. `site/index.html` draws the PNGs on an HTML canvas and handles the projection maths for the graticule, land and cursor readout.

## Project layout

```
build_quicklooks.py   GeoTIFF -> PNG overlays + index.json
fetch_land.py         Natural Earth land polygons -> site/data/land.json
serve.py              Local web server with caching disabled
requirements.txt
site/
  index.html          The viewer
  data/               Generated files (git-ignored)
```

## Notes and limitations

- Overlays are 8-bit **quicklooks** for visual inspection, not for quantitative analysis. Use the original GeoTIFFs for that.
- A thin strip of saturated pixels along swath edges is trimmed; very small features at the edges may be lost.
- Each displayed scene uses roughly 7 MB of browser memory (at 400 m). Very long periods can be slow; use shorter periods or a larger `--res`.
- The default 50 m Natural Earth coastline is coarse (about 1:50 million) and will not match fine coastal detail in the SAR imagery. Use `python fetch_land.py --res 10m` for more detail.

## Troubleshooting

- **Page shows old content:** hard-refresh (Ctrl/Cmd+Shift+R) or use `serve.py`, which disables caching.
- **"Could not load data/index.json":** run the server from this project (`python serve.py`), and make sure step 1 produced `site/data/index.json`.
- **Land checkbox greyed out:** run `python fetch_land.py`. If the machine has no internet, save the GeoJSON from the printed URL and run `python fetch_land.py --input <file>`.
- **Red text in the sidebar:** it names the failing file or error.

## Data and credits

- Contains modified Copernicus Sentinel data (2020), processed by you. Check the acknowledgement wording required for your data source.
- Land polygons: [Natural Earth](https://www.naturalearthdata.com/), public domain.

## License

The code in this repository is released under the [MIT License](LICENSE). The licence covers the code only: Sentinel data and Natural Earth land polygons keep their own terms (see Data and credits).
