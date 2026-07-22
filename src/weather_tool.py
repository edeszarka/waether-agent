from typing import Any

import requests

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

MIN_PLAUSIBLE_TEMP = -90.0
MAX_PLAUSIBLE_TEMP = 60.0

POPULATED_FEATURE_CODES = frozenset({
    "PPL", "PPLA", "PPLA2", "PPLA3", "PPLA4", "PPLC", "PPLCH",
    "PPLF", "PPLG", "PPLH", "PPLL", "PPLQ", "PPLR", "PPLS",
    "PPLW", "STLMT",
})

# GeoNames hierarchy: lower number = higher administrative order.
_FEATURE_CODE_RANK: dict[str, int] = {
    "PPLC": 0,
    "PPLA": 1,
    "PPLA2": 2,
    "PPLA3": 3,
    "PPLA4": 4,
    "PPL": 5,
    "PPLCH": 6,
    "PPLF": 6,
    "PPLG": 6,
    "PPLH": 6,
    "PPLL": 6,
    "PPLQ": 6,
    "PPLR": 6,
    "PPLS": 6,
    "PPLW": 6,
    "STLMT": 7,
    "PPLX": 8,
}

COUNTRY_CODES: dict[str, str] = {
    "hungary": "HU",
    "austria": "AT",
    "united states": "US",
    "usa": "US",
    "united kingdom": "GB",
    "uk": "GB",
    "germany": "DE",
    "france": "FR",
    "italy": "IT",
    "spain": "ES",
    "netherlands": "NL",
    "belgium": "BE",
    "switzerland": "CH",
    "canada": "CA",
    "australia": "AU",
    "japan": "JP",
    "china": "CN",
    "india": "IN",
    "brazil": "BR",
    "mexico": "MX",
    "poland": "PL",
    "czech republic": "CZ",
    "czechia": "CZ",
    "slovakia": "SK",
    "romania": "RO",
    "bulgaria": "BG",
    "serbia": "RS",
    "croatia": "HR",
    "slovenia": "SI",
    "ukraine": "UA",
    "russia": "RU",
    "sweden": "SE",
    "norway": "NO",
    "denmark": "DK",
    "finland": "FI",
    "greece": "GR",
    "portugal": "PT",
    "turkey": "TR",
    "egypt": "EG",
    "south africa": "ZA",
    "argentina": "AR",
    "colombia": "CO",
    "new zealand": "NZ",
    "south korea": "KR",
}


def _resolve_country_code(country: str | None) -> tuple[str | None, str | None]:
    """Return (iso_alpha2, note). *note* is set when the value was unrecognized."""
    if not country:
        return None, None
    cleaned = country.strip()
    if len(cleaned) == 2 and cleaned.isalpha():
        return cleaned.upper(), None
    code = COUNTRY_CODES.get(cleaned.lower())
    if code:
        return code, None
    return None, f"Unrecognized country '{cleaned}' — proceeding without country filter."


def _is_populated_place(result: dict[str, Any]) -> bool:
    return result.get("feature_code", "") in POPULATED_FEATURE_CODES


def _exact_name_match(searched: str, candidate_name: str) -> bool:
    return searched.lower() == candidate_name.lower()


def _with_note(result: dict[str, Any], note: str | None) -> dict[str, Any]:
    if note:
        result["_note"] = note
    return result


def _filter_geocoding_results(
    raw_results: list[dict[str, Any]],
    searched_city: str,
) -> list[dict[str, Any]]:
    return [
        r for r in raw_results
        if _exact_name_match(searched_city, r.get("name", ""))
        and _is_populated_place(r)
    ]


def _deduplicate_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse same-city entries recorded at multiple admin levels.

    Key is (name, country_code, admin1) — so Springfield IL and Springfield MA
    remain separate candidates. Within a group the highest-rank feature-code wins.
    """
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for r in results:
        key = (r.get("name", "").lower(), r.get("country_code", ""), r.get("admin1", ""))
        groups.setdefault(key, []).append(r)

    return [
        min(group, key=lambda r: _FEATURE_CODE_RANK.get(r.get("feature_code", ""), 99))
        for group in groups.values()
    ]


def get_current_temperature(city: str, country: str | None = None) -> dict[str, Any]:
    """Get the current temperature for *city* via Open-Meteo.

    Parameters
    ----------
    city : str
        The city name (required).
    country : str or None
        Optional country name or ISO-3166-1 alpha-2 code to narrow the
        geocoding search.

    Returns
    -------
    dict
    On success:
        {"city": ..., "temperature": ..., "unit": "celsius"}
    On expected error (does NOT raise):
        {"error": "city_not_found",   "detail": <str>}
        {"error": "ambiguous_city",   "detail": [<candidate dict>, ...]}
        {"error": "upstream_error",   "detail": <str>}
    """
    country_code, country_note = _resolve_country_code(country)

    if not city or not city.strip():
        return _with_note({"error": "city_not_found", "detail": "City name is empty."}, country_note)

    city_clean = city.strip()

    # --- Step 1: geocode ---------------------------------------------------
    try:
        params: dict[str, Any] = {
            "name": city_clean, "count": 10, "language": "en", "format": "json",
        }
        if country_code:
            params["countryCode"] = country_code
        geo_resp = requests.get(GEOCODING_URL, params=params, timeout=10)
        geo_resp.raise_for_status()
        geo_data = geo_resp.json()
    except requests.RequestException as exc:
        return _with_note({"error": "upstream_error", "detail": f"Geocoding API request failed: {exc}"}, country_note)

    raw_results = geo_data.get("results", [])
    if not raw_results:
        return _with_note({
            "error": "city_not_found",
            "detail": f"No location found for '{city_clean}'.",
        }, country_note)

    results = _filter_geocoding_results(raw_results, city_clean)
    results = _deduplicate_results(results)
    if not results:
        return _with_note({
            "error": "city_not_found",
            "detail": f"No location found for '{city_clean}'.",
        }, country_note)

    if len(results) > 1:
        candidates = [
            {
                "name": r.get("name", "?"),
                "region": r.get("admin1", ""),
                "country": r.get("country", ""),
            }
            for r in results
        ]
        return _with_note({
            "error": "ambiguous_city",
            "detail": candidates,
        }, country_note)

    location = results[0]
    lat = location["latitude"]
    lon = location["longitude"]
    resolved_name = location.get("name", city_clean)
    admin1 = location.get("admin1", "")
    resolved_country = location.get("country", "")
    parts = [p for p in (resolved_name, admin1, resolved_country) if p]
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
        return _with_note({"error": "upstream_error", "detail": f"Forecast API request failed: {exc}"}, country_note)

    current = wx_data.get("current_weather")
    if current is None:
        return _with_note({
            "error": "upstream_error",
            "detail": "Forecast response missing 'current_weather' field.",
        }, country_note)

    temperature = current.get("temperature")
    if temperature is None:
        return _with_note({
            "error": "upstream_error",
            "detail": "Forecast response missing temperature in current_weather.",
        }, country_note)

    temp_val = float(temperature)
    if not (MIN_PLAUSIBLE_TEMP <= temp_val <= MAX_PLAUSIBLE_TEMP):
        return _with_note({
            "error": "upstream_error",
            "detail": (
                f"Temperature {temp_val}°C is outside plausible range "
                f"({MIN_PLAUSIBLE_TEMP} to {MAX_PLAUSIBLE_TEMP}°C)."
            ),
        }, country_note)

    return _with_note({
        "city": display_name,
        "temperature": temp_val,
        "unit": "celsius",
    }, country_note)
