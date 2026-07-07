from config.settings import get_settings


def _make_provider(model: str | None = None):
    s = get_settings()
    provider = s.llm_provider

    # auto-detect from whichever key is set
    if not provider:
        if s.anthropic_api_key:
            provider = "anthropic"
        elif s.gemini_api_key:
            provider = "gemini"
        else:
            raise RuntimeError(
                "No LLM provider configured. Set AGENT_ANTHROPIC_API_KEY or "
                "AGENT_GEMINI_API_KEY in .env, or set AGENT_LLM_PROVIDER explicitly."
            )

    if provider == "anthropic":
        from llm.providers.anthropic import AnthropicProvider
        return AnthropicProvider(api_key=s.anthropic_api_key, model=model or s.llm_model)
    if provider == "gemini":
        from llm.providers.gemini import GeminiProvider
        return GeminiProvider(api_key=s.gemini_api_key, model=model or s.llm_model)

    raise RuntimeError(f"Unknown LLM provider: {provider!r}. Supported: anthropic, gemini")


class LLMClient:
    """Thin wrapper over the configured LLM provider.

    `model`, when given, overrides the provider's default model for this
    client instance — this lets two different call sites (e.g. the codegen
    and interpretation graph nodes) each pin their own model string while
    sharing the same provider auto-detection/config plumbing.
    """

    def __init__(self, model: str | None = None) -> None:
        self._provider = _make_provider(model=model)

    def call_model(self, prompt: str, *, system: str | None = None) -> str:
        return self._provider.call_model(prompt, system=system)
