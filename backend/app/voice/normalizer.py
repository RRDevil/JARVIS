"""
J.A.R.V.I.S. Speech-Specific Text Normalization Engine (Backend).

Provides deterministic, lightweight text normalization for spoken speech delivery.
Handles numbers, decimals, percentages, currency, dates, technical abbreviations, and code blocks
without altering visible conversational text.
"""

import math
import re
from typing import Dict, List, Optional

ONES = [
    "", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
    "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
    "seventeen", "eighteen", "nineteen"
]

TENS = [
    "", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"
]


def integer_to_words(n: int) -> str:
    if n == 0:
        return "zero"
    if n < 0:
        return f"negative {integer_to_words(abs(n))}"

    if n < 20:
        return ONES[n]

    if n < 100:
        ten = n // 10
        rest = n % 10
        return f"{TENS[ten]}-{ONES[rest]}" if rest > 0 else TENS[ten]

    if n < 1000:
        hundred = n // 100
        rest = n % 100
        rest_str = f" {integer_to_words(rest)}" if rest > 0 else ""
        return f"{ONES[hundred]} hundred{rest_str}"

    if n < 1000000:
        thousand = n // 1000
        rest = n % 1000
        rest_str = f" {integer_to_words(rest)}" if rest > 0 else ""
        return f"{integer_to_words(thousand)} thousand{rest_str}"

    if n < 1000000000:
        million = n // 1000000
        rest = n % 1000000
        rest_str = f" {integer_to_words(rest)}" if rest > 0 else ""
        return f"{integer_to_words(million)} million{rest_str}"

    return str(n)


def year_to_words(year: int) -> str:
    if 2000 <= year <= 2009:
        return f"two thousand{f' {ONES[year - 2000]}' if year > 2000 else ''}"
    century = year // 100
    decade = year % 100
    century_str = integer_to_words(century)
    if decade == 0:
        return f"{century_str} hundred"
    if decade < 10:
        return f"{century_str} oh {ONES[decade]}"
    return f"{century_str} {integer_to_words(decade)}"


PRONUNCIATION_DICTIONARY: Dict[str, str] = {
    "ai": "A I",
    "ml": "M L",
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
    "tts": "T T S",
    "stt": "S T T",
    "llm": "L L M",
    "llms": "L L Ms",
    "ocr": "O C R",
    "sse": "S S E",
    "rest": "rest",
    "gui": "gooey",
    "onnx": "on-ix",
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
}

TITLE_ABBREVIATIONS: Dict[str, str] = {
    "dr": "Doctor",
    "mr": "Mister",
    "mrs": "Missus",
    "ms": "Miz",
    "prof": "Professor",
    "sr": "Senior",
    "jr": "Junior",
    "vs": "versus",
    "etc": "etcetera",
    "approx": "approximately",
    "dept": "department",
    "fig": "figure",
    "no": "number",
    "vol": "volume",
}


def register_pronunciation(term: str, spoken: str) -> None:
    """Register custom pronunciation in dictionary."""
    PRONUNCIATION_DICTIONARY[term.lower()] = spoken


def normalize_numeric_expression(num_str: str) -> str:
    """Helper to convert numeric strings (integers or decimals) to words."""
    if "." in num_str:
        parts = num_str.split(".", 1)
        try:
            whole = integer_to_words(int(parts[0]))
        except ValueError:
            whole = parts[0]
        frac_digits = " ".join(integer_to_words(int(d)) for d in parts[1] if d.isdigit())
        return f"{whole} point {frac_digits}"
    try:
        val = int(num_str)
        return integer_to_words(val)
    except ValueError:
        return num_str


def register_pronunciation(term: str, pronunciation: str) -> None:
    """Registers or overrides a custom pronunciation in the dictionary."""
    PRONUNCIATION_DICTIONARY[term.strip().lower()] = pronunciation.strip()


def lookup_pronunciation(term: str) -> Optional[str]:
    """Looks up the pronunciation for a given word or acronym."""
    return PRONUNCIATION_DICTIONARY.get(term.strip().lower())


