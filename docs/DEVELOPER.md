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
                         │  tool_call: get_current_temperature(city)
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
  `get_current_temperature(city: str) -> dict` that geocodes the city
  via Open-Meteo then fetches the current temperature.

## Run-trace JSON schema

Every run produces a trace file in `traces/`. Schema:

```json
{
  "run_id": "20260722T114708-184292a4",
  "timestamp": "2026-07-22T11:47:08.897612+00:00",
  "user_input": "What's the temperature in Budapest?",
  "steps": [
    {"type": "tool_call",  "content": {"name": "get_current_temperature", "arguments": {"city": "Budapest"}}},
    {"type": "tool_result","content": {"error": "ambiguous_city", "detail": [...]}},
    {"type": "think",       "content": "It looks like there are several places named \"Budapest\" ... Could you please clarify which Budapest you're interested in?"}
  ],
  "final_output": "It looks like there are several places named \"Budapest\" ... Could you please clarify which Budapest you're interested in?"
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

### Weather tool tests (`tests/test_weather_tool.py`)

Unit tests for `get_current_temperature` with mocked HTTP:

- Normal city resolution + forecast
- Nonexistent city name (`city_not_found`)
- Ambiguous city name (`ambiguous_city`)
- Empty / whitespace-only input
- Upstream errors from both APIs
- Missing `current_weather` field in forecast response

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
