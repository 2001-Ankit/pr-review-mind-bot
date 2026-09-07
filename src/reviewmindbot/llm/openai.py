"""OpenAI and OpenAI-compatible providers."""

from __future__ import annotations

from .base import Completion, LLMProvider


class OpenAIProvider(LLMProvider):
    """Chat Completions against OpenAI or any compatible endpoint."""

    name = "openai"
    base_url: str | None = None

    def __init__(self, api_key: str, model: str, **kwargs) -> None:
        super().__init__(model, **kwargs)
        from openai import OpenAI  # imported lazily

        self._client = OpenAI(
            api_key=api_key,
            base_url=self.base_url,
            timeout=self.timeout,
            # Retries are handled uniformly in LLMProvider.generate.
            max_retries=0,
        )

    def _complete(self, system_prompt: str, user_prompt: str) -> Completion:
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
        )

        text = response.choices[0].message.content or ""
        usage = getattr(response, "usage", None)
        if usage is None:
            return Completion.estimated_from(text, system_prompt + user_prompt)

        return Completion(
            text=text,
            input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(usage, "completion_tokens", 0) or 0,
        )


class GroqProvider(OpenAIProvider):
    """Groq exposes an OpenAI-compatible Chat Completions API."""

    name = "groq"
    base_url = "https://api.groq.com/openai/v1"
