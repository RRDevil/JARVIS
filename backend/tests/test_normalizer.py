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

    def test_comma_separated_and_standalone_numbers(self):
        res = normalize_text_for_speech("Processed 1,250 requests out of 42 batches.")
        assert "one thousand two hundred fifty requests" in res
        assert "forty-two batches" in res

    def test_negative_numbers(self):
        res = normalize_text_for_speech("The temperature is -5 degrees and offset is -12.")
        assert "negative five degrees" in res
        assert "negative twelve" in res

    def test_programming_languages_cpp_and_csharp(self):
        res = normalize_text_for_speech("Writing routines in C++ and building in C#.")
        assert "C plus plus" in res
        assert "C sharp" in res

    def test_email_address_normalization(self):
        res = normalize_text_for_speech("Contact support@jarvis.ai for assistance.")
        assert "support at jarvis dot A I" in res

    def test_metric_and_time_units(self):
        res = normalize_text_for_speech("Latency is 0.21s with 15ms buffer and 100MB memory.")
        assert "zero point two one seconds" in res
        assert "fifteen milliseconds" in res
        assert "one hundred megabytes" in res

    def test_file_paths_windows_and_posix(self):
        res_win = normalize_text_for_speech("Check C:\\Windows\\System32\\config.sys file.")
        assert "C drive slash Windows slash System32 slash config dot sys" in res_win

        res_posix = normalize_text_for_speech("Check /var/log/syslog file.")
        assert "slash var slash log slash syslog" in res_posix

    def test_expanded_cross_language_parity_corpus(self):
        # ISO Calendar Dates
        res_date = normalize_text_for_speech("Release date is 2026-11-13.")
        assert "November thirteenth, twenty twenty-six" in res_date

        # Durations
        res_dur = normalize_text_for_speech("Execution lasted 2h 30m.")
        assert "two hours thirty minutes" in res_dur

        # 24-hour time format
        res_24 = normalize_text_for_speech("Meeting at 14:30 sharp.")
        assert "two thirty P M" in res_24

        # IPv4 addresses
        res_ip = normalize_text_for_speech("Connected to 192.168.1.1 successfully.")
        assert "one hundred ninety-two dot one hundred sixty-eight dot one dot one" in res_ip

        # Semantic versions
        res_ver = normalize_text_for_speech("Upgraded to v1.2.3 today.")
        assert "version one point two point three" in res_ver

        # Rs currency
        res_rs = normalize_text_for_speech("Invoice total is Rs. 500.")
        assert "five hundred rupees" in res_rs

        # Negative percentages
        res_neg_pct = normalize_text_for_speech("Variance is -3.5% overall.")
        assert "negative three point five percent" in res_neg_pct
