import time

from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import requests

from shapely.geometry import shape
from pyproj import Geod

from boundary_checker import BoundaryChecker

app = FastAPI(
    title="PFZ Finder API",
    description="Find the nearest Potential Fishing Zone using INCOIS PFZ data"
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

INCOIS_URL = "https://incois.gov.in/geoserver/PFZ_Automation/ows"

# WGS84 ellipsoid geodesic calculator
# distances directly on lat/lon points
geod = Geod(ellps="WGS84")

_cache = {"data": None, "timestamp": 0}
CACHE_TTL_SECONDS = 3600  # refresh once per hour


def get_pfz_data():
    now = time.time()

    if _cache["data"] is not None and (now - _cache["timestamp"]) < CACHE_TTL_SECONDS:
        return _cache["data"]

    params = {
        "service": "WFS",
        "version": "1.1.0",
        "request": "GetFeature",
        "typeName": "PFZ_Automation:pfzlines",
        "outputFormat": "application/json",
        "srsName": "EPSG:4326",
    }

    try:
        response = requests.get(INCOIS_URL, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

    except requests.RequestException as e:
        raise HTTPException(
            status_code=502,
            detail=f"Unable to fetch PFZ data from INCOIS: {str(e)}"
        )

    _cache["data"] = data
    _cache["timestamp"] = now

    return data


def extract_coords(geom):
    geom_type = geom.geom_type

    if geom_type in ("Point", "LineString", "LinearRing"):
        return list(geom.coords)

    elif geom_type in ("MultiPoint", "MultiLineString"):
        return [pt for part in geom.geoms for pt in part.coords]

    elif geom_type == "Polygon":
        return list(geom.exterior.coords)

    elif geom_type == "MultiPolygon":
        return [pt for part in geom.geoms for pt in part.exterior.coords]

    else:
        return []


def find_nearest_pfz(latitude: float, longitude: float, data):
    nearest_pfz = None
    minimum_distance = float("inf")

    for feature in data.get("features", []):
        geometry = feature.get("geometry")

        if not geometry:
            continue

        try:
            pfz = shape(geometry)
            coords = extract_coords(pfz)

            for lon2, lat2 in coords:
                _, _, distance_m = geod.inv(longitude, latitude, lon2, lat2)

                if distance_m < minimum_distance:
                    minimum_distance = distance_m

                    nearest_pfz = {
                        "pfz_id": feature.get("id"),
                        "distance_km": round(distance_m / 1000, 3),
                        "nearest_point": {
                            "latitude": round(lat2, 6),
                            "longitude": round(lon2, 6)
                        },
                        "properties": feature.get("properties", {})
                    }

        except Exception:
            continue

    return nearest_pfz


@app.get("/")
def root():
    return {"message": "PFZ Finder API is running. See /docs for usage."}


@app.get("/nearest-pfz")
def nearest_pfz(
    latitude: float = Query(..., ge=-90, le=90,
                            description="Fisherman's latitude"),
    longitude: float = Query(..., ge=-180, le=180,
                             description="Fisherman's longitude")
):
    data = get_pfz_data()
    result = find_nearest_pfz(latitude, longitude, data)

    if result is None:
        raise HTTPException(status_code=404, detail="No PFZ found")

    return {
        "user_location": {"latitude": latitude, "longitude": longitude},
        "nearest_pfz": result
    }


print("Loading boundary/safety checker (MPA, EEZ, IMBL, bathymetry)...")
checker = BoundaryChecker(
    "india-mpas.geojson",
    "india-eez.geojson",
    "imbl.geojson",
    None  # auto-detects the ETOPO .tif by filename
)
print("Boundary checker ready.")


@app.get("/safety-check")
def safety_check(latitude: float, longitude: float):
    return checker.check_point(latitude=latitude, longitude=longitude)


@app.get("/full-report")
def full_report(latitude: float, longitude: float):
    """Combines nearest-PFZ + full safety check in one call."""
    pfz_data = get_pfz_data()
    pfz_result = find_nearest_pfz(latitude, longitude, pfz_data)
    safety = checker.check_point(latitude=latitude, longitude=longitude)

    return {
        "location": {"latitude": latitude, "longitude": longitude},
        "nearest_pfz": pfz_result,
        "safety": safety
    }

# swagger ui is not able to load large data, but we can proceed


@app.get("/pfz-lines")
def pfz_lines():
    """Returns the raw INCOIS PFZ GeoJSON — used for drawing lines on the map."""
    return get_pfz_data()

# frontend team-> add a feature where user can click on the map and get the nearest PFZ and safety check report


@app.get("/boundaries/mpas")
def get_mpas():
    with open("india-mpas.geojson", "r", encoding="utf-8") as f:
        return json.load(f)


@app.get("/boundaries/eez")
def get_eez():
    with open("india-eez.geojson", "r", encoding="utf-8") as f:
        return json.load(f)


@app.get("/boundaries/imbl")
def get_imbl():
    with open("imbl.geojson", "r", encoding="utf-8") as f:
        return json.load(f)


@app.get("/map", response_class=HTMLResponse)
def show_map():
    with open("map.html", "r") as f:
        return f.read()
