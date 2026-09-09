from contextlib import asynccontextmanager
from shapely.geometry import shape
from pyproj import Geod
import requests
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from dotenv import load_dotenv
from boundary_checker import BoundaryChecker
from typing import Any
import uuid
import time
import threading
from pathlib import Path
import os
import json
import itertools
import io
import base64
from pydantic import BaseModel
from navigation import (
    Coordinate,
    NavigationRequest,
    generate_route,
    distance_km,
)


class NavigationResponse(BaseModel):
    status: str
    distance_km: float
    route: list
    warnings: list


try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

try:
    from gtts import gTTS
except ImportError:
    gTTS = None

load_dotenv()

geo_checker: BoundaryChecker = None  # type: ignore
SESSIONS_FILE = Path("chat_sessions.json")

raw_keys = os.getenv("GEMINI_API_KEYS", os.getenv("GEMINI_API_KEY", ""))
API_KEYS = [k.strip() for k in raw_keys.split(",") if k.strip()]
key_cycle = itertools.cycle(API_KEYS) if API_KEYS else None
key_lock = threading.Lock()

INCOIS_URL = "https://incois.gov.in/geoserver/PFZ_Automation/ows"
PFZ_CACHE_TTL_SECONDS = 3600
pfz_cache = {"data": None, "timestamp": 0}
geod = Geod(ellps="WGS84")


def _first_value(values: Any) -> Any:
    if not isinstance(values, list):
        return None
    return next((value for value in values if value is not None), None)


def get_weather_data(latitude: float, longitude: float) -> dict[str, str]:
    weather = {"temp": "N/A", "wind": "N/A", "desc": "", "waves": "N/A"}

    try:
        weather_response = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": latitude,
                "longitude": longitude,
                "hourly": "wind_speed_10m",
                "forecast_days": 1,
            },
            timeout=10,
        )
        if weather_response.status_code == 200:
            hourly = weather_response.json().get("hourly", {})
            wind_speed = _first_value(hourly.get("wind_speed_10m"))
            if wind_speed is not None:
                weather["wind"] = f"{wind_speed:.1f} km/h"
    except Exception as err:
        print(f"Weather data unavailable: {err}")

    try:
        marine_response = requests.get(
            "https://marine-api.open-meteo.com/v1/marine",
            params={
                "latitude": latitude,
                "longitude": longitude,
                "hourly": "sea_surface_temperature,wave_height",
                "forecast_days": 1,
            },
            timeout=10,
        )
        if marine_response.status_code == 200:
            hourly = marine_response.json().get("hourly", {})
            sea_temperature = _first_value(
                hourly.get("sea_surface_temperature"))
            wave_height = _first_value(hourly.get("wave_height"))
            if sea_temperature is not None:
                weather["temp"] = f"{sea_temperature:.1f}°C"
            if wave_height is not None:
                weather["waves"] = f"{wave_height:.1f} m"
    except Exception as err:
        print(f"Marine data unavailable: {err}")

    return weather


def get_next_client() -> Any:
    if key_cycle is None or genai is None:
        raise RuntimeError(
            "Chatbot is not configured: install google-genai and set GEMINI_API_KEY or GEMINI_API_KEYS in backend/.env.")
    with key_lock:
        selected_key = next(key_cycle)
    return genai.Client(api_key=selected_key)


def execute_with_fallback(system_instruction: str, gemini_contents: list):
    if not API_KEYS or genai is None or types is None:
        raise RuntimeError(
            "Chatbot is not configured: install google-genai and set GEMINI_API_KEY or GEMINI_API_KEYS in backend/.env.")
    last_err = None
    for _ in range(len(API_KEYS)):
        client = get_next_client()
        for model_name in ["gemini-3.7-flash", "gemini-3.8-flash"]:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=gemini_contents,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        response_mime_type="application/json",
                    ),
                )
                return json.loads(response.text)
            except Exception as err:
                last_err = err
                print(
                    f"[Quota Rotation] Model '{model_name}' hit error: {err}. Trying"
                    " next..."
                )

    raise RuntimeError(f"All API keys and models exhausted: {last_err}")


