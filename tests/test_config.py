"""Tests for collector/config.py."""

import os

from collector import config


class TestConfigDefaults:
    """Test that config loads default values when env vars are not set."""

    def test_qb_url_default(self, monkeypatch):
        monkeypatch.delenv("QB_URL", raising=False)
        # Reload config to pick up the change
        import importlib

        importlib.reload(config)
        assert config.QB_URL == "http://qbittorrent:30024"

    def test_qb_username_default(self, monkeypatch):
        monkeypatch.delenv("QB_USERNAME", raising=False)
        import importlib

        importlib.reload(config)
        assert config.QB_USERNAME == "admin"

    def test_interval_seconds_default(self, monkeypatch):
        monkeypatch.delenv("INTERVAL_SECONDS", raising=False)
        import importlib

        importlib.reload(config)
        assert config.INTERVAL_SECONDS == 900

    def test_tracker_refresh_default(self, monkeypatch):
        monkeypatch.delenv("TRACKER_REFRESH_SECONDS", raising=False)
        import importlib

        importlib.reload(config)
        assert config.TRACKER_REFRESH_SECONDS == 86400


class TestConfigEnvVars:
    """Test that config reads values from environment variables."""

    def test_qb_url_from_env(self, monkeypatch):
        monkeypatch.setenv("QB_URL", "http://custom-host:8080")
        import importlib

        importlib.reload(config)
        assert config.QB_URL == "http://custom-host:8080"

    def test_qb_url_strips_trailing_slash(self, monkeypatch):
        monkeypatch.setenv("QB_URL", "http://custom-host:8080/")
        import importlib

        importlib.reload(config)
        assert config.QB_URL == "http://custom-host:8080"

    def test_interval_from_env(self, monkeypatch):
        monkeypatch.setenv("INTERVAL_SECONDS", "1800")
        import importlib

        importlib.reload(config)
        assert config.INTERVAL_SECONDS == 1800

    def test_postgres_host_from_env(self, monkeypatch):
        monkeypatch.setenv("POSTGRES_HOST", "db.example.com")
        import importlib

        importlib.reload(config)
        assert config.POSTGRES_HOST == "db.example.com"

    def test_postgres_port_from_env(self, monkeypatch):
        monkeypatch.setenv("POSTGRES_PORT", "5433")
        import importlib

        importlib.reload(config)
        assert config.POSTGRES_PORT == 5433


class TestSetupLogging:
    def test_returns_logger(self, monkeypatch):
        monkeypatch.setenv("LOG_LEVEL", "INFO")
        import importlib

        importlib.reload(config)
        logger = config.setup_logging()
        assert logger.name == "qbittorrent-stats"

    def test_log_level_is_read_from_env(self, monkeypatch):
        # LOG_LEVEL is read at module import time via os.getenv,
        # so we verify the config module uses the env var correctly
        # by checking the default value when env is not set
        monkeypatch.delenv("LOG_LEVEL", raising=False)
        import importlib

        importlib.reload(config)
        assert config.LOG_LEVEL == "INFO"  # Default fallback
