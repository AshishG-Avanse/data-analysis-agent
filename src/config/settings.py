from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AGENT_",
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = Field(default="sqlite:///./data/agent.db")
    log_level: str = Field(default="INFO")

    # LLM provider — auto-detected from whichever key is set if left blank
    llm_provider: str = Field(default="")   # "anthropic" | "gemini"
    llm_model: str = Field(default="")      # uses provider default when blank

    # Provider keys — set exactly one
    anthropic_api_key: str = Field(default="")
    gemini_api_key: str = Field(default="")

    # Per-node model overrides (blank = provider default, see spec/architecture.md)
    llm_model_codegen: str = Field(default="")     # env: AGENT_LLM_MODEL_CODEGEN
    llm_model_interpret: str = Field(default="")   # env: AGENT_LLM_MODEL_INTERPRET

    # Iterative code-gen/execute/retry loop (spec/agent.md)
    max_retries: int = Field(default=3)             # env: AGENT_MAX_RETRIES
    exec_timeout_seconds: int = Field(default=15)   # env: AGENT_EXEC_TIMEOUT_SECONDS


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
