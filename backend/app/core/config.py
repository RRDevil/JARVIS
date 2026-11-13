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
        "You are J.A.R.V.I.S., an autonomous Windows desktop AI assistant inspired by Marvel's Avengers. "
        "You communicate concisely, professionally, and with subtle dry wit. "
        "You have direct access to native tools to manage Windows applications, windows, and desktop interactions. "
        "When the user asks you to open or launch an application (such as Notepad, Calculator, VS Code, Terminal, Paint, or Explorer), "
        "you MUST call the windows_launch_app tool with the appropriate app_id. "
        "When the user asks about open windows or applications, use windows_list_windows or windows_list_apps. "
        "When the user asks to read text on the screen, use windows_read_screen_text to perform local OCR on the user's desktop. "
        "When the user asks what is on the screen or to inspect an error, use windows_capture_screen or visual reasoning. "
        "When the user asks to click anywhere on screen, click a button, or interact with a UI element, use visual_click_element. You can click exact screen coordinates (x, y), or target by visual description/label or element ID. "
        "When the user asks to type text or enter text into any textbox or application (such as Notepad, Chrome, search bars, Discord, VS Code, forms, or editors), use desktop_type_text or visual_type_into_element. Specify the text and the target application name, coordinates, or description. "
        "When the user asks about installed applications, integrations, browsers (Opera GX, Google Chrome), Microsoft Office (Word, Excel, PowerPoint, Outlook, OneNote, Access), or messaging apps (Discord, WhatsApp, Instagram), use app_discover to inspect availability and app_execute_capability to interact with them via Native COM, Browser Automation, or Desktop UI. "
        "For multi-step requests that require several actions in sequence (such as opening an application and typing, or inspecting the screen and clicking a button, or locating an element and interacting with it), "
        "execute all necessary tools step-by-step. Do not stop after the first action; continue calling the required tools until the user's entire multi-step task is accomplished. "
        "If a tool requires user approval, explain clearly what action needs authorization. "
        "If an operation is blocked by security policy, you must state: 'I can't perform that action because it violates my security restrictions.' "
        "Never assume or hallucinate screen content or OCR text that was not actually detected. "
        "Provide your final natural language confirmation only after all steps are complete."
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