def normalize_text_for_speech(text: str) -> str:
    """Transforms raw text output into natural, calm phonemic speech representation."""
    if not text or not text.strip():
        return ""

    s = text.strip()

    # 1. Multi-line code blocks
    s = re.sub(r"```[\w\-]*\n[\s\S]*?```", " Code snippet omitted. ", s)
    s = re.sub(r"```[\s\S]*?```", " Code snippet omitted. ", s)

    # 2. Inline code backticks
    s = re.sub(r"`([^`]+)`", r"\1", s)

    # 3. Image embeds
    s = re.sub(r"!\[([^\]]*)\]\([^)]+\)", "", s)

    # 4. Markdown links [title](url) -> title
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)

    # 5. Bare URLs -> natural phrase
    s = re.sub(r"https?://(?:www\.)?([a-zA-Z0-9.\-]+)\S*", r"\1 link", s)

    # 6. Markdown headers, bold, italics, blockquotes
    s = re.sub(r"^#{1,6}\s+", "", s, flags=re.MULTILINE)
    s = re.sub(r"\*\*([^\*]+)\*\*", r"\1", s)
    s = re.sub(r"\*([^\*]+)\*", r"\1", s)
    s = re.sub(r"__([^_]+)__", r"\1", s)
    s = re.sub(r"_([^_]+)_", r"\1", s)
    s = re.sub(r"^\s*>\s+", "", s, flags=re.MULTILINE)

    # 7. Markdown list bullets & numbered items
    s = re.sub(r"^\s*[-*+]\s+\[[ xX]\]\s+", "", s, flags=re.MULTILINE)
    s = re.sub(r"^\s*[-*+]\s+", "", s, flags=re.MULTILINE)
    s = re.sub(r"^\s*\d+\.\s+", "", s, flags=re.MULTILINE)

    # 8. HTML tags & emojis
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"[\U00010000-\U0010ffff]", "", s)

    # 9. Currency
    def _replace_currency(raw_val: str, currency_name: str, cent_name: str = "cents") -> str:
        if "." in raw_val:
            parts = raw_val.split(".", 1)
            whole = int(parts[0]) if parts[0] else 0
            cents_part = parts[1]
            if len(cents_part) == 1:
                cents_part += "0"
            cents = int(cents_part[:2])
            whole_str = integer_to_words(whole)
            cents_str = integer_to_words(cents)
            if whole > 0 and cents > 0:
                return f"{whole_str} {currency_name} and {cents_str} {cent_name}"
            elif cents > 0:
                return f"{cents_str} {cent_name}"
            else:
                return f"{whole_str} {currency_name}"
        else:
            return f"{integer_to_words(int(raw_val))} {currency_name}"

    s = re.sub(r"\bNPR\s*(\d+(?:\.\d+)?)\b", lambda m: _replace_currency(m.group(1), "Nepalese rupees", "paisa"), s, flags=re.IGNORECASE)
    s = re.sub(r"\$\s*(\d+(?:\.\d+)?)\b", lambda m: _replace_currency(m.group(1), "dollars", "cents"), s)
    s = re.sub(r"€\s*(\d+(?:\.\d+)?)\b", lambda m: _replace_currency(m.group(1), "euros", "cents"), s)
    s = re.sub(r"£\s*(\d+(?:\.\d+)?)\b", lambda m: _replace_currency(m.group(1), "pounds", "pence"), s)
    s = re.sub(r"₹\s*(\d+(?:\.\d+)?)\b", lambda m: _replace_currency(m.group(1), "Indian rupees", "paisa"), s)
    s = re.sub(r"¥\s*(\d+(?:\.\d+)?)\b", lambda m: f"{integer_to_words(int(float(m.group(1))))} yen", s)

    # 10. Percentages
    s = re.sub(r"(\d+(?:\.\d+)?)\s*%", lambda m: f"{normalize_numeric_expression(m.group(1))} percent", s)

    # 11. Time expressions (e.g. 10:30 AM, 3:00 PM)
    def _replace_time(m):
        hour = int(m.group(1))
        minute = int(m.group(2))
        meridiem = " ".join(m.group(3).upper())
        hour_str = integer_to_words(hour)
        if minute == 0:
            min_str = ""
        elif minute < 10:
            min_str = f" oh {integer_to_words(minute)}"
        else:
            min_str = f" {integer_to_words(minute)}"
        return f"{hour_str}{min_str} {meridiem}"

    s = re.sub(r"\b(\d{1,2}):(\d{2})\s*(am|pm|AM|PM)\b", _replace_time, s)

    # 12. Latin phrases
    s = re.sub(r"\be\.g\.,?\s*", "for example, ", s, flags=re.IGNORECASE)
    s = re.sub(r"\bi\.e\.,?\s*", "that is, ", s, flags=re.IGNORECASE)
    s = re.sub(r"\betc\b\.?", "etcetera", s, flags=re.IGNORECASE)

    # 13. Titles & Honorifics
    def _replace_title(m):
        lower = m.group(1).lower()
        if lower in TITLE_ABBREVIATIONS:
            return f"{TITLE_ABBREVIATIONS[lower]} "
        return m.group(0)

    s = re.sub(r"\b([A-Za-z]{2,5})\.\s+(?=[A-Z])", _replace_title, s)

    # 14. Version tags (v2, v3, v2.5)
    s = re.sub(r"\bv(\d+(?:\.\d+)?)\b", r"version \1", s, flags=re.IGNORECASE)

    # 15. Standalone Years (1900-2099)
    s = re.sub(r"\b(19\d{2}|20\d{2})\b", lambda m: year_to_words(int(m.group(1))), s)

    # 16. Technical terms
    s = re.sub(r"\bC\+\+\b", "C plus plus", s)
    s = re.sub(r"\bC#\b", "C sharp", s)
    s = re.sub(r"\.NET\b", "dot net", s, flags=re.IGNORECASE)
    s = re.sub(r"\bNode\.js\b", "Node dot J S", s, flags=re.IGNORECASE)
    s = re.sub(r"\bVue\.js\b", "Vue dot J S", s, flags=re.IGNORECASE)
    s = re.sub(r"\bReact\.js\b", "React dot J S", s, flags=re.IGNORECASE)
    s = re.sub(r"\bGitHub\b", "Git Hub", s, flags=re.IGNORECASE)
    s = re.sub(r"\bGitLab\b", "Git Lab", s, flags=re.IGNORECASE)

    # 17. Word-level acronym replacements
    tokens = re.split(r"(\b)", s)
    for i, token in enumerate(tokens):
        lower_token = token.lower()
        if lower_token in PRONUNCIATION_DICTIONARY:
            tokens[i] = PRONUNCIATION_DICTIONARY[lower_token]
    s = "".join(tokens)

    # 18. Remaining standalone decimals
    def _replace_decimal(m):
        whole = integer_to_words(int(m.group(1)))
        frac_digits = " ".join(integer_to_words(int(d)) for d in m.group(2) if d.isdigit())
        return f"{whole} point {frac_digits}"

    s = re.sub(r"\b(\d+)\.(\d+)\b", _replace_decimal, s)

    # 19. Clean up symbols & whitespace (preserve internal underscores in variable names)
    s = re.sub(r"[#*~`><|]", " ", s)
    s = re.sub(r"(^|\s)_+|_+(\s|$)", r"\1 \2", s)
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\s+([.,!?;:])", r"\1", s)

    return s.strip()
