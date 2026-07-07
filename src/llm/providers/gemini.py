from google import genai
from google.genai import types


class GeminiProvider:
    DEFAULT_MODEL = "gemini-3.1-pro-preview"
    # Per-node defaults (spec/architecture.md -> "LLM Provider & Model"),
    # used when the corresponding AGENT_LLM_MODEL_* setting is blank.
    DEFAULT_MODEL_CODEGEN = "gemini-3.1-pro-preview"
    DEFAULT_MODEL_INTERPRET = "gemini-2.5-flash"

    def __init__(self, api_key: str, model: str) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model or self.DEFAULT_MODEL

    def call_model(self, prompt: str, *, system: str | None = None) -> str:
        config = types.GenerateContentConfig(
            system_instruction=system,
        ) if system else None
        response = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
            config=config,
        )
        return response.text
