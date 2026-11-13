"""
Unit tests for J.A.R.V.I.S. Speech-Specific Text Normalization Subsystem (Python).
"""

import pytest
from app.voice.normalizer import (
    normalize_text_for_speech,
    integer_to_words,
    year_to_words,
    register_pronunciation,
    lookup_pronunciation,
)


class TestSpeechNormalizer:
    def test_integer_to_words(self):
        assert integer_to_words(0) == "zero"
        assert integer_to_words(5) == "five"
        assert integer_to_words(13) == "thirteen"
        assert integer_to_words(25) == "twenty-five"
        assert integer_to_words(100) == "one hundred"
        assert integer_to_words(500) == "five hundred"
        assert integer_to_words(1234) == "one thousand two hundred thirty-four"

    def test_currency_normalization(self):
        # NPR
        res_npr = normalize_text_for_speech("The total is NPR 500.")
        assert "five hundred Nepalese rupees" in res_npr

        # USD
        res_usd = normalize_text_for_speech("The server cost $25.")
        assert "twenty-five dollars" in res_usd

        # Decimals in currency
        res_usd_cents = normalize_text_for_speech("Balance is $3.50.")
        assert "three dollars and fifty cents" in res_usd_cents

    def test_percentage_normalization(self):
        res = normalize_text_for_speech("Success rate reached 25% today.")
        assert "twenty-five percent" in res

        res_dec = normalize_text_for_speech("Growth is 3.5%.")
        assert "three point five percent" in res_dec

    def test_year_and_date_normalization(self):
        assert year_to_words(2026) == "twenty twenty-six"
        assert year_to_words(1999) == "nineteen ninety-nine"
        assert year_to_words(2000) == "two thousand"

        res = normalize_text_for_speech("Established in 2026.")
        assert "twenty twenty-six" in res

    def test_abbreviations_and_honorifics(self):
        res = normalize_text_for_speech("Dr. Smith said e.g. and etc. are Latin.")
        assert "Doctor Smith" in res
        assert "for example" in res
        assert "etcetera" in res

    def test_technical_acronyms(self):
        res = normalize_text_for_speech("Run the SQL query and parse JSON from the API.")
        assert "sequel" in res
        assert "jason" in res
        assert "A P I" in res

    def test_markdown_and_code_delimiters(self):
        markdown_text = """### System Diagnostic
```python
def calculate():
    return 42
```
* Status: **Online**
Check [docs](https://example.com) for details."""

        spoken = normalize_text_for_speech(markdown_text)
        # Markdown symbols should be stripped
        assert "###" not in spoken
        assert "**" not in spoken
        assert "https://" not in spoken
        assert "System Diagnostic" in spoken
        assert "Status:" in spoken
        assert "Online" in spoken
        assert "Code snippet omitted" in spoken

    def test_extensible_pronunciation_dictionary(self):
        register_pronunciation("K8s", "Kubernetes")
        assert lookup_pronunciation("k8s") == "Kubernetes"

        res = normalize_text_for_speech("Deploying on K8s cluster.")
        assert "Kubernetes" in res
