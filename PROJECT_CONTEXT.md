# Mock fibre dashboard: project context

Context for an AI assistant (or a person) picking up this project. It covers what exists, how it works, and what is still open.

## Goal

Compare three web map options for showing a small fibre network (sites and routes) in the Kajang / KL area of Malaysia:

1. Google Maps JavaScript API
2. Leaflet with OpenStreetMap raster tiles
3. MapLibre GL JS with the OpenFreeMap vector basemap, plus a toggle to OSM raster tiles

## Environment

- Windows with WSL2, running Ubuntu 26.04
- Project folder: `~/project/mock-dashboard`
- Docker comes from Docker Desktop on Windows, through its WSL integration. The user is in the `docker` group.
- Installed through apt: unzip 6.00, zip 3.0, curl 8.18.0, git 2.53.0, python3 3.14.4, pip 25.1.1, GDAL 3.12.2 (`ogr2ogr`, `ogrinfo`), postgresql-client 18.6 (`psql`). Node is also available.

## Architecture

```
mock_fibre.kmz -> unzip -> kml/doc.kml -> ogr2ogr -> PostGIS (database "geo") -> ogr2ogr -> sites.geojson, routes.geojson
                                          (one-time build step)

Browser <- python3 -m http.server 8000 (serves .html and .geojson as static files)
  - loads the map library from the unpkg CDN (pinned versions)
  - loads basemap tiles from tile.openstreetmap.org or tiles.openfreemap.org
  - fetches routes.geojson and sites.geojson and draws them on top of the basemap
```

The maps don't need a database at runtime. PostGIS is used only to build the GeoJSON files, which are static. Any static host can serve the pages: GitHub Pages, Netlify, S3 or nginx.

A database at runtime is only needed if the data becomes live, large or query-driven. In that case, put an API in front of PostGIS: `pg_featureserv` for GeoJSON, `pg_tileserv` or Martin for vector tiles, or a custom backend.

## Data

The source file is `mock_fibre.kmz`, which contains a single `doc.kml`.

- Folder `Sites` holds 5 points. `description` is either "Core site" or "Aggregation".
  - Kajang Hub, Bangi POP, Cheras POP, KL Central, Putrajaya POP
- Folder `Routes` holds 4 lines. `description` looks like "Underground, 24 cores" or "Aerial, 48 cores".
  - Kajang-Bangi (Underground), Kajang-Cheras (Aerial), Cheras-KL Central (Underground), Bangi-Putrajaya (Aerial)

Exported GeoJSON:

- Coordinates are WGS84 (EPSG:4326, RFC 7946).
- Each feature has only `name` and `description` as properties.
- Because of `PROMOTE_TO_MULTI`, sites are `MultiPoint` and routes are `MultiLineString`.

## PostGIS

- Container `postgis`, image `postgis/postgis:16-3.4` (PostGIS 3.4.3, PostgreSQL 16)
- Port 5432, user `postgres`, password `postgres`
- Named volume `pgdata`, so data persists. Restart policy is `unless-stopped`.
- Database `geo` has the `postgis` extension enabled.
- Tables `sites` (5 rows) and `routes` (4 rows), with the geometry column `geom`.
  - The tables also have the LIBKML columns `id`, `timestamp`, `begin`, `end`, `altitudemode`, `tessellate`, `extrude`, `visibility`, `draworder` and `icon`.

Commands used:

```bash
docker volume create pgdata
docker run -d --name postgis -e POSTGRES_PASSWORD=postgres -p 5432:5432 \
  -v pgdata:/var/lib/postgresql/data --restart unless-stopped postgis/postgis:16-3.4

export PGPASSWORD=postgres
psql -h localhost -U postgres -c "CREATE DATABASE geo"
psql -h localhost -U postgres -d geo -c "CREATE EXTENSION IF NOT EXISTS postgis; SELECT postgis_full_version();"

unzip -o mock_fibre.kmz -d kml
ogr2ogr -f PostgreSQL "PG:host=localhost dbname=geo user=postgres password=postgres" kml/doc.kml \
  -lco GEOMETRY_NAME=geom -nlt PROMOTE_TO_MULTI -dim XY -overwrite

for t in sites routes; do
  ogr2ogr -f GeoJSON $t.geojson "PG:host=localhost dbname=geo user=postgres password=postgres" \
    -sql "SELECT name, description, geom FROM $t" -nln $t -lco RFC7946=YES
done
```

