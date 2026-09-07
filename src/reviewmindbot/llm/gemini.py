"""Google Gemini provider."""

from __future__ import annotations

from .base import Completion, LLMProvider


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, api_key: str, model: str, **kwargs) -> None:
        super().__init__(model, **kwargs)
        from google import genai  # imported lazily so other providers work without it

        self._client = genai.Client(api_key=api_key)

    def _complete(self, system_prompt: str, user_prompt: str) -> Completion:
        from google.genai import types

        response = self._client.models.generate_content(
            model=self.model,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.2,
            ),
        )

        text = response.text or ""
        metadata = getattr(response, "usage_metadata", None)
        if metadata is None:
            return Completion.estimated_from(text, system_prompt + user_prompt)

        return Completion(
            text=text,
            input_tokens=getattr(metadata, "prompt_token_count", 0) or 0,
            output_tokens=getattr(metadata, "candidates_token_count", 0) or 0,
        )
