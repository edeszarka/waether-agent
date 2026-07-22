import json
import os
from unittest.mock import patch

from openai.types.chat import ChatCompletionMessage, ChatCompletionMessageToolCall
from openai.types.chat.chat_completion_message_tool_call import Function

from src.orchestrator import run_agent


def _tool_msg(city: str, call_id: str = "call_1", country: str = "") -> ChatCompletionMessage:
    args: dict[str, str] = {"city": city}
    if country:
        args["country"] = country
    return ChatCompletionMessage(
        content=f"I'll look up the temperature in {city}.",
        role="assistant",
        tool_calls=[
            ChatCompletionMessageToolCall(
                id=call_id,
                function=Function(
                    name="get_current_temperature",
                    arguments=json.dumps(args),
                ),
                type="function",
            )
        ],
    )


def _multi_tool_msg(
    calls: list[tuple[str, str]],
) -> ChatCompletionMessage:
    return ChatCompletionMessage(
        content=f"I'll look up temperatures for {len(calls)} cities.",
        role="assistant",
        tool_calls=[
            ChatCompletionMessageToolCall(
                id=call_id,
                function=Function(
                    name="get_current_temperature",
                    arguments=json.dumps({"city": city}),
                ),
                type="function",
            )
            for city, call_id in calls
        ],
    )


def _tool_msg_with_country(city: str, country: str, call_id: str = "call_1") -> ChatCompletionMessage:
    return ChatCompletionMessage(
        content=f"I'll look up the temperature in {city}.",
        role="assistant",
        tool_calls=[
            ChatCompletionMessageToolCall(
                id=call_id,
                function=Function(
                    name="get_current_temperature",
                    arguments=json.dumps({"city": city, "country": country}),
                ),
                type="function",
            )
        ],
    )


def _final_msg(text: str) -> ChatCompletionMessage:
    return ChatCompletionMessage(
        content=text,
        role="assistant",
        tool_calls=None,
    )


_BUDAPEST_OK = {"city": "Budapest, Budapest, Hungary", "temperature": 26.5, "unit": "celsius"}
_VIENNA_OK = {"city": "Vienna, Vienna, Austria", "temperature": 22.3, "unit": "celsius"}

_AMBIGUOUS_RESULT = {
    "error": "ambiguous_city",
    "detail": [
        {"name": "Springfield", "region": "Illinois", "country": "United States"},
        {"name": "Springfield", "region": "Massachusetts", "country": "United States"},
    ],
}

TRACES_DIR = "traces"


def _clean_trace(path: str) -> None:
    if path and os.path.exists(path):
        os.remove(path)


