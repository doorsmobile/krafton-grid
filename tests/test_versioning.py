import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("bump", Path(__file__).resolve().parents[1] / "scripts" / "bump_version.py")
bump = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bump)


def test_single_digit_minor_wrap():
    assert bump.bump("1.8") == "1.9"
    assert bump.bump("1.9") == "2.0"
    assert bump.bump("2.0") == "2.1"
    assert bump.bump("2.4", major=True) == "3.0"
    with pytest.raises(SystemExit):
        bump.parse("1.10")


def test_sync_keeps_history():
    text = "<!-- RELEASE:START --> grid-claude-v2.0 <!-- RELEASE:END --> run grid-claude-v2.0 · was grid-claude-v1.0"
    out = bump.sync(text, "2.0", "2.1")
    assert "grid-claude-v2.1 <!-- RELEASE:END --> run grid-claude-v2.1" in out and "grid-claude-v1.0" in out


def test_release_name_contains_claude():
    from app import config
    assert "claude" in config.RELEASE_NAME and config.APP_PORT == 8003
