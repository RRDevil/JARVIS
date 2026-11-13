"""J.A.R.V.I.S. Pronunciation Management Engine.

Provides configurable phonetic substitutions and domain dictionaries for technical
acronyms, application brands, operating system paths, and user-defined names.
"""

from typing import Dict, List, Optional
import re
import threading


class PronunciationDictionary:
    """Thread-safe pronunciation registry with domain-specific phonemic mappings."""

    def __init__(self):
        self._lock = threading.RLock()
        self._dictionary: Dict[str, str] = {}
        self._load_builtins()

    def _load_builtins(self) -> None:
        """Load default standard pronunciation mappings."""
        builtins: Dict[str, str] = {
            # AI / ML
            "ai": "A I",
            "ml": "M L",
            "llm": "L L M",
            "llms": "L L Ms",
            "gpt": "G P T",
            "rag": "rag",
            "onnx": "on-ix",
            "rvc": "R V C",
            "tts": "T T S",
            "stt": "S T T",
            "ocr": "O C R",
            "sse": "S S E",
            "pytorch": "pie torch",
            "tensorflow": "tensor flow",

            # Technologies, Languages & Frameworks
            "api": "A P I",
            "apis": "A P Is",
            "ui": "U I",
            "ux": "U X",
            "os": "O S",
            "cpu": "C P U",
            "cpus": "C P Us",
            "gpu": "G P U",
            "gpus": "G P Us",
            "ram": "ram",
            "rom": "rom",
            "sql": "sequel",
            "json": "jason",
            "html": "H T M L",
            "css": "C S S",
            "http": "H T T P",
            "https": "H T T P S",
            "url": "U R L",
            "urls": "U R Ls",
            "cli": "C L I",
            "sdk": "S D K",
            "sdks": "S D Ks",
            "ide": "I D E",
            "gui": "gooey",
            "regex": "reg-ex",
            "io": "I O",
            "ipc": "I P C",
            "wpm": "words per minute",
            "fps": "frames per second",
            "ms": "milliseconds",
            "kb": "kilobytes",
            "mb": "megabytes",
            "gb": "gigabytes",
            "ghz": "gigahertz",
            "mhz": "megahertz",
            "fastapi": "fast A P I",
            "uvicorn": "you-vee-corn",
            "pydantic": "pie-dan-tic",
            "sqlite": "sequel-light",
            "postgres": "post-gres",
            "postgresql": "post-gres Q L",
            "latex": "lay-tech",
            "katex": "kay-tech",

            # Brands & Applications
            "github": "Git Hub",
            "gitlab": "Git Lab",
            "discord": "Discord",
            "whatsapp": "Whats App",
            "instagram": "Instagram",
            "opera": "Opera",
            "chrome": "Chrome",
            "safari": "Safari",
            "vscode": "V S Code",
            "powerpoint": "PowerPoint",
            "excel": "Excel",
            "onenote": "OneNote",
            "macos": "mac O S",
            "nvidia": "en-vid-ee-uh",
            "amd": "A M D",
            "intel": "Intel",
        }
        self._dictionary.update(builtins)

    def register(self, term: str, pronunciation: str) -> None:
        """Register or update a custom term's spoken pronunciation."""
        with self._lock:
            self._dictionary[term.strip().lower()] = pronunciation.strip()

    def remove(self, term: str) -> bool:
        """Remove a term from the custom pronunciation dictionary."""
        with self._lock:
            return self._dictionary.pop(term.strip().lower(), None) is not None

    def lookup(self, term: str) -> Optional[str]:
        """Look up the spoken pronunciation for a term."""
        with self._lock:
            return self._dictionary.get(term.strip().lower())

    def apply(self, text: str) -> str:
        """Apply all dictionary substitutions across whole words in the input string."""
        if not text:
            return ""

        with self._lock:
            # Word-level replacement preserving surrounding punctuation
            tokens = re.split(r"(\b[\w\-.]+\b)", text)
            for i, token in enumerate(tokens):
                lower_token = token.lower()
                if lower_token in self._dictionary:
                    tokens[i] = self._dictionary[lower_token]
            return "".join(tokens)

    def list_all(self) -> Dict[str, str]:
        """Return a copy of all registered pronunciations."""
        with self._lock:
            return dict(self._dictionary)


# Global singleton instance
pronunciation_dictionary = PronunciationDictionary()
