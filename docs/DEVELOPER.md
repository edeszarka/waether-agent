# Developer Guide

See [SPEC.md](../SPEC.md) for the full architecture specification.

## Running tests

```bash
# Install dependencies
pip install -e ".[dev]"

# Run all tests
python -m pytest

# Run a specific test file
python -m pytest tests/test_weather_tool.py -v
python -m pytest tests/test_scenarios.py -v
```

## Test scenarios (`tests/test_scenarios.py`)

These tests verify the orchestrator's looping/branching logic by mocking
the LLM client with scripted responses.  Each scenario matches one of the
behavioural test cases in SPEC.md §4:

| Test | What it verifies |
|---|---|
| `test_single_city_returns_temperature` | One tool call → numeric temperature in the answer. Trace has: think, tool_call, tool_result, think. |
| `test_refuses_forecast_question` | Out-of-scope query → no tool call, polite refusal mentioning scope. |
| `test_ambiguous_city_asks_clarification` | Ambiguous city name → tool call returns `ambiguous_city` error → LLM asks for clarification. |
| `test_two_cities_both_reported` | Two tool calls in one turn → both resolved → both temperatures in the answer. |

All four tests also assert on the JSON run-trace file written to `traces/`:
correct step types, order, and content.

## Weather tool tests (`tests/test_weather_tool.py`)

Unit tests for `get_current_temperature` with mocked HTTP calls:

- Normal city resolution + forecast
- Nonexistent city name (`city_not_found`)
- Ambiguous city name (`ambiguous_city`)
- Empty / whitespace-only input (`city_not_found`)
- Upstream errors from both the geocoding and forecast APIs
- Missing `current_weather` field in the forecast response

## Configuration

Set these environment variables (or copy `.env.example` to `.env`):

- `LLM_BASE_URL` — OpenAI-compatible endpoint URL
- `LLM_API_KEY` — API key
- `LLM_MODEL` — model name
