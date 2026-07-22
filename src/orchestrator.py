import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from src.llm_client import LLMClient
from src.weather_tool import get_current_temperature

SYSTEM_PROMPT = """\
You are a helpful assistant that answers questions about the current temperature in named cities.

Rules:
1. Only answer questions about the current temperature of a named city or cities.
2. If a request names multiple cities, call the get_current_temperature tool once per city and report each result in your final answer.
3. If the user provides disambiguating detail (country, region, etc.), include it in the tool's city parameter. If the city is still ambiguous or cannot be found, ask the user to clarify — do not guess.
4. Politely refuse anything else (forecasts, other weather attributes, unrelated topics) without calling any tool.\
"""

TOOL_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "get_current_temperature",
        "description": "Look up the current temperature for a city using Open-Meteo weather data.",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "The city name, optionally including region/country for disambiguation (e.g. 'Budapest, Hungary' or 'London, UK'). Include any qualifying detail the user provided.",
                },
            },
            "required": ["city"],
        },
    },
}

TRACES_DIR = "traces"
MAX_ITERATIONS = 6


class RunTrace:
    def __init__(self, user_input: str) -> None:
        ts = datetime.now(timezone.utc)
        suffix = uuid.uuid4().hex[:8]
        self.run_id = f"{ts.strftime('%Y%m%dT%H%M%S')}-{suffix}"
        self.timestamp = ts.isoformat()
        self.user_input = user_input
        self.steps: list[dict[str, Any]] = []
        self.final_output: str = ""

    def add_step(self, step_type: str, content: Any = None, **extra: Any) -> None:
        entry: dict[str, Any] = {"type": step_type}
        if content is not None:
            entry["content"] = content
        entry.update(extra)
        self.steps.append(entry)

    def write(self) -> str:
        data: dict[str, Any] = {
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "user_input": self.user_input,
            "steps": self.steps,
            "final_output": self.final_output,
        }
        os.makedirs(TRACES_DIR, exist_ok=True)
        path = os.path.join(TRACES_DIR, f"{self.run_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return os.path.abspath(path)


def run_agent(
    user_input: str,
    llm_client: LLMClient | None = None,
) -> tuple[str, str]:
    """Run the weather-agent loop and return (final_answer, trace_file_path)."""
    if llm_client is None:
        llm_client = LLMClient()

    trace = RunTrace(user_input)

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_input},
    ]
    tools = [TOOL_SCHEMA]

    for _iteration in range(MAX_ITERATIONS):
        response = llm_client.complete(messages, tools=tools)

        think_content = response.content or ""
        if think_content:
            trace.add_step("think", think_content)

        if not response.tool_calls:
            trace.final_output = think_content
            trace_path = trace.write()
            return think_content, trace_path

        assistant_msg: dict[str, Any] = {
            "role": "assistant",
            "content": response.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in response.tool_calls
            ],
        }
        messages.append(assistant_msg)

        for tc in response.tool_calls:
            if tc.function.name != "get_current_temperature":
                continue

            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}

            city = args.get("city", "")
            trace.add_step(
                "tool_call",
                name="get_current_temperature",
                arguments={"city": city},
            )

            result = get_current_temperature(city)
            trace.add_step("tool_result", result)

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result),
                }
            )

    trace.add_step(
        "think",
        f"Hit iteration cap of {MAX_ITERATIONS} — aborting.",
    )
    trace.final_output = ""
    trace_path = trace.write()
    return (
        "I'm sorry, I wasn't able to complete your request within the allowed number of steps. Please try again.",
        trace_path,
    )
