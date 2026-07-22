import os
from dataclasses import dataclass, field

from openai import OpenAI
from openai.types.chat import ChatCompletionMessage


@dataclass
class LLMConfig:
    base_url: str = ""
    api_key: str = ""
    model: str = ""

    @classmethod
    def from_env(cls) -> "LLMConfig":
        base_url = os.environ.get("LLM_BASE_URL")
        api_key = os.environ.get("LLM_API_KEY")
        model = os.environ.get("LLM_MODEL")
        missing = [k for k, v in [("LLM_BASE_URL", base_url), ("LLM_API_KEY", api_key), ("LLM_MODEL", model)] if not v]
        if missing:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing)}. "
                "Set them directly or via a .env file."
            )
        return cls(base_url=base_url, api_key=api_key, model=model)


class LLMClient:
    def __init__(self, config: LLMConfig | None = None):
        self.config = config or LLMConfig.from_env()
        self._client = OpenAI(
            base_url=self.config.base_url,
            api_key=self.config.api_key,
        )

    def complete(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        **kwargs,
    ) -> ChatCompletionMessage:
        params: dict = {
            "model": self.config.model,
            "messages": messages,
        }
        if tools is not None:
            params["tools"] = tools
        params.update(kwargs)
        response = self._client.chat.completions.create(**params)
        return response.choices[0].message