def get_pfz_data():
    now = time.time()
    if pfz_cache["data"] is not None and now - pfz_cache["timestamp"] < PFZ_CACHE_TTL_SECONDS:
        return pfz_cache["data"]
    try:
        response = requests.get(INCOIS_URL, params={
            "service": "WFS", "version": "1.1.0", "request": "GetFeature",
            "typeName": "PFZ_Automation:pfzlines", "outputFormat": "application/json", "srsName": "EPSG:4326",
        }, timeout=30)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as err:
        raise HTTPException(
            status_code=502, detail=f"Unable to fetch PFZ data from INCOIS: {err}")
    pfz_cache.update({"data": data, "timestamp": now})
    return data


def find_nearest_pfz(latitude: float, longitude: float, data: dict):
    nearest, minimum_distance = None, float("inf")
    for feature in data.get("features", []):
        geometry = feature.get("geometry")
        if not geometry:
            continue
        try:
            geom = shape(geometry)
            if geom.geom_type in ("Point", "LineString", "LinearRing", "Polygon"):
                coords = list(geom.coords) if geom.geom_type != "Polygon" else list(
                    geom.exterior.coords)  # type: ignore
            elif geom.geom_type in ("MultiPoint", "MultiLineString"):
                # type: ignore
                coords = [point for part in geom.geoms for point in part.coords]
            elif geom.geom_type == "MultiPolygon":
                # type: ignore
                coords = [
                    point for part in geom.geoms for point in part.exterior.coords]
            else:
                coords = []
            for lon2, lat2 in coords:
                _, _, distance_m = geod.inv(longitude, latitude, lon2, lat2)
                if distance_m < minimum_distance:
                    minimum_distance = distance_m
                    nearest = {"pfz_id": feature.get("id"), "distance_km": round(distance_m / 1000, 3),
                               "nearest_point": {"latitude": round(lat2, 6), "longitude": round(lon2, 6)},
                               "properties": feature.get("properties", {})}
        except Exception:
            continue
    return nearest


