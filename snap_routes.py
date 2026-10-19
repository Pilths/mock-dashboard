#!/usr/bin/env python3
"""Snap the straight-line routes to real roads using an OSRM server.

Reads routes.straight.geojson (created from routes.geojson on first run, so the
original hand-drawn lines are never lost) and writes routes.geojson with the
road geometry. Standard library only.

    python3 snap_routes.py                 # endpoints only, public OSRM demo server
    python3 snap_routes.py --via           # also force the route through the original vertices
    python3 snap_routes.py --server http://localhost:5000   # self-hosted OSRM

The public demo server is for light use only. For anything heavier, run your own
OSRM (docker run osrm/osrm-routed) with a Malaysia extract from Geofabrik.
"""
import argparse, json, shutil, ssl, sys, time, urllib.request
from pathlib import Path

HERE = Path(__file__).parent
SRC = HERE / "routes.straight.geojson"
OUT = HERE / "routes.geojson"


def ssl_context():
    # Python 3.13+ enables strict X.509 checks that many corporate HTTPS-inspection
    # proxies fail ("Basic Constraints of CA cert not marked critical"). Turn off only
    # that strictness; certificate and hostname verification stay on.
    ctx = ssl.create_default_context()
    ctx.verify_flags &= ~getattr(ssl, "VERIFY_X509_STRICT", 0)
    return ctx


def snap(server, profile, coords):
    path = ";".join(f"{x},{y}" for x, y in coords)
    url = f"{server}/route/v1/{profile}/{path}?overview=full&geometries=geojson&continue_straight=false"
    with urllib.request.urlopen(url, timeout=30, context=ssl_context()) as r:
        data = json.load(r)
    if data.get("code") != "Ok":
        raise RuntimeError(data.get("message") or data.get("code"))
    route = data["routes"][0]
    return route["geometry"]["coordinates"], route["distance"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="https://router.project-osrm.org")
    ap.add_argument("--profile", default="driving")
    ap.add_argument("--via", action="store_true", help="route through every original vertex, not just the endpoints")
    a = ap.parse_args()

    if not SRC.exists():
        shutil.copy(OUT, SRC)
    fc = json.loads(SRC.read_text())

    for f in fc["features"]:
        line = f["geometry"]["coordinates"][0]
        pts = line if a.via else [line[0], line[-1]]
        try:
            snapped, dist = snap(a.server.rstrip("/"), a.profile, pts)
        except Exception as e:
            sys.exit(f"{f['properties']['name']}: routing failed ({e}); routes.geojson left unchanged")
        # keep the exact site coordinates at both ends so the line touches the markers
        snapped = [line[0]] + snapped + [line[-1]]
        f["geometry"]["coordinates"] = [snapped]
        f["properties"]["length_km"] = round(dist / 1000, 2)
        print(f"{f['properties']['name']}: {len(snapped)} points, {dist/1000:.1f} km")
        time.sleep(1)  # be polite to the public server

    OUT.write_text(json.dumps(fc, indent=1) + "\n")
    print("wrote", OUT.name)


if __name__ == "__main__":
    main()
