"""Debug script: dump raw Open-Meteo Geocoding API output for analysis.

Not part of the shipped tool — purely diagnostic.
"""

import json
import requests

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
BASE_PARAMS = {"count": 10, "language": "en", "format": "json"}

CALLS = [
    {"label": "Budapest — no countryCode", "params": {"name": "Budapest"}},
    {"label": "Budapest — countryCode=HU", "params": {"name": "Budapest", "country_code": "HU"}},
    {"label": "Budapest — countryCode=GB", "params": {"name": "Budapest", "country_code": "GB"}},
    {"label": "Budapest — countryCode=US", "params": {"name": "Budapest", "country_code": "US"}},
]

FIELDS = [
    "name", "latitude", "longitude",
    "feature_code",
    "country_code",
    "admin1", "admin2", "admin3", "admin4",
    "country", "timezone",
    "population", "elevation",
]


def main() -> None:
    for call in CALLS:
        print(f"\n{'=' * 80}")
        print(f"  {call['label']}")
        print(f"{'=' * 80}")

        params = {**BASE_PARAMS, **call["params"]}
        try:
            resp = requests.get(GEOCODING_URL, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            print(f"  ERROR: {exc}")
            continue

        results = data.get("results", [])
        print(f"  count = {len(results)}\n")

        if not results:
            print("  (no results)")
            continue

        for i, r in enumerate(results):
            print(f"  --- result {i} ---")
            for field in FIELDS:
                val = r.get(field, "<MISSING>")
                print(f"    {field}: {val}")


if __name__ == "__main__":
    main()