def _load_trace(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class TestSuccessfulRetrieval:

    def test_single_city_returns_temperature(self):
        mock_llm = _MockLLM(side_effect=[
            _tool_msg("Budapest"),
            _final_msg("The temperature in Budapest is 26.5\u00b0C."),
        ])

        with patch("src.orchestrator.get_current_temperature", return_value=_BUDAPEST_OK):
            answer, trace_path = run_agent(
                "What's the temperature in Budapest?",
                llm_client=mock_llm,
            )

        try:
            assert "26.5" in answer
            assert "Budapest" in answer

            trace = _load_trace(trace_path)
            assert trace["user_input"] == "What's the temperature in Budapest?"
            assert trace["final_output"] == answer

            steps = trace["steps"]
            assert len(steps) == 4
            assert steps[0]["type"] == "think"
            assert steps[1]["type"] == "tool_call"
            assert steps[1]["name"] == "get_current_temperature"
            assert steps[1]["arguments"]["city"] == "Budapest"
            assert steps[2]["type"] == "tool_result"
            assert steps[2]["content"] == _BUDAPEST_OK
            assert steps[3]["type"] == "think"
        finally:
            _clean_trace(trace_path)


class TestOutOfScopeQuery:

    def test_refuses_forecast_question(self):
        refusal = (
            "I can only answer questions about the current temperature in a named city. "
            "I cannot provide weather forecasts or other weather attributes."
        )
        mock_llm = _MockLLM(side_effect=[
            _final_msg(refusal),
        ])

        with patch("src.orchestrator.get_current_temperature") as mock_weather:
            answer, trace_path = run_agent(
                "What's the forecast for next week in Budapest?",
                llm_client=mock_llm,
            )

        try:
            assert "only" in answer.lower()
            assert "current temperature" in answer.lower()
            mock_weather.assert_not_called()

            trace = _load_trace(trace_path)
            assert len(trace["steps"]) == 1
            assert trace["steps"][0]["type"] == "think"
            assert trace["final_output"] == answer
        finally:
            _clean_trace(trace_path)


class TestAmbiguousCity:

    def test_ambiguous_city_asks_clarification(self):
        clarification = "There are multiple places named Springfield. Which one do you mean?"
        mock_llm = _MockLLM(side_effect=[
            _tool_msg("Springfield", call_id="call_springfield"),
            _final_msg(clarification),
        ])

        with patch("src.orchestrator.get_current_temperature", return_value=_AMBIGUOUS_RESULT):
            answer, trace_path = run_agent(
                "What's the temperature in Springfield?",
                llm_client=mock_llm,
            )

        try:
            assert "Springfield" in answer
            assert not any(
                word in answer.lower()
                for word in ("26.5", "22.3", "temperature is")
            ), "Should ask for clarification, not report a temperature"

            trace = _load_trace(trace_path)
            steps = trace["steps"]
            step_types = [s["type"] for s in steps]
            assert step_types == ["think", "tool_call", "tool_result", "think"]

            tool_call_step = steps[1]
            assert tool_call_step["arguments"]["city"] == "Springfield"

            tool_result_step = steps[2]
            assert tool_result_step["content"]["error"] == "ambiguous_city"
            assert len(tool_result_step["content"]["detail"]) == 2
        finally:
            _clean_trace(trace_path)


class TestMultipleCities:

    def test_two_cities_both_reported(self):
        mock_llm = _MockLLM(side_effect=[
            _multi_tool_msg([("Budapest", "call_bp"), ("Vienna", "call_vn")]),
            _final_msg(
                "The current temperature in Budapest is 26.5\u00b0C "
                "and in Vienna it is 22.3\u00b0C."
            ),
        ])

        def _weather_side_effect(city: str, **kwargs) -> dict:
            return {"Budapest": _BUDAPEST_OK, "Vienna": _VIENNA_OK}.get(city, {})

        with patch("src.orchestrator.get_current_temperature", side_effect=_weather_side_effect):
            answer, trace_path = run_agent(
                "What's the temperature in Budapest and Vienna?",
                llm_client=mock_llm,
            )

        try:
            assert "26.5" in answer
            assert "22.3" in answer
            assert "Budapest" in answer
            assert "Vienna" in answer

            trace = _load_trace(trace_path)
            steps = trace["steps"]
            step_types = [s["type"] for s in steps]
            assert step_types == [
                "think",
                "tool_call", "tool_result",
                "tool_call", "tool_result",
                "think",
            ]

            arguments = [
                s["arguments"]["city"]
                for s in steps
                if s["type"] == "tool_call"
            ]
            assert arguments == ["Budapest", "Vienna"]

            temperatures = [
                s["content"]["temperature"]
                for s in steps
                if s["type"] == "tool_result"
            ]
            assert temperatures == [26.5, 22.3]
        finally:
            _clean_trace(trace_path)


class TestCountryDisambiguation:

    def test_country_passed_separately_resolves(self):
        mock_llm = _MockLLM(side_effect=[
            _tool_msg_with_country("Budapest", "Hungary"),
            _final_msg("The current temperature in Budapest is 26.5\u00b0C."),
        ])

        with patch("src.orchestrator.get_current_temperature", return_value=_BUDAPEST_OK):
            answer, trace_path = run_agent(
                "What's the temperature in Budapest, Hungary?",
                llm_client=mock_llm,
            )

        try:
            assert "26.5" in answer
            trace = _load_trace(trace_path)
            tool_call = trace["steps"][1]
            assert tool_call["arguments"]["city"] == "Budapest"
            assert tool_call["arguments"]["country"] == "Hungary"
        finally:
            _clean_trace(trace_path)


class _MockLLM:
    """Scripted mock that returns pre-built ChatCompletionMessage objects."""

    def __init__(self, side_effect: list[ChatCompletionMessage]):
        self._responses = list(reversed(side_effect))
        self.messages_history: list[list[dict]] = []

    def complete(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        **kwargs,
    ) -> ChatCompletionMessage:
        self.messages_history.append(list(messages))
        return self._responses.pop()
