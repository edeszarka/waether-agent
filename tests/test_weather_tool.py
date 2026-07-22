import json
from unittest.mock import patch

import requests

from src.weather_tool import get_current_temperature

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


def _make_geo_result(name, lat, lon, admin1="", country=""):
    return {"name": name, "latitude": lat, "longitude": lon, "admin1": admin1, "country": country}


def _make_forecast(temperature):
    return {"current_weather": {"temperature": temperature, "time": "2026-07-22T12:00"}}


class TestGetCurrentTemperature:

    def test_normal_city(self):
        geo_payload = {"results": [_make_geo_result("Budapest", 47.49, 19.04, "Budapest", "Hungary")]}
        wx_payload = _make_forecast(26.5)

        with patch("src.weather_tool.requests.get") as mock_get:
            def side_effect(url, **kwargs):
                class MockResponse:
                    def __init__(self, data):
                        self._data = data
                    def raise_for_status(self):
                        pass
                    def json(self):
                        return self._data
                if GEOCODING_URL in url:
                    return MockResponse(geo_payload)
                if FORECAST_URL in url:
                    return MockResponse(wx_payload)
                raise AssertionError(f"unexpected URL: {url}")

            mock_get.side_effect = side_effect
            result = get_current_temperature("Budapest")

        assert result["city"] == "Budapest, Budapest, Hungary"
        assert result["temperature"] == 26.5
        assert result["unit"] == "celsius"

    def test_nonexistent_city(self):
        geo_payload = {"results": []}

        with patch("src.weather_tool.requests.get") as mock_get:
            class MockResponse:
                def raise_for_status(self):
                    pass
                def json(self):
                    return geo_payload

            mock_get.return_value = MockResponse()
            result = get_current_temperature("Asdfghjkl")

        assert result["error"] == "city_not_found"
        assert "Asdfghjkl" in result["detail"]

    def test_ambiguous_city(self):
        geo_payload = {
            "results": [
                _make_geo_result("Springfield", 39.78, -89.65, "Illinois", "United States"),
                _make_geo_result("Springfield", 42.10, -72.58, "Massachusetts", "United States"),
            ]
        }

        with patch("src.weather_tool.requests.get") as mock_get:
            class MockResponse:
                def raise_for_status(self):
                    pass
                def json(self):
                    return geo_payload

            mock_get.return_value = MockResponse()
            result = get_current_temperature("Springfield")

        assert result["error"] == "ambiguous_city"
        assert len(result["detail"]) == 2
        assert result["detail"][0]["name"] == "Springfield"
        assert result["detail"][0]["region"] == "Illinois"

    def test_empty_city(self):
        result = get_current_temperature("")
        assert result["error"] == "city_not_found"

        result = get_current_temperature("   ")
        assert result["error"] == "city_not_found"

    def test_geocoding_upstream_error(self):
        with patch("src.weather_tool.requests.get") as mock_get:
            mock_get.side_effect = requests.exceptions.ConnectionError("connection refused")
            result = get_current_temperature("Budapest")

        assert result["error"] == "upstream_error"
        assert "connection refused" in result["detail"].lower()

    def test_forecast_upstream_error(self):
        geo_payload = {"results": [_make_geo_result("Budapest", 47.49, 19.04)]}

        with patch("src.weather_tool.requests.get") as mock_get:
            def side_effect(url, **kwargs):
                class MockGeoResponse:
                    def raise_for_status(self):
                        pass
                    def json(self):
                        return geo_payload

                class MockWxResponse:
                    def raise_for_status(self):
                        raise requests.exceptions.HTTPError("HTTP 503")
                    def json(self):
                        return {}

                if GEOCODING_URL in url:
                    return MockGeoResponse()
                if FORECAST_URL in url:
                    return MockWxResponse()

            mock_get.side_effect = side_effect
            result = get_current_temperature("Budapest")

        assert result["error"] == "upstream_error"
        assert "503" in result["detail"]

    def test_forecast_missing_current_weather(self):
        geo_payload = {"results": [_make_geo_result("Budapest", 47.49, 19.04)]}

        with patch("src.weather_tool.requests.get") as mock_get:
            def side_effect(url, **kwargs):
                class MockResponse:
                    def raise_for_status(self):
                        pass
                    def json(self):
                        return {"current_weather": {}} if FORECAST_URL in url else geo_payload

                return MockResponse()

            mock_get.side_effect = side_effect
            result = get_current_temperature("Budapest")

        assert result["error"] == "upstream_error"
