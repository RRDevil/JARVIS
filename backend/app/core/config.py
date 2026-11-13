"""JARVIS Core Configuration Module."""

from pathlib import Path
from typing import List, Optional, Union
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
import json


class Settings(BaseSettings):
    """Application settings with environment variable overrides and validation."""

    # Project metadata
    PROJECT_NAME: str = "JARVIS Desktop Assistant"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"

    # Server configuration
    JARVIS_HOST: str = "127.0.0.1"
    JARVIS_PORT: int = 8000
    JARVIS_DEBUG: bool = True

    # Security & CORS
    JARVIS_ALLOWED_ORIGINS: Union[str, List[str]] = Field(
        default=["http://localhost:5173", "http://127.0.0.1:5173", "tauri://localhost"]
    )
    JARVIS_API_KEY_SECRET: str = "jarvis-default-local-token-change-in-env"

    # AI Provider configuration
    GEMINI_API_KEY: str = ""
    GEMINI_DEFAULT_MODEL: str = "gemini-flash-lite-latest"
    AI_REQUEST_TIMEOUT_SECONDS: float = 120.0
    AI_MAX_OUTPUT_TOKENS: int = 2048
    AI_MAX_CONTEXT_MESSAGES: int = 20
    AI_MAX_INPUT_CHARS: int = 16000
    AI_TEMPERATURE: float = 0.7
    AI_SYSTEM_INSTRUCTION: str = (
        "You are J.A.R.V.I.S., a goal-oriented Windows desktop personal AI agent inspired by Marvel's Avengers. "
        "You communicate concisely, professionally, and with subtle dry wit. "
        "You independently understand high-level objectives rather than requiring the user to dictate every intermediate step. "
        "When given a goal (such as finding and updating a document, or messaging a person), you autonomously formulate "
        "and execute the necessary sequence of steps: observing the desktop, checking saved preferences, preparing actions, "
        "obtaining approval where consequential, and verifying outcomes. "
        "You have direct access to native tools to manage Windows applications, windows, and desktop interactions. "
        "USER PREFERENCE MEMORY: You retain user-specific workflow and application preferences across sessions. "
        "When the user asks to contact someone or open a site, check saved preferences using preference_query. "
        "Honor confirmed per-person and per-website preferences. When the user explicitly states or confirms a preference, "
        "store it using preference_store so you never have to ask again. "
        "SEMANTIC PERCEPTION: When inspecting messaging applications (Instagram, WhatsApp, Discord), use semantic_read_conversations. "
        "In Instagram Direct, you MUST strictly distinguish genuine conversation entries from Instagram Notes, note authors, "
        "story bubbles, and search suggestions. Never report a Note or note author as an active conversation. "
        "When the user asks you to open or launch an application, use windows_launch_app or app_execute_capability. "
        "When the user asks to click anywhere on screen, click a button, or interact with a UI element, use visual_click_element. "
        "When the user asks to type text or enter text into any textbox or application, use desktop_type_text or visual_type_into_element. "
        "CRITICAL TEXT ENTRY INTEGRITY: When the user asks you to type or enter text, you MUST preserve the EXACT verbatim text requested by the user. Do not summarize, rephrase, or substitute conversational filler, greetings, descriptions, or status updates into typing tool calls. "
        "When a consequential tool execution completes following user approval, do NOT re-propose or repeat the tool call. "
        "BROWSER & WEB SEARCH AUTOMATION: When the user asks to open a tab, browse, search, or find information/articles in a web browser (Opera GX, Google Chrome): "
        "ALWAYS use app_execute_capability with app_id='browser.opera_gx' (or 'browser.chrome') and capability_id='browser.navigate' with 'query' (e.g. {'query': 'species of snakes found in Nepal'}) or 'url'. "
        "DO NOT use windows_launch_app or attempt to guess screen coordinates for web browsers. "
        "To inspect or read opened page articles and search results, use app_execute_capability with capability_id='browser.read_page', or windows_read_screen_text. "
        "MULTI-STEP GOAL PLANNING: For multi-step requests, you can use plan_create to formulate verified sequential steps. "
        "Execute all necessary tools step-by-step. Do not stop after the first action; continue calling the required tools until the user's entire multi-step task is accomplished. "
        "When an action requires user approval, clearly state what action requires authorization in your conversational text. "
        "When an approval decision is granted, immediately continue to the next step of the plan. "
        "NATURAL CONVERSATIONAL RESPONSES: Always provide spoken text accompanying your tool proposals or execution (e.g. 'Opening Opera GX to locate articles on snake species in Nepal...'). Never leave your conversational response completely empty. "
        "When the user asks about installed applications, integrations, browsers (Opera GX, Google Chrome), Microsoft Office (Word, Excel, PowerPoint, Outlook, OneNote, Access), or messaging apps (Discord, WhatsApp, Instagram), use app_discover and app_execute_capability. "
        "If a tool requires user approval, explain clearly what action needs authorization. "
        "If an operation is blocked by security policy, state: 'I can't perform that action because it violates my security restrictions.' "
        "Never assume or hallucinate screen content or OCR text that was not actually detected. "
        "Provide your final natural language confirmation only after all steps are complete and verified."
    )

    # Filesystem Sandboxing
    JARVIS_WORKSPACE_ROOT: str = "./data/workspace"
    JARVIS_ALLOWED_PATHS: Union[str, List[str]] = Field(
        default=["./data/workspace"]
    )

    # Persistence & External Models Storage
    JARVIS_DATABASE_URL: str = "sqlite:///./data/jarvis.db"
    JARVIS_MODELS_DIR: Optional[str] = Field(
        default=None,
        description="External directory for large voice/speech models (Faster-Whisper, Piper, RVC). Keeps repo lightweight for GitHub.",
    )

    @field_validator("JARVIS_ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_allowed_origins(cls, value: Union[str, List[str]]) -> List[str]:
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return parsed
            except Exception:
                return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("JARVIS_ALLOWED_PATHS", mode="before")
    @classmethod
    def parse_allowed_paths(cls, value: Union[str, List[str]]) -> List[str]:
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return parsed
            except Exception:
                return [p.strip() for p in value.split(",") if p.strip()]
        return value

    @property
    def workspace_path(self) -> Path:
        """Resolve workspace root into an absolute Path."""
        path = Path(self.JARVIS_WORKSPACE_ROOT).resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path

    model_config = SettingsConfigDict(
        env_file=(
            str(Path(__file__).resolve().parents[3] / ".env"),
            str(Path(__file__).resolve().parents[2] / ".env"),
            ".env",
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )


# Singleton settings instance
settings = Settings()

