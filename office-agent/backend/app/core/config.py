from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "office-agent"

    # ---- LLM ----
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = ""
    LLM_MODEL: str = "deepseek-chat"
    LLM_TIMEOUT: int = 120
    LLM_MAX_RETRIES: int = 2
    LLM_RETRY_BACKOFF: float = 1.5
    LLM_DEFAULT_TEMPERATURE: float = 0.1
    LLM_DEFAULT_MAX_TOKENS: int = 0
    LLM_ENABLE_LOGGING: bool = False
    LLM_THINKING_TYPE: str = ""
    LLM_REASONING_EFFORT: str = ""

    # ---- Runtime / iteration ----
    AGENT_MAX_REPLANS: int = 2
    AGENT_MAX_STEP_RETRIES: int = 1
    AGENT_RETRY_BACKOFF_BASE_SECONDS: float = 0.8
    AGENT_RETRY_BACKOFF_MAX_SECONDS: float = 5.0
    AGENT_RETRY_BACKOFF_JITTER_SECONDS: float = 0.2
    AGENT_TRACE_MAX_STRING_CHARS: int = 2000
    AGENT_TRACE_MAX_COLLECTION_ITEMS: int = 50

    # ---- Feature toggles ----
    ENABLE_PLANNER_LOGS: bool = True
    ENABLE_EXECUTOR_LOGS: bool = True
    ENABLE_VERIFIER_LOGS: bool = True
    ENABLE_FILESTORE_CACHE: bool = True

    # ---- File system layout ----
    UPLOAD_DIR: str = "storage/uploads"
    OUTPUT_DIR: str = "storage/outputs"
    TEMP_DIR: str = "storage/temp"
    CACHE_DIR: str = "storage/cache"

    # ---- Output naming ----
    OUTPUT_NAMING_STYLE: str = "timestamp"  # timestamp / sequence
    OUTPUT_FILENAME_MAX_LEN: int = 96

    # ---- Cleanup policy ----
    TEMP_FILE_TTL_SECONDS: int = 86400
    CACHE_FILE_TTL_SECONDS: int = 86400
    CLEANUP_ENABLED: bool = True

    # ---- Logger ----
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"  # json / text

    class Config:
        env_file = ".env"


settings = Settings()