def load_all_sessions() -> dict:
    if not SESSIONS_FILE.exists():
        return {}
    try:
        with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_all_sessions(data: dict):
    with open(SESSIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global geo_checker
    base_dir = os.path.dirname(os.path.abspath(__file__))
    mpa_path = os.path.join(base_dir, "india-mpas.geojson")
    eez_path = os.path.join(base_dir, "india-eez.geojson")
    imbl_path = os.path.join(base_dir, "imbl.geojson")

    print("\n[Lifespan] Preloading Maritime Layers and ETOPO Bathymetry...")
    try:
        geo_checker = BoundaryChecker(
            mpa_file=mpa_path,
            eez_file=eez_path,
            imbl_file=imbl_path,
            bathymetry_file=None,
        )
        print("[Lifespan] Spatial safety engine initialized successfully.")
    except Exception as e:
        print(f"[Lifespan] Warning: Failed to load spatial engine: {e}")
        geo_checker = None  # type: ignore
    yield
    if geo_checker and getattr(geo_checker, "bathymetry", None):
        assert geo_checker.bathymetry is not None
        geo_checker.bathymetry.close()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SUPPORTED_LANGS = {"ml", "ta", "te", "bn", "gu", "kn", "mr", "hi", "ur", "en"}


@app.get("/")
def serve_home():
    return FileResponse("chatbot.html")


@app.get("/map")
def serve_map():
    return FileResponse("map.html")


@app.get("/nearest-pfz")
def nearest_pfz(latitude: float = Query(..., ge=-90, le=90), longitude: float = Query(..., ge=-180, le=180)):
    result = find_nearest_pfz(latitude, longitude, get_pfz_data())
    if result is None:
        raise HTTPException(
            status_code=404, detail="No PFZ found for this location.")
    return {"user_location": {"latitude": latitude, "longitude": longitude}, "nearest_pfz": result}


@app.get("/safety-check")
def safety_check(latitude: float = Query(..., ge=-90, le=90), longitude: float = Query(..., ge=-180, le=180)):
    if geo_checker is None:
        raise HTTPException(
            status_code=503, detail="Safety engine is still starting or failed to load.")
    try:
        return geo_checker.check_point(latitude=latitude, longitude=longitude)
    except ValueError as err:
        raise HTTPException(status_code=422, detail=str(err))


@app.get("/full-report")
def full_report(latitude: float = Query(..., ge=-90, le=90), longitude: float = Query(..., ge=-180, le=180)):
    return {
        "location": {"latitude": latitude, "longitude": longitude},
        "nearest_pfz": find_nearest_pfz(latitude, longitude, get_pfz_data()),
        "safety": safety_check(latitude, longitude),
        "weather": get_weather_data(latitude, longitude),
    }


@app.get("/pfz-lines")
def pfz_lines():
    return get_pfz_data()


@app.get("/boundaries/{boundary_type}")
def boundaries(boundary_type: str):
    boundary_files = {
        "mpas": "india-mpas.geojson",
        "eez": "india-eez.geojson",
        "imbl": "imbl.geojson",
    }
    filename = boundary_files.get(boundary_type)
    if filename is None:
        raise HTTPException(status_code=404, detail="Unknown boundary layer")
    filepath = Path(__file__).with_name(filename)
    if not filepath.exists():
        raise HTTPException(
            status_code=404, detail="Boundary layer is unavailable")
    return FileResponse(filepath, media_type="application/geo+json")


@app.get("/api/sessions")
def list_sessions():
    sessions = load_all_sessions()
    session_list = []
    for s_id, data in sessions.items():
        session_list.append({
            "session_id": s_id,
            "title": data.get("title", "New Advisory Chat"),
        })
    return session_list[::-1]


@app.post("/api/sessions/new")
def create_new_session():
    sessions = load_all_sessions()
    session_id = str(uuid.uuid4())
    sessions[session_id] = {"title": "New Advisory Chat", "history": []}
    save_all_sessions(sessions)
    return {"session_id": session_id, "title": "New Advisory Chat"}


@app.get("/api/sessions/{session_id}")
def get_session(session_id: str):
    sessions = load_all_sessions()
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Chat not found")
    return sessions[session_id]


@app.delete("/api/sessions/{session_id}")
def delete_single_session(session_id: str):
    sessions = load_all_sessions()
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Chat not found")
    del sessions[session_id]
    save_all_sessions(sessions)
    return {"status": "success", "message": f"Deleted session {session_id}"}


@app.delete("/api/sessions")
def clear_all_sessions():
    save_all_sessions({})
    return {"status": "success", "message": "All chat history cleared"}


@app.get("/api/navigation/health")
def navigation_health():
    return {
        "status": "ok",
        "service": "navigation"
    }


@app.post("/api/navigation/route")
def calculate_route(request: NavigationRequest):

    if geo_checker is None:
        raise HTTPException(
            status_code=503,
            detail="Safety engine is not available"
        )

    start = request.start
    destination = request.destination

    # Validate coordinates
    if not (-90 <= start.latitude <= 90):
        raise HTTPException(
            status_code=422,
            detail="Invalid starting latitude"
        )

    if not (-180 <= start.longitude <= 180):
        raise HTTPException(
            status_code=422,
            detail="Invalid starting longitude"
        )

    if not (-90 <= destination.latitude <= 90):
        raise HTTPException(
            status_code=422,
            detail="Invalid destination latitude"
        )

    if not (-180 <= destination.longitude <= 180):
        raise HTTPException(
            status_code=422,
            detail="Invalid destination longitude"
        )

    route = generate_route(
        start,
        destination,
        points=30
    )

    warnings = []

    # Check every route point
    for point in route:

        try:
            safety = geo_checker.check_point(
                latitude=point["latitude"],
                longitude=point["longitude"]
            )

            status = safety.get("status", "UNKNOWN")

            point["status"] = status

            point["safety"] = safety

            # Collect warnings
            point_warnings = safety.get("warnings", [])

            if point_warnings:
                warnings.extend(point_warnings)

        except Exception as e:
            point["status"] = "unknown"

    # Remove duplicate warnings
    warnings = list(dict.fromkeys(warnings))

    total_distance = distance_km(
        start,
        destination
    )

    return {
        "status": "success",
        "distance_km": round(total_distance, 2),
        "route": route,
        "warnings": warnings,
        "start": start.model_dump(),
        "destination": destination.model_dump(),
    }


@app.post("/chat-fishery")
async def chat_fishery(
    lat: float = Form(...),
    lon: float = Form(...),
    message: str = Form(None),
    session_id: str = Form(None),
    audio: UploadFile = File(None),
):
    try:
        sessions = load_all_sessions()
        if not session_id or session_id not in sessions:
            session_id = str(uuid.uuid4())
            sessions[session_id] = {
                "title": "New Advisory Chat", "history": []}

        session_data = sessions[session_id]
        history = session_data.get("history", [])

        geo_data = {}
        if geo_checker:
            try:
                geo_data = geo_checker.check_point(latitude=lat, longitude=lon)
            except Exception as geo_err:
                print(f"Geo safety check error: {geo_err}")

        marine_res = {}
        try:
            m_resp = requests.get(
                "https://marine-api.open-meteo.com/v1/marine",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "hourly": "wave_height,wave_period,swell_wave_height",
                    "forecast_days": 1,
                },
                timeout=10,
            )
            marine_res = m_resp.json() if m_resp.status_code == 200 else {}
        except Exception:
            pass

        weather_res = {}
        owm_key = os.getenv("OWM_API_KEY")
        if owm_key:
            try:
                w_resp = requests.get(
                    "https://api.openweathermap.org/data/2.5/weather",
                    params={
                        "lat": lat,
                        "lon": lon,
                        "appid": owm_key,
                        "units": "metric",
                    },
                    timeout=10,
                )
                weather_res = w_resp.json() if w_resp.status_code == 200 else {}
            except Exception:
                pass

        system_instruction = f"""
        You are 'ORCA', an AI coastal advisory and marine safety assistant for fishermen and coastal navigators.
        User GPS Coordinates: Latitude {lat}, Longitude {lon}
        
        Local Maritime & Bathymetry Status:
        - Overall Status: {geo_data.get('status', 'UNKNOWN')}
        - Inside Indian EEZ: {geo_data.get('inside_india_eez')}
        - Inside Marine Protected Area (MPA): {geo_data.get('inside_mpa')} (Details: {geo_data.get('mpa_areas')})
        - Distance to IMBL (Border): {geo_data.get('distance_to_imbl_m')} meters
        - Border Warning Triggered: {geo_data.get('imbl_alert')}
        - Water Depth: {geo_data.get('depth_m')} meters (Status: {geo_data.get('depth_status')})
        - Elevation / Is Land: {geo_data.get('elevation_m')}m / {geo_data.get('is_land')}
        - Critical Safety Warnings: {geo_data.get('warnings', [])}
        
        Live Meteorological Data:
        - Marine Forecast (Waves/Swells): {marine_res.get('hourly')}
        - Weather Data (Wind, Rain, Temp): {weather_res}
        
        Context & Memory Rules:
        1. Context Continuity: You have full access to the previous turns in this session. Maintain context across the conversation. If the user asks follow-up questions (e.g., "what about tomorrow?", "is it safe there?", "what fish can I catch there?"), resolve references to previously mentioned places or conditions directly.
        2. High Priority Alert: If 'imbl_alert' is True, urgently warn about the international border. If near shallow waters or MPAs, warn about navigational hazards and prohibited fishing.
        3. PFZ & Coastal Queries: Even if the user coordinates are inland, do NOT refuse questions about sea conditions, Potential Fishing Zones (PFZ), or general marine safety for requested regions.
        4. Language: Always reply in the exact language the user is speaking/asking in.
        5. Length: Keep answers concise (2 to 3 practical sentences) so audio playback (TTS) remains quick and clear.
        6. Format: Return ONLY a valid JSON object:
           {{
             "reply": "<plain text without markdown, asterisks, or formatting>",
             "lang_code": "<2-letter ISO language code like 'ml', 'ta', 'te', 'bn', 'hi', 'en'>"
           }}
        """

        gemini_contents = []
        for turn in history:
            role = "user" if turn["role"] == "user" else "model"
            assert types is not None
            gemini_contents.append(
                types.Content(
                    role=role,
                    parts=[types.Part.from_text(text=turn["content"])]
                )
            )

        new_turn_parts = []
        user_record_text = message.strip() if message else ""

        if audio:
            audio_bytes = await audio.read()
            assert types is not None
            new_turn_parts.append(
                types.Part.from_bytes(
                    data=audio_bytes,
                    mime_type=audio.content_type or "audio/webm",
                )
            )
            if not user_record_text:
                user_record_text = "🎙️"

        if message and message.strip():
            assert types is not None
            new_turn_parts.append(types.Part.from_text(text=message.strip()))
        elif not audio:
            default_prompt = "What is the sea condition and safety advisory right now?"
            new_turn_parts.append(types.Part.from_text(text=default_prompt))
            user_record_text = default_prompt

        assert types is not None
        gemini_contents.append(types.Content(
            role="user", parts=new_turn_parts))

        data = execute_with_fallback(system_instruction, gemini_contents)

        reply_text = data.get("reply", "").strip()
        lang_code = data.get("lang_code", "en").lower().strip()
        if lang_code not in SUPPORTED_LANGS:
            lang_code = "en"

        history.append({"role": "user", "content": user_record_text})
        history.append({"role": "model", "content": reply_text})

        if session_data.get("title") == "New Advisory Chat" and user_record_text:
            clean_prompt = user_record_text.replace(
                "🎙️ [Voice Advisory Request]", ""
            ).strip()
            lowered = clean_prompt.lower()
            trivial_phrases = {
                "hello",
                "hi",
                "hey",
                "test",
                "try again",
                "help",
                "ok",
                "okay",
            }

            if clean_prompt and lowered not in trivial_phrases:
                words = clean_prompt.split()
                session_data["title"] = " ".join(words[:4]).title()
            else:
                status = geo_data.get("status", "Advisory")
                session_data["title"] = (
                    f"Sea Check ({status.replace('_', ' ').title()})"
                )

        session_data["history"] = history
        sessions[session_id] = session_data
        save_all_sessions(sessions)

        if gTTS is None:
            raise RuntimeError("Chatbot audio is unavailable: install gTTS.")
        tts = gTTS(text=reply_text, lang=lang_code, slow=False)
        audio_buffer = io.BytesIO()
        tts.write_to_fp(audio_buffer)
        audio_buffer.seek(0)
        audio_b64 = base64.b64encode(audio_buffer.read()).decode("utf-8")

        return {
            "session_id": session_id,
            "reply": reply_text,
            "lang_code": lang_code,
            "audio_base64": f"data:audio/mp3;base64,{audio_b64}",
            "geo_status": geo_data.get("status"),
            "depth_m": geo_data.get("depth_m"),
            "distance_to_imbl_m": geo_data.get("distance_to_imbl_m"),
        }

    except Exception as err:
        print(f"Chat error: {err}")
        raise HTTPException(status_code=500, detail=str(err))