## Files

| File | Purpose |
|---|---|
| `mock_fibre.kmz` | Source data |
| `kml/doc.kml` | KML unzipped from the KMZ |
| `sites.geojson`, `routes.geojson` | Exported from PostGIS. All map pages load these files. |
| `index.html` | Links to the three map pages |
| `osm.html` | Leaflet 1.9.4 with OSM raster tiles |
| `maplibre.html` | MapLibre GL JS 4.7.1 with the OpenFreeMap `liberty` style, plus a button to switch to an inline OSM raster style |
| `google.html` | Google Maps JS API (`v=quarterly`, the closest Google offers to pinning). Not active, see below. |

Each page is one self-contained HTML file with no build step. All pages behave the same way:

- **Route colours:** routes are coloured by checking `description` for "underground" (case-insensitive).
  - Underground routes are brown `#8B4513` and solid.
  - Aerial routes are blue `#1E88E5` and dashed.
- **Site markers:** sites are red circles with a permanent name label.
- **Popups:** clicking a site or route shows a popup with its name and description. Text is HTML-escaped.
- **Zoom:** the view fits the bounds of all features.
- **Legend:** each page has a small legend.

Page-specific notes:

- **MapLibre:**
  - Calling `setStyle` removes custom layers, so data layers are re-added on every `style.load` event.
  - Dashes can't be data-driven in v4, so Underground and Aerial are separate layers with filters.
  - Labels use the OpenFreeMap glyphs (`Noto Sans Regular`).
- **Google:**
  - Uses the Data layer.
  - The Data layer can't draw dashed lines, so Aerial differs by colour only.

## Status

- Working: `osm.html` and `maplibre.html`. Their inline JS passed `node --check` and all files return HTTP 200 from the server. They have not yet been checked visually in a browser.
- On hold: `google.html`. The user chose to skip Google Maps because the API needs a billing account with card verification. The file stays as it is. With the placeholder key `YOUR_API_KEY` it shows a "set your key" message. To turn it on, set `GOOGLE_MAPS_API_KEY` at the top of the file.
- Not persistent: the web server ran in the background from a Claude Code session and stops when that session ends. To restart it:
  `cd ~/project/mock-dashboard && python3 -m http.server 8000`, then open http://localhost:8000/
- To remove the Docker setup: `docker rm -f postgis && docker volume rm pgdata`. This deletes the database data.

## API and service limits

| Service | Key needed | Limits |
|---|---|---|
| OSM tiles (`tile.openstreetmap.org`) | No | Run by volunteers. The tile usage policy has no fixed quota, but it bans heavy use, bulk downloading or prefetching, and use without attribution, and offenders can be blocked. Good for dev and light use, not production traffic. |
| OpenFreeMap | No | Free, no stated quota, no sign-up. Attribution required, no SLA, funded by donations. Can be self-hosted. |
| Google Maps JS API | Yes, with billing | Needs a billing account. Under 2025 pricing there is a free monthly allowance (about 10k Dynamic Maps loads), then pay per use. |
| Leaflet / MapLibre | No | Open-source browser libraries with no usage limits. |
| unpkg CDN | No | Free, no SLA. For production, serve the library files yourself. |

## Tech stack summary

- **Build and data:** GDAL `ogr2ogr`, PostGIS 3.4 on PostgreSQL 16 in Docker, psql
- **Data format:** GeoJSON in WGS84
- **Frontend:** plain HTML and JS, Leaflet 1.9.4, MapLibre GL JS 4.7.1, and the Google Maps JS API (inactive)
- **Serving:** `python3 -m http.server` for development. Use nginx or a static host for production.

## Recommendation

For production without API keys or a card, use MapLibre + OpenFreeMap (or self-hosted tiles) + static GeoJSON. Add PostGIS behind an API only if the data needs to be live or grows large.
