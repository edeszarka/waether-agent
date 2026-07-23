# User Guide

## What this agent does

This agent answers exactly one kind of question: *"What is the current
temperature in \<city\>?"* — using live weather data from Open-Meteo.
You can name one city or several in a single question (e.g. "Budapest
and Vienna"), and the agent will resolve each one independently.

## What it will NOT answer

The agent is deliberately narrow. It will politely refuse:

- Weather **forecasts** ("What's the weather going to be like tomorrow?")
- Weather attributes other than temperature ("What's the wind speed in
  London?")
- Questions that don't name a real city
- Unrelated topics of any kind

If a city name is ambiguous (multiple locations share the same name),
the agent will ask you to clarify rather than guessing. This can even
happen with well-known names — "Budapest" returns matches in Hungary,
Georgia (USA), and Missouri (USA), so the agent will ask which one you
mean.

**Tip:** including a country name in your question (e.g. "Budapest,
Hungary") helps the agent resolve ambiguous names directly instead of
asking for clarification.

If a city name cannot be found at all, the agent will tell you and ask
you to try a different name.

## Setup

### 1. Install dependencies

```bash
pip install -e ".[dev]"
```

### 2. Configure an LLM endpoint

Copy `.env.example` to `.env` and fill in the values:

```bash
cp .env.example .env
```

On Windows (Command Prompt / PowerShell) use `copy .env.example .env` instead.

You need three settings:

| Variable | What it is |
|---|---|
| `LLM_BASE_URL` | Base URL of any OpenAI-compatible chat-completions API |
| `LLM_API_KEY` | Your API key |
| `LLM_MODEL` | The model name to use |

Two concrete examples:

**OpenAI** (the original provider):
```
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=sk-proj-...
LLM_MODEL=gpt-4o
```

**DeepSeek** (an OpenAI-compatible alternative):
```
LLM_BASE_URL=https://api.deepseek.com
LLM_API_KEY=sk-...
LLM_MODEL=deepseek-chat
```

Any provider that speaks the OpenAI chat-completions format works.

## Running the agent

```bash
./run.sh "What's the temperature in Budapest?"
```

Or equivalently:

```bash
python -m src.main "What's the temperature in Budapest?"
```

### Example questions and expected output

| Question | What you'll get |
|---|---|
| "What's the temperature in Reykjavik?" | The current temperature for Reykjavik, e.g. "The current temperature in Reykjavik, Iceland is 11.5°C." |
| "What's the forecast for next week?" | A polite refusal stating the agent only answers current-temperature questions. |
| "What's the temperature in Springfield?" | A clarification question asking which Springfield you mean (multiple locations exist). |
| "What's the temperature in Budapest and Vienna?" | Without country names both cities are ambiguous → the agent asks for clarification (try "Budapest, Hungary and Vienna, Austria" instead). |
| "What's the temperature in Budapest, Hungary and Vienna, Austria?" | Both temperatures reported, e.g. "Budapest, Hungary: 27.4°C, Vienna, Austria: 25.3°C." |
| "What's the temperature in Asdfghjkl?" | A message that the city was not found. |

## Run traces

After every execution a JSON trace file is written to `traces/`. The
filename is a timestamp plus a short random suffix (e.g.
`20260722T114708-184292a4.json`). It contains:

- Your original question
- Every step the agent took (decisions, tool calls, responses from
  Open-Meteo)
- The final answer you received

You can open the file in any text editor to review what happened.
This is useful for debugging or auditing.
