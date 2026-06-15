"""Tests for configuration loading and validation."""

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from court_bot.core.config import load_config, generate_example_config, AppConfig


class TestConfigLoading:
    """Test YAML config loading and Pydantic validation."""

    def test_generate_example_config_is_valid_yaml(self):
        text = generate_example_config()
        data = yaml.safe_load(text)
        assert isinstance(data, dict)
        assert "platform" in data

    def test_load_minimal_config(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            f.write(generate_example_config())
            path = f.name

        try:
            config = load_config(path)
            assert isinstance(config, AppConfig)
            assert config.platform == "wechat_miniapp"
            assert config.schedule.open_time == "20:00:00"
            assert isinstance(config.booking.preferred_courts, list)
        finally:
            os.unlink(path)

    def test_env_var_interpolation(self, monkeypatch):
        """Test that ${VAR} patterns are expanded from environment."""
        monkeypatch.setenv("TEST_PASSWORD", "secret123")

        yaml_content = """
platform: wechat_miniapp
auth:
  student_id: "test_user"
  password: "${TEST_PASSWORD}"
booking:
  court_type: ""
  date_offset: 1
  preferred_times: []
  preferred_courts: []
schedule:
  open_time: "20:00:00"
notify: {}
advanced: {}
custom: {}
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            f.write(yaml_content)
            path = f.name

        try:
            config = load_config(path)
            assert config.auth.password == "secret123"
        finally:
            os.unlink(path)

    def test_load_nonexistent_file(self):
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/path/config.yaml")


class TestAppConfig:
    """Test Pydantic model defaults."""

    def test_defaults(self):
        cfg = AppConfig()
        assert cfg.platform == "wechat_miniapp"
        assert cfg.schedule.open_time == "20:00:00"
        assert cfg.advanced.retry_count == 3
        assert cfg.advanced.ntp_server == "ntp.aliyun.com"
        assert cfg.booking.fallback_to_any is True
