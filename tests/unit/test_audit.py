"""Unit tests for core/audit.py — _redact helper."""

import pytest

from core.audit import _redact


# ── _redact ───────────────────────────────────────────────────────────────────


def test_redact_password_key():
    assert _redact({"password": "secret123"}) == {"password": "[REDACTED]"}


def test_redact_token_key():
    assert _redact({"token": "Bearer abc"}) == {"token": "[REDACTED]"}


def test_redact_api_key():
    assert _redact({"api_key": "sk-123"}) == {"api_key": "[REDACTED]"}


def test_redact_kubeconfig():
    assert _redact({"kubeconfig": "/path/to/kube"}) == {"kubeconfig": "[REDACTED]"}


def test_redact_authorization_header():
    assert _redact({"Authorization": "Bearer tok"}) == {"Authorization": "[REDACTED]"}


def test_redact_nested():
    obj = {"outer": {"password": "x", "safe": "y"}}
    result = _redact(obj)
    assert result["outer"]["password"] == "[REDACTED]"
    assert result["outer"]["safe"] == "y"


def test_redact_list():
    obj = [{"password": "x"}, {"safe": "y"}]
    result = _redact(obj)
    assert result[0]["password"] == "[REDACTED]"
    assert result[1]["safe"] == "y"


def test_redact_safe_key_unchanged():
    assert _redact({"prom_url": "http://prom.example.com"}) == {"prom_url": "http://prom.example.com"}


def test_redact_long_string_truncated():
    long_str = "a" * 600
    result = _redact(long_str)
    assert len(result) < 600
    assert result.endswith("…[truncated]")


def test_redact_short_string_unchanged():
    assert _redact("hello") == "hello"


def test_redact_secret_key_case_insensitive():
    assert _redact({"SECRET_KEY": "hidden"}) == {"SECRET_KEY": "[REDACTED]"}
