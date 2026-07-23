# Specification: Simple Weather Agent

## 1. Vision & Intent

A minimal, LLM-driven agent that answers exactly one class of question: *"What is the current temperature in <city or cities>?"* — using the Open-Meteo public forecast API as its only data source. A single request may name more than one city (e.g. "temperature in Budapest and Vienna?"), in which case the agent resolves each one. The agent is intentionally narrow in scope; correctness, auditability, and simplicity are prioritized over generality.

## 2. Technical Architecture

```
User question
     |
     v
[ Orchestrator (Python) ] ---- system prompt (scope + behavior rules)
     |
     v
[ LLM (OpenAI-compatible chat + tool calling) ]
     |
      |  tool_call: get_current_temperature(city, country?)
      v
[ Weather tool ]
      |  1. geocode(city, country?) -> lat/lon   (Open-Meteo Geocoding API)
      |  2. forecast(lat, lon)                   (Open-Meteo Forecast API, current_weather=true)
     v
[ Tool result returned to LLM ]
     |
     v
[ LLM produces final answer ]
     |
     v
[ Run trace written to disk ] + [ Answer printed to user ]
```

### 2.1 LLM client — provider-agnostic by design

- Uses the OpenAI Python SDK's chat-completions interface (`base_url`, `api_key`, `model` all configurable via environment variables / a `.env` file).
- No code path assumes a specific vendor. Any endpoint that speaks the OpenAI chat-completions + tool-calling format works: OpenAI itself, or a compatible provider/self-hosted server.
- Config surface:
  - `LLM_BASE_URL`
  - `LLM_API_KEY`
  - `LLM_MODEL`

### 2.2 Orchestrator

- A conversation loop per run, repeated until the model stops requesting tools:
  1. Build the message list: system prompt + user question.
  2. Call the LLM with the `get_current_temperature` tool schema available.
  3. If the model's turn includes one or more tool calls (e.g. one per city when several are named): validate each call's arguments, execute each, append all tool results, and call the model again.
  4. Repeat step 3 until a turn produces no tool calls — that turn's content is the final reply. A per-run iteration cap (e.g. 6 turns) guards against runaway loops.
  5. If the model replies directly with no tool call at all (e.g. a clarification question or a refusal): return that as-is.
  6. Write the full run trace (see §3) before returning the answer.

### 2.3 Weather tool

- One Python function, `get_current_temperature(city: str, country: str | None = None) -> dict`.
- Step 1: resolve `city` to coordinates via Open-Meteo's Geocoding API. When `country` is provided, it is passed as Open-Meteo's `countryCode` parameter to narrow geocoding results to a single country.
- Step 2: call Open-Meteo's Forecast API (`current_weather=true`) with those coordinates.
- Returns a small structured result: `{ "city": ..., "temperature": ..., "unit": "celsius" }`, or a typed error (`city_not_found`, `ambiguous_city`, `upstream_error`).
- No MCP server, no separate protocol layer — this is a single direct HTTP call wrapped in a plain function, which is all the scope calls for.

### 2.4 Scope control

Two layers, deliberately simple:

1. **System prompt** — explicitly instructs the model: only answer current-temperature-for-named-city(ies) questions; if the request names several cities, call the tool once per city and report each result; ask for clarification if a city is ambiguous or missing; politely refuse anything else (forecasts, other weather attributes, unrelated topics).
2. **Code-level guard** — the tool function rejects empty/invalid city strings and surfaces geocoding ambiguity (multiple matches) as a distinct error the orchestrator turns into a clarification request, rather than silently guessing.

This avoids standing up a separate "policy server" or "semantic gating" component — the constraint lives where it's easy to read and test.

## 3. Observability: Run Trace

Every run produces one trace file (JSON) capturing enough to reconstruct what happened without any external tracing infrastructure:

```json
{
  "run_id": "...",
  "timestamp": "...",
  "user_input": "...",
  "steps": [
    {"type": "think", "content": "<model reasoning / decision to call a tool>"},
    {"type": "tool_call", "name": "get_current_temperature", "arguments": {...}},
    {"type": "tool_result", "content": {...}},
    {"type": "think", "content": "<model's final reasoning>"}
  ],
  "final_output": "..."
}
```

- `think` entries capture the model's reasoning/decisions at each turn.
- `tool_call` / `tool_result` entries capture exactly what was sent to and received from Open-Meteo.
- No OpenTelemetry collector or external service required — the trace is a plain file, reviewable by opening it.

## 4. Behavioral Test Cases

At least three scenario-based tests, each specifying input, expected tool call(s), and expected output shape:

1. **Successful retrieval** — "What's the temperature in Budapest?" → one tool call with `city=Budapest` → numeric temperature + unit in the final answer.
2. **Out-of-scope query** — "What's the forecast for next week in Budapest?" → no tool call (or a refusal after evaluating scope) → polite refusal stating the agent only reports current temperature.
3. **Ambiguous city** — a city name matching multiple locations → no premature tool call → a clarification question asking which location the user means.
4. **Multiple cities in one request** — "What's the temperature in Budapest and Vienna?" → two tool calls (one per city) within the same run → a final answer reporting both temperatures.

## 5. Documentation

- `docs/USER.md` — how to run the agent, example questions, what it will and won't answer.
- `docs/DEVELOPER.md` — architecture overview (this spec, condensed), how to configure the LLM endpoint, how to read a run trace, how to run tests.

## 6. Repository Layout

```
.
├── README.md
├── SPEC.md
├── run.sh
├── src/
│   ├── orchestrator.py
│   ├── weather_tool.py
│   └── llm_client.py
├── docs/
│   ├── USER.md
│   └── DEVELOPER.md
├── tests/
│   └── test_scenarios.py
└── traces/            # run traces written here
```

## 7. Explicit Non-Goals

Called out deliberately, in case reviewers wonder why they're absent:

- **No MCP server** — one hardcoded REST integration doesn't need a general-purpose tool-interop protocol.
- **No "Agent Skills" folder convention** — that packaging pattern belongs to a different runtime (Claude's skills system) and doesn't fit an OpenAI-compatible agent with a single tool.
- **No OpenTelemetry / external tracing backend** — a structured JSON trace file satisfies the traceability requirement without extra infrastructure.
- **No multi-agent design** — a single orchestrator loop is sufficient for a single-tool, single-intent agent.
