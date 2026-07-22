from typing import Any

import requests

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

MIN_PLAUSIBLE_TEMP = -90.0
MAX_PLAUSIBLE_TEMP = 60.0


def get_current_temperature(city: str) -> dict[str, Any]:
    """Get the current temperature for *city* via Open-Meteo.

    Contract
    --------
    On success returns:
        {"city": <resolved display name>, "temperature": <float>, "unit": "celsius"}

    On expected error returns (does NOT raise):
        {"error": "city_not_found",   "detail": <str>}
        {"error": "ambiguous_city",   "detail": [<candidate dict>, ...]}
        {"error": "upstream_error",   "detail": <str>}
    """
    if not city or not city.strip():
        return {"error": "city_not_found", "detail": "City name is empty."}

    city_clean = city.strip()

    # --- Step 1: geocode ---------------------------------------------------
    try:
        geo_resp = requests.get(
            GEOCODING_URL,
            params={"name": city_clean, "count": 10, "language": "en", "format": "json"},
            timeout=10,
        )
        geo_resp.raise_for_status()
        geo_data = geo_resp.json()
    except requests.RequestException as exc:
        return {"error": "upstream_error", "detail": f"Geocoding API request failed: {exc}"}

    results = geo_data.get("results", [])
    if not results:
        return {
            "error": "city_not_found",
            "detail": f"No location found for '{city_clean}'.",
        }

    if len(results) > 1:
        candidates = [
            {
                "name": r.get("name", "?"),
                "region": r.get("admin1", ""),
                "country": r.get("country", ""),
            }
            for r in results
        ]
        return {
            "error": "ambiguous_city",
            "detail": candidates,
        }

    location = results[0]
    lat = location["latitude"]
    lon = location["longitude"]
    resolved_name = location.get("name", city_clean)
    admin1 = location.get("admin1", "")
    country = location.get("country", "")
    parts = [p for p in (resolved_name, admin1, country) if p]
    display_name = ", ".join(parts)

    # --- Step 2: fetch current weather -------------------------------------
    try:
        wx_resp = requests.get(
            FORECAST_URL,
            params={"latitude": lat, "longitude": lon, "current_weather": "true"},
            timeout=10,
        )
        wx_resp.raise_for_status()
        wx_data = wx_resp.json()
    except requests.RequestException as exc:
        return {"error": "upstream_error", "detail": f"Forecast API request failed: {exc}"}

    current = wx_data.get("current_weather")
    if current is None:
        return {
            "error": "upstream_error",
            "detail": "Forecast response missing 'current_weather' field.",
        }

    temperature = current.get("temperature")
    if temperature is None:
        return {
            "error": "upstream_error",
            "detail": "Forecast response missing temperature in current_weather.",
        }

    temp_val = float(temperature)
    if not (MIN_PLAUSIBLE_TEMP <= temp_val <= MAX_PLAUSIBLE_TEMP):
        return {
            "error": "upstream_error",
            "detail": (
                f"Temperature {temp_val}°C is outside plausible range "
                f"({MIN_PLAUSIBLE_TEMP} to {MAX_PLAUSIBLE_TEMP}°C)."
            ),
        }

    return {
        "city": display_name,
        "temperature": temp_val,
        "unit": "celsius",
    }
