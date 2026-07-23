# Developer Guide

See [SPEC.md](../SPEC.md) for the full architecture specification.
This document is a condensed reference.

## Architecture overview

```
User question  ──►  Orchestrator (system prompt + tool-loop)
                         │
                         ▼
                     LLMClient ──► OpenAI-compatible API
                          │
                          │  tool_call: get_current_temperature(city, country?)
                          ▼
                     weather_tool ──► Open-Meteo Geocoding API
                          │            └─► Open-Meteo Forecast API
                          ▼
                     Tool result ──► Orchestrator resumes loop
                         │
                         ▼
                    Final answer + JSON trace file
```

Three source modules, each with a single responsibility:

- `src/llm_client.py` — thin wrapper around the OpenAI SDK. Reads
  `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` from the environment.
- `src/orchestrator.py` — the conversation loop. Holds the system
  prompt (`SYSTEM_PROMPT`), the tool schema (`TOOL_SCHEMA`), and the
  `run_agent()` function that drives turns up to a hard cap of 6.
  Also contains `RunTrace` for the JSON trace writer.
- `src/weather_tool.py` — a single function
  `get_current_temperature(city: str, country: str | None = None) -> dict`
  that geocodes the city via Open-Meteo then fetches the current
  temperature. The optional `country` parameter narrows geocoding
  via Open-Meteo's `countryCode` query parameter. Before returning
  candidates, the function applies exact-name-match and
  populated-feature-code filtering (excluding airports, city
  districts/PPLX, etc.) and deduplicates same-city entries by
  feature-code rank. A temperature-range validation
  (-90°C to 60°C) rejects implausible values as an `upstream_error`.
  - `scripts/debug_geocode.py` — a standalone diagnostic utility
    (not part of the shipped agent) that dumps raw Open-Meteo
    Geocoding API responses for inspecting how city names resolve
    at the API level.

## Run-trace JSON schema

Every run produces a trace file in `traces/`. Schema:

```json
{
  "run_id": "20260722T140035-bb88e130",
  "timestamp": "2026-07-22T14:00:35.602179+00:00",
  "user_input": "What's the temperature in Budapest, Hungary and Vienna, Austria?",
  "steps": [
    {"type": "tool_call",  "name": "get_current_temperature", "arguments": {"city": "Budapest", "country": "Hungary"}},
    {"type": "tool_result","content": {"city": "Budapest, Budapest, Hungary", "temperature": 27.4, "unit": "celsius"}},
    {"type": "tool_call",  "name": "get_current_temperature", "arguments": {"city": "Vienna", "country": "Austria"}},
    {"type": "tool_result","content": {"city": "Vienna, State of Vienna, Austria", "temperature": 25.3, "unit": "celsius"}},
    {"type": "think",       "content": "Here are the current temperatures:\n\n- **Budapest, Hungary** — **27.4°C**\n- **Vienna, Austria** — **25.3°C**\n\nBoth cities are enjoying pleasant weather today!"}
  ],
  "final_output": "Here are the current temperatures:\n\n- **Budapest, Hungary** — **27.4°C**\n- **Vienna, Austria** — **25.3°C**\n\nBoth cities are enjoying pleasant weather today!"
}
```

Step types:

| Type | When it appears |
|---|---|
| `think` | The model's reasoning or decision text for a turn |
| `tool_call` | A tool invocation sent to `weather_tool` (name + arguments) |
| `tool_result` | The exact dict returned by `weather_tool` |

The final answer appears both as the last `think` step and in
`final_output`.

## Running tests

```bash
pip install -e ".[dev]"
python -m pytest          # all tests
python -m pytest -v       # verbose, all tests
python -m pytest tests/test_weather_tool.py -v
python -m pytest tests/test_scenarios.py -v
```

### Scenario tests (`tests/test_scenarios.py`)

Each test mocks the LLM client with scripted responses and verifies the
orchestrator's branching logic + trace output.

| Test | Input | Expected behaviour |
|---|---|---|
| `test_single_city_returns_temperature` | "What's the temperature in Budapest?" | 1 tool call → numeric temperature + unit in answer |
| `test_refuses_forecast_question` | "What's the forecast for next week in Budapest?" | No tool call → polite refusal mentioning scope |
| `test_ambiguous_city_asks_clarification` | "What's the temperature in Springfield?" | 1 tool call → `ambiguous_city` error → clarification question |
| `test_two_cities_both_reported` | "What's the temperature in Budapest and Vienna?" | 2 tool calls → both temperatures reported |
| `test_country_passed_separately_resolves` | "What's the temperature in Budapest, Hungary?" | 1 tool call with `city="Budapest"` + `country="Hungary"` → temperature reported |

### Weather tool tests (`tests/test_weather_tool.py`)

Unit tests for `get_current_temperature` with mocked HTTP:

**TestGetCurrentTemperature** — core tool behavior:
- `test_normal_city` — normal geocoding + forecast returns temperature
- `test_nonexistent_city` — `city_not_found` error
- `test_ambiguous_city` — `ambiguous_city` error (multiple matches)
- `test_empty_city` — empty/whitespace input → `city_not_found`
- `test_geocoding_upstream_error` — geocoding API HTTP error
- `test_forecast_upstream_error` — forecast API HTTP error
- `test_impossible_temperature_rejected` — temperature outside -90..60°C range rejected as `upstream_error`
- `test_forecast_missing_current_weather` — missing `current_weather` field → `upstream_error`

**TestCountryFilter** — country-parameter behaviour:
- `test_with_country_resolves` — country name narrows geocoding to the correct result
- `test_alpha2_code_accepted` — ISO-3166-1 alpha-2 code accepted as country
- `test_unrecognized_country_falls_through` — unrecognized country passes through without filter

**TestGeocodingFiltering** — exact-name and feature-code filtering:
- `test_prefix_match_filtered_out` — substring/prefix matches (e.g. "Budapest" matching "Budapester Str.") excluded
- `test_airport_excluded_from_candidates` — airports and districts (PPLX, etc.) excluded

**TestFeatureCodeDedup** — same-city deduplication:
- `test_same_city_deduped_by_feature_code_rank` — same city at multiple admin levels collapsed to highest-rank entry
- `test_different_admin1_remains_ambiguous` — same city name in different admin1 regions stays ambiguous
- `test_same_name_different_country_remains_ambiguous` — same city name in different countries stays ambiguous

## Configuration

Copy `.env.example` to `.env` and set:

- `LLM_BASE_URL` — any OpenAI-compatible endpoint
- `LLM_API_KEY` — API key
- `LLM_MODEL` — model name

## Explicit non-goals (from SPEC.md §7)

These are absent by design, not by oversight:

- **No MCP server** — a single hardcoded REST integration doesn't
  need a general-purpose tool-interop protocol.
- **No "Agent Skills" folder convention** — that packaging pattern
  is designed for a different runtime (Claude skills) and doesn't
  fit an OpenAI-compatible agent with one tool.
- **No OpenTelemetry / external tracing** — the JSON trace file
  satisfies the traceability requirement without extra infrastructure.
- **No multi-agent design** — one orchestrator loop is sufficient for
  a single-tool, single-intent agent.
