"""Tests for ticker symbol validation."""

import pytest

from app.market.tickers import TICKER_PATTERN, normalize_ticker


class TestNormalizeTicker:
    """Unit tests for normalize_ticker."""

    def test_uppercases(self):
        assert normalize_ticker("aapl") == "AAPL"

    def test_strips_whitespace(self):
        assert normalize_ticker("  AAPL  ") == "AAPL"

    def test_accepts_single_letter(self):
        assert normalize_ticker("v") == "V"

    def test_accepts_five_letters(self):
        assert normalize_ticker("zzzzz") == "ZZZZZ"

    def test_rejects_six_letters(self):
        with pytest.raises(ValueError):
            normalize_ticker("ZZZZZZ")

    def test_rejects_empty_string(self):
        with pytest.raises(ValueError):
            normalize_ticker("")

    def test_rejects_whitespace_only(self):
        with pytest.raises(ValueError):
            normalize_ticker("   ")

    def test_rejects_digits(self):
        with pytest.raises(ValueError):
            normalize_ticker("12345")

    def test_rejects_words_with_spaces(self):
        with pytest.raises(ValueError):
            normalize_ticker("hello world")

    def test_rejects_symbols(self):
        with pytest.raises(ValueError):
            normalize_ticker("AA-PL")

    def test_error_message_includes_original_input(self):
        with pytest.raises(ValueError, match="hello world"):
            normalize_ticker("hello world")


class TestTickerPattern:
    """Sanity checks on the shared regex, independent of normalize_ticker."""

    def test_matches_well_formed_ticker(self):
        assert TICKER_PATTERN.match("AAPL")

    def test_does_not_match_lowercase(self):
        assert TICKER_PATTERN.match("aapl") is None

    def test_does_not_match_empty(self):
        assert TICKER_PATTERN.match("") is None
