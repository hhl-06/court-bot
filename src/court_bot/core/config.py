"""
Configuration management with YAML, env vars, and Pydantic validation.

Supports:
- Loading from YAML file
- Environment variable interpolation (${VAR_NAME})
- CLI overrides via --set key=value
- Pydantic model for type safety
"""

import os
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


# ── Pydantic models for validated config ──────────────────

class AuthConfig(BaseModel):
    """Authentication configuration."""
    student_id: str = ""
    password: str = ""
    login_type: str = "auto"  # auto, wechat, cas, direct, token
    token: str = ""           # pre-obtained token (bypass login)
    refresh_token: str = ""   # refresh token (extends token lifetime)
    token_expiration: str = ""# token expiration time "YYYY-MM-DD HH:MM:SS"
    wechat_code: str = ""     # wx.login() code for WeChat OAuth
    auth_url: str = ""        # custom login endpoint
    refresh_url: str = ""     # token refresh endpoint
    extra: dict[str, Any] = Field(default_factory=dict)


class BookingConfig(BaseModel):
    """Booking preferences."""
    court_type: str = ""
    date_offset: int = 1
    target_day_of_week: str = ""  # e.g. "Friday", "星期五" — overrides date_offset
    preferred_times: list[str] = Field(default_factory=list)
    preferred_courts: list[int] = Field(default_factory=list)
    consecutive_slots: int = 1  # book N consecutive slots on the same court
    fallback_to_any: bool = True
    max_candidates: int = 20
    time_window: str = ""  # 只在此时段内回退，如 "18:30-21:30"；空=不限


class ScheduleConfig(BaseModel):
    """Timing configuration."""
    open_time: str = "20:00:00"
    pre_fetch_seconds: int = 5
    fire_early_ms: int = 80
    timezone: str = "Asia/Shanghai"


class NotifyConfig(BaseModel):
    """Notification channel configuration."""
    bark_key: str = ""
    dingtalk_webhook: str = ""
    server_chan_key: str = ""
    pushplus_token: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    email_smtp_host: str = ""
    email_smtp_port: int = 465
    email_sender: str = ""
    email_password: str = ""
    email_receiver: str = ""


class AdvancedConfig(BaseModel):
    """Advanced tuning options."""
    retry_count: int = 3
    retry_interval: float = 0.15
    time_sync: bool = True
    ntp_server: str = "ntp.aliyun.com"
    request_timeout: float = 8.0
    rate_limit: float = 5.0
    dry_run: bool = False
    log_level: str = "INFO"


class AppConfig(BaseModel):
    """Top-level application configuration."""
    platform: str = "wechat_miniapp"
    auth: AuthConfig = Field(default_factory=AuthConfig)
    booking: BookingConfig = Field(default_factory=BookingConfig)
    schedule: ScheduleConfig = Field(default_factory=ScheduleConfig)
    notify: NotifyConfig = Field(default_factory=NotifyConfig)
    advanced: AdvancedConfig = Field(default_factory=AdvancedConfig)
    custom: dict[str, Any] = Field(default_factory=dict)


# ── Config loader ─────────────────────────────────────────

_ENV_PATTERN = re.compile(r"\$\{(\w+)\}")


def _resolve_env_vars(value: Any) -> Any:
    """Recursively expand ${VAR_NAME} environment variable references."""
    if isinstance(value, str):
        def _replacer(m: re.Match) -> str:
            return os.environ.get(m.group(1), m.group(0))
        return _ENV_PATTERN.sub(_replacer, value)
    if isinstance(value, dict):
        return {k: _resolve_env_vars(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_env_vars(v) for v in value]
    return value


def load_config(path: str | Path) -> AppConfig:
    """
    Load and validate configuration from a YAML file.

    Environment variables in the form ${VAR_NAME} are automatically expanded.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    raw = _resolve_env_vars(raw)
    config = AppConfig(**raw)
    # 把源文件路径存到 config 上，供平台适配器把刷新后的 token 持久化回文件。
    # Pydantic 会拒绝未知字段赋值，所以绕过 __setattr__。
    object.__setattr__(config, "_config_path", str(path))
    return config


def generate_example_config() -> str:
    """Generate a well-commented example configuration YAML."""
    return """\
# ============================================================
# Court Bot — Example Configuration
# ============================================================
# Copy this to config/config.yaml and fill in your details.
# Sensitive values can use ${ENV_VAR} syntax.

# ── Platform ──────────────────────────────────────────────
# Supported: wechat_miniapp | web_portal | custom_api
platform: wechat_miniapp

# ── Authentication ────────────────────────────────────────
auth:
  student_id: "2021001234"
  password: "${COURT_BOT_PASSWORD}"
  login_type: auto
  token: ""
  refresh_token: ""
  token_expiration: ""
  wechat_code: ""

# ── Booking Preferences ───────────────────────────────────
booking:
  court_type: "羽毛球"
  date_offset: 1
  target_day_of_week: "星期五"
  preferred_times:
    - "18:30-19:30"
  preferred_courts: [6, 7, 8, 9, 10]
  consecutive_slots: 2
  fallback_to_any: true

# ── Schedule ──────────────────────────────────────────────
schedule:
  open_time: "20:00:00"
  pre_fetch_seconds: 5
  fire_early_ms: 80
  timezone: "Asia/Shanghai"
  run_day: "星期四"
  run_time: "07:00"

# ── Notifications ─────────────────────────────────────────
# At least one channel recommended.
notify:
  bark_key: ""
  dingtalk_webhook: ""
  server_chan_key: ""
  pushplus_token: ""
  telegram_bot_token: ""
  telegram_chat_id: ""

# ── Advanced ──────────────────────────────────────────────
advanced:
  retry_count: 3
  retry_interval: 0.15
  time_sync: true
  ntp_server: "ntp.aliyun.com"
  request_timeout: 8.0
  rate_limit: 5.0
  dry_run: false
  log_level: "INFO"

# ── Custom (platform-specific) ────────────────────────────
custom: {}
"""
