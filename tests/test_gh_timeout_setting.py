from unittest.mock import patch

from scripts.ghcall import get_gh_timeout, run_gh


def test_custom_timeout(monkeypatch):
    monkeypatch.setenv("FAIRCODE_GH_TIMEOUT", "120")

    assert get_gh_timeout() == 120

    with patch("scripts.ghcall.subprocess.run") as mock_run:
        run_gh(["gh", "--version"])

        assert mock_run.call_args.kwargs["timeout"] == 120


def test_invalid_timeout(monkeypatch):
    monkeypatch.setenv("FAIRCODE_GH_TIMEOUT", "hello")

    assert get_gh_timeout() == 60


def test_default_timeout(monkeypatch):
    monkeypatch.delenv("FAIRCODE_GH_TIMEOUT", raising=False)

    assert get_gh_timeout() == 60


def test_explicit_timeout(monkeypatch):
    monkeypatch.setenv("FAIRCODE_GH_TIMEOUT", "120")

    with patch("scripts.ghcall.subprocess.run") as mock_run:
        run_gh(["gh", "--version"], timeout=15)

        assert mock_run.call_args.kwargs["timeout"] == 15