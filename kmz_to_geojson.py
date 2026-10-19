#!/usr/bin/env python3
"""Convert a KMZ/KML into sites.geojson and routes.geojson (standard library only).

    python kmz_to_geojson.py my_network.kmz

Point placemarks become sites; LineString placemarks become routes. Folders are
searched recursively and MultiGeometry is handled. Properties kept: name, description.
Writes routes.straight.geojson (the untouched source lines, which snap_routes.py reads)
and routes.geojson (a copy, so the maps work straight away).
"""
import json, sys, zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).parent


def local(tag):
    return tag.rsplit("}", 1)[-1]


def read_kml(path):
    if path.suffix.lower() == ".kmz":
        with zipfile.ZipFile(path) as z:
            name = next((n for n in z.namelist() if n.lower() == "doc.kml"), None) \
                or next(n for n in z.namelist() if n.lower().endswith(".kml"))
            return ET.fromstring(z.read(name))
    return ET.parse(path).getroot()


def parse_coords(text):
    out = []
    for tok in text.split():
        p = tok.split(",")
        if len(p) >= 2:
            out.append([float(p[0]), float(p[1])])  # drop altitude
    return out


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    root = read_kml(Path(sys.argv[1]))
    sites, routes = [], []
    for pm in (e for e in root.iter() if local(e.tag) == "Placemark"):
        props = {"name": "", "description": ""}
        for child in pm:
            if local(child.tag) in props:
                props[local(child.tag)] = (child.text or "").strip()
        points, lines = [], []
        for g in pm.iter():
            t = local(g.tag)
            if t in ("Point", "LineString"):
                c = next((x for x in g if local(x.tag) == "coordinates"), None)
                if c is not None and c.text:
                    (points if t == "Point" else lines).append(parse_coords(c.text))
        if points:
            sites.append({"type": "Feature", "properties": props,
                          "geometry": {"type": "MultiPoint", "coordinates": [p[0] for p in points if p]}})
        if lines:
            routes.append({"type": "Feature", "properties": props,
                           "geometry": {"type": "MultiLineString", "coordinates": [l for l in lines if len(l) > 1]}})

    def dump(name, feats, fname):
        (HERE / fname).write_text(json.dumps({"type": "FeatureCollection", "name": name, "features": feats}, indent=1) + "\n")

    dump("sites", sites, "sites.geojson")
    dump("routes", routes, "routes.straight.geojson")
    dump("routes", routes, "routes.geojson")
    print(f"{len(sites)} sites, {len(routes)} routes. Next: python snap_routes.py")


if __name__ == "__main__":
    main()
