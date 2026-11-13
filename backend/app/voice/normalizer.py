"""
J.A.R.V.I.S. Speech-Specific Text Normalization Engine (Backend).

Provides deterministic, lightweight text normalization for spoken speech delivery.
Handles numbers, decimals, percentages, currency, dates, technical abbreviations, and code blocks
without altering visible conversational text.
"""

import math
import re
from typing import Dict, List, Optional

from app.voice.pronunciation import pronunciation_dictionary

ONES = [
    "", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
    "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
    "seventeen", "eighteen", "nineteen"
]

TENS = [
    "", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"
]

MONTH_NAMES = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
]

ORDINALS = [
    "", "first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth",
    "eleventh", "twelfth", "thirteenth", "fourteenth", "fifteenth", "sixteenth", "seventeenth", "eighteenth", "nineteenth", "twentieth",
    "twenty-first", "twenty-second", "twenty-third", "twenty-fourth", "twenty-fifth", "twenty-sixth", "twenty-seventh", "twenty-eighth", "twenty-ninth", "thirtieth", "thirty-first"
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
    """Helper to convert numeric strings (integers or decimals, including negative) to words."""
    is_neg = num_str.startswith("-")
    clean_str = num_str[1:] if is_neg else num_str
    prefix = "negative " if is_neg else ""
    if "." in clean_str:
        parts = clean_str.split(".", 1)
        try:
            whole = integer_to_words(int(parts[0]))
        except ValueError:
            whole = parts[0]
        frac_digits = " ".join(integer_to_words(int(d)) for d in parts[1] if d.isdigit())
        return f"{prefix}{whole} point {frac_digits}"
    try:
        val = int(clean_str)
        return f"{prefix}{integer_to_words(val)}"
    except ValueError:
        return num_str


def register_pronunciation(term: str, pronunciation: str) -> None:
    """Registers or overrides a custom pronunciation in the dictionary."""
    clean_term = term.strip().lower()
    clean_spoken = pronunciation.strip()
    PRONUNCIATION_DICTIONARY[clean_term] = clean_spoken
    pronunciation_dictionary.register(clean_term, clean_spoken)


def lookup_pronunciation(term: str) -> Optional[str]:
    """Looks up the pronunciation for a given word or acronym."""
    clean_term = term.strip().lower()
    return pronunciation_dictionary.lookup(clean_term) or PRONUNCIATION_DICTIONARY.get(clean_term)


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

    # 5b. Email addresses -> natural phrase
    s = re.sub(r"\b([a-zA-Z0-9_.+-]+)@([a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)\b", lambda m: f"{m.group(1)} at {m.group(2).replace('.', ' dot ')}", s)

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

    # 8b. IPv4 addresses (must precede decimal splitting)
    def _replace_ip(m):
        octets = [int(x) for x in m.groups()]
        if all(0 <= o <= 255 for o in octets):
            return f"{octets[0]} dot {octets[1]} dot {octets[2]} dot {octets[3]}"
        return m.group(0)
    s = re.sub(r"\b(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})\b", _replace_ip, s)

    # 8c. ISO Calendar Dates (YYYY-MM-DD)
    def _replace_iso_date(m):
        year = int(m.group(1))
        month = int(m.group(2))
        day = int(m.group(3))
        month_name = MONTH_NAMES[month] if 1 <= month <= 12 else str(month)
        day_ord = ORDINALS[day] if 1 <= day <= 31 else integer_to_words(day)
        year_str = year_to_words(year)
        return f"{month_name} {day_ord}, {year_str}"
    s = re.sub(r"\b(19\d\d|20\d\d)-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])\b", _replace_iso_date, s)

    # 8d. Durations (e.g. 2h 30m, 45m, 3h)
    s = re.sub(
        r"\b(\d+)\s*h(?:rs?|ours?)?\s*(\d+)\s*m(?:ins?|inutes?)?\b",
        lambda m: f"{integer_to_words(int(m.group(1)))} hours {integer_to_words(int(m.group(2)))} minutes",
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(r"\b(\d+)\s*h(?:rs?|ours?)\b", lambda m: f"{integer_to_words(int(m.group(1)))} hours", s, flags=re.IGNORECASE)
    s = re.sub(r"\b(\d+)\s*m(?:ins?|inutes?)\b", lambda m: f"{integer_to_words(int(m.group(1)))} minutes", s, flags=re.IGNORECASE)

    # 8e. Delimited integers (remove commas between digits e.g. 1,250 -> 1250)
    s = re.sub(r"\b(\d{1,3}),(\d{3})\b", r"\1\2", s)

    # 8f. Metric & Time units
    s = re.sub(r"\b(\d+(?:\.\d+)?)\s*ms\b", r"\1 milliseconds", s)
    s = re.sub(r"\b(\d+(?:\.\d+)?)\s*s\b", r"\1 seconds", s)
    s = re.sub(r"\b(\d+(?:\.\d+)?)\s*sec\b", r"\1 seconds", s)
    s = re.sub(r"\b(\d+(?:\.\d+)?)\s*min\b", r"\1 minutes", s)
    s = re.sub(r"\b(\d+(?:\.\d+)?)\s*(?:MB|mb)\b", r"\1 megabytes", s)
    s = re.sub(r"\b(\d+(?:\.\d+)?)\s*(?:GB|gb)\b", r"\1 gigabytes", s)
    s = re.sub(r"\b(\d+(?:\.\d+)?)\s*(?:KB|kb)\b", r"\1 kilobytes", s)

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

    s = re.sub(r"\bRs\.?\s*(\d+(?:\.\d+)?)\b", lambda m: _replace_currency(m.group(1), "rupees", "paisa"), s, flags=re.IGNORECASE)
    s = re.sub(r"\bNPR\s*(\d+(?:\.\d+)?)\b", lambda m: _replace_currency(m.group(1), "Nepalese rupees", "paisa"), s, flags=re.IGNORECASE)
    s = re.sub(r"\$\s*(\d+(?:\.\d+)?)\b", lambda m: _replace_currency(m.group(1), "dollars", "cents"), s)
    s = re.sub(r"€\s*(\d+(?:\.\d+)?)\b", lambda m: _replace_currency(m.group(1), "euros", "cents"), s)
    s = re.sub(r"£\s*(\d+(?:\.\d+)?)\b", lambda m: _replace_currency(m.group(1), "pounds", "pence"), s)
    s = re.sub(r"₹\s*(\d+(?:\.\d+)?)\b", lambda m: _replace_currency(m.group(1), "Indian rupees", "paisa"), s)
    s = re.sub(r"¥\s*(\d+(?:\.\d+)?)\b", lambda m: f"{integer_to_words(int(float(m.group(1))))} yen", s)

    # 10. Percentages (including negative e.g. -3.5%)
    s = re.sub(r"(-?\d+(?:\.\d+)?)\s*%", lambda m: f"{normalize_numeric_expression(m.group(1))} percent", s)

    # 11. Time expressions (12h AM/PM and 24h clock)
    def _replace_time_ampm(m):
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

    s = re.sub(r"\b(\d{1,2}):(\d{2})\s*(am|pm|AM|PM)\b", _replace_time_ampm, s)

    def _replace_time_24h(m):
        hour = int(m.group(1))
        minute = int(m.group(2))
        peri = "P M" if hour >= 12 else "A M"
        h12 = hour % 12
        if h12 == 0:
            h12 = 12
        h_str = integer_to_words(h12)
        if minute == 0:
            m_str = ""
        elif minute < 10:
            m_str = f" oh {integer_to_words(minute)}"
        else:
            m_str = f" {integer_to_words(minute)}"
        return f"{h_str}{m_str} {peri}"

    s = re.sub(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", _replace_time_24h, s)

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

    # 14. Version tags (v2, v3, v2.5, v1.2.3)
    s = re.sub(
        r"\bv(\d+)\.(\d+)(?:\.(\d+))?\b",
        lambda m: f"version {m.group(1)} point {m.group(2)}" + (f" point {m.group(3)}" if m.group(3) else ""),
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(r"\bv(\d+)\b", r"version \1", s, flags=re.IGNORECASE)

    # 15. Standalone Years (1900-2099)
    s = re.sub(r"\b(19\d{2}|20\d{2})\b", lambda m: year_to_words(int(m.group(1))), s)

    # 16. Technical terms
    s = re.sub(r"(?<!\w)C\+\+(?!\w)", "C plus plus", s)
    s = re.sub(r"(?<!\w)C#(?!\w)", "C sharp", s)
    s = re.sub(r"\.NET\b", "dot net", s, flags=re.IGNORECASE)
    s = re.sub(r"\bNode\.js\b", "Node dot J S", s, flags=re.IGNORECASE)
    s = re.sub(r"\bVue\.js\b", "Vue dot J S", s, flags=re.IGNORECASE)
    s = re.sub(r"\bReact\.js\b", "React dot J S", s, flags=re.IGNORECASE)

    # 17. Mathematical Expressions
    s = re.sub(r"(\b[a-zA-Z0-9]+)\^(\d+)\b", r"\1 to the power of \2", s)
    s = re.sub(r"(\d+)\s*\+\s*(\d+)", r"\1 plus \2", s)
    s = re.sub(r"(\d+)\s*-\s*(\d+)", r"\1 minus \2", s)
    s = re.sub(r"(\d+)\s*[*×]\s*(\d+)", r"\1 times \2", s)
    s = re.sub(r"(\d+)\s*[/÷]\s*(\d+)", r"\1 divided by \2", s)
    s = re.sub(r"(\b[a-zA-Z0-9_]+)\s*!=\s*([a-zA-Z0-9_]+\b)", r"\1 does not equal \2", s)
    s = re.sub(r"(\b[a-zA-Z0-9_]+)\s*<=\s*([a-zA-Z0-9_]+\b)", r"\1 is less than or equal to \2", s)
    s = re.sub(r"(\b[a-zA-Z0-9_]+)\s*>=\s*([a-zA-Z0-9_]+\b)", r"\1 is greater than or equal to \2", s)
    s = re.sub(r"(\b[a-zA-Z0-9_]+)\s*=\s*([a-zA-Z0-9_]+\b)", r"\1 equals \2", s)
    s = re.sub(r"(\d+)\s*<\s*(\d+)", r"\1 is less than \2", s)
    s = re.sub(r"(\d+)\s*>\s*(\d+)", r"\1 is greater than \2", s)
    s = re.sub(r"±\s*(\d+)", r"plus or minus \1", s)

    # 18. File Paths (Windows & POSIX)
    def _replace_win_path(m):
        drive = m.group(1).upper()
        rest = m.group(2).replace("\\", " slash ")
        rest = re.sub(r"\.([a-zA-Z0-9]{1,4})\b", r" dot \1", rest)
        return f"{drive} drive slash {rest}"
    s = re.sub(r"\b([A-Za-z]):\\([A-Za-z0-9_.\-\\]+)\b", _replace_win_path, s)

    def _replace_unix_path(m):
        p_str = m.group(0).replace("/", " slash ")
        p_str = re.sub(r"\.([a-zA-Z0-9]{1,4})\b", r" dot \1", p_str)
        return p_str
    s = re.sub(r"(?<!\w)/(?:[A-Za-z0-9_.\-]+/)+[A-Za-z0-9_.\-]+", _replace_unix_path, s)

    # 19. Domain Pronunciation Dictionary (acronyms, frameworks, brands)
    s = pronunciation_dictionary.apply(s)

    # 20. Remaining standalone decimals
    def _replace_decimal(m):
        whole = integer_to_words(int(m.group(1)))
        frac_digits = " ".join(integer_to_words(int(d)) for d in m.group(2) if d.isdigit())
        return f"{whole} point {frac_digits}"

    s = re.sub(r"\b(\d+)\.(\d+)\b", _replace_decimal, s)

    # 20b. Negative integers
    s = re.sub(r"(?:(?<=\s)|^)-(\d+)\b", lambda m: f"negative {integer_to_words(int(m.group(1)))}", s)

    # 20c. Remaining standalone integers
    s = re.sub(r"\b(\d+)\b", lambda m: integer_to_words(int(m.group(1))), s)

    # 21. Clean up symbols & whitespace
    s = re.sub(r"[#*~`|]", " ", s)
    s = re.sub(r"(^|\s)_+|_+(\s|$)", r"\1 \2", s)
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\s+([.,!?;:])", r"\1", s)

    return s.strip()
