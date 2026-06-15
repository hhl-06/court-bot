# 🏸 Court Bot

<div align="center">

**Automated sports court booking with precision scheduling, multi-platform support, and rich notifications.**

[![CI](https://github.com/yourusername/court-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/yourusername/court-bot/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Docker](https://img.shields.io/badge/docker-ready-blue)](Dockerfile)

</div>

---

## What is Court Bot?

Court Bot automatically reserves sports courts (badminton, tennis, basketball, etc.) the moment booking opens. It intercepts and replays API calls to submit your reservation faster than any human can tap through a mini program or web form.

**How it works:**

```
📱 WeChat Mini Program / Web Portal
        ↓  (packet capture: mitmproxy / Charles)
🔍 Reverse-engineer the HTTP API
        ↓
🐍 Python script replays the API calls
        ↓
⏱️ NTP-synced precision timing fires at exactly opening time
        ↓
✅ Booking submitted in milliseconds
        ↓
📲 Notification pushed to your phone
```

## ✨ Features

- ⚡ **Sub-second precision** — NTP time sync + busy-wait scheduling beats human reaction time
- 📱 **Multi-platform** — WeChat Mini Programs, web portals, or any REST API
- 🔐 **Flexible auth** — Password, token, WeChat OAuth, or pre-obtained sessions
- 📡 **Multi-channel notifications** — Bark, DingTalk, Server酱, PushPlus, Telegram, Email
- 🎨 **Beautiful CLI** — Rich-powered terminal UI with live status
- 🐳 **Docker ready** — Run anywhere with a single command
- 🧩 **Pluggable architecture** — Add new platforms without touching core logic
- 🔁 **Auto-retry with fallback** — Tries your top picks first, falls back to any available slot
- 🛡️ **Rate-limited** — Configurable request throttling to avoid anti-bot detection

## 📋 Supported Platforms

| Platform | Adapter | Status |
|----------|---------|--------|
| WeChat Mini Program (微信小程序) | `wechat_miniapp` | ✅ Stable |
| Generic web portal (Selenium) | `web_portal` | 🚧 Beta |
| Custom REST API (config-driven) | `custom_api` | ✅ Stable |

> **Adding your school's system:** Court Bot is designed to be extended. See [CONTRIBUTING.md](CONTRIBUTING.md) to add a platform adapter for your school.

## 🚀 Quick Start

### 1. Installation

```bash
# From PyPI (recommended)
pip install court-bot

# Or from source (for latest features)
git clone https://github.com/yourusername/court-bot.git
cd court-bot
pip install -e .
```

### 2. Generate Config

```bash
court-bot init-config
```

This creates `config/config.yaml` — edit it with your account and preferences.

### 3. Capture API (WeChat Mini Program)

**You must capture the API calls from the mini program before Court Bot can book for you.** This is a one-time setup.

<details>
<summary><b>📖 Step-by-step packet capture guide (click to expand)</b></summary>

#### Install mitmproxy
```bash
pip install mitmproxy
```

#### Start the proxy
```bash
mitmweb --listen-port 8080
```
This opens a web interface at `http://127.0.0.1:8081`.

#### Configure your phone
- **iPhone:** Settings → Wi-Fi → ⓘ → HTTP Proxy → Manual
  - Server: your computer's LAN IP
  - Port: 8080
- **Android:** Settings → WLAN → long-press Wi-Fi → Modify → Manual proxy

#### Install the CA certificate
- Open `http://mitm.it` on your phone's browser
- Download and install the certificate
- **iPhone only:** Settings → General → About → Certificate Trust Settings → Enable mitmproxy

#### Capture the booking flow
1. Open WeChat → your booking mini program
2. Walk through the FULL flow: login → view courts → view time slots → submit a booking
3. In mitmweb, find and export the API requests

#### What to capture
| # | API Request | Purpose |
|---|------------|---------|
| 1 | Login request | Auth token format |
| 2 | Court list | Court IDs and names |
| 3 | Time slots | Slot IDs and availability |
| 4 | Submit booking | **The core booking request** |
| 5 | My bookings | Verification |

</details>

### 4. Configure the Platform Adapter

Edit `src/court_bot/platforms/wechat_miniapp.py` and replace all `YOUR_*` / `← CHANGE ME` placeholders with values from your packet capture.

Key things to set:
- `BASE_URL` — your school's API domain
- `ENDPOINT_*` — the API endpoint paths
- `AUTH_HEADER_NAME` — how the token is sent (Authorization, token, etc.)
- JSON field paths in each method

### 5. Run!

```bash
# See available slots for tomorrow
court-bot slots

# Dry run — fetch everything but don't book
court-bot run --dry-run

# 🚀 The real thing — wait for opening time and book
court-bot run

# Book immediately (for testing)
court-bot run --now

# Check your existing bookings
court-bot list

# Cancel a booking
court-bot cancel <booking-id>
```

## 🐳 Docker

```bash
# Build
docker build -t court-bot .

# Run with mounted config
docker run -v $(pwd)/config:/app/config court-bot run

# Or use docker-compose
cp config/config.example.yaml config/config.yaml
# Edit config/config.yaml...
docker compose run --rm court-bot run
```

## 📁 Project Structure

```
court-bot/
├── src/court_bot/
│   ├── cli/main.py              # Typer CLI entry point
│   ├── core/
│   │   ├── config.py            # YAML + Pydantic config
│   │   ├── scheduler.py         # Booking orchestrator
│   │   └── time_sync.py         # NTP precision timing
│   ├── platforms/
│   │   ├── base.py              # Abstract platform interface
│   │   ├── wechat_miniapp.py    # WeChat Mini Program adapter
│   │   ├── web_portal.py        # Selenium-based web adapter
│   │   └── custom_api.py        # Config-driven REST API adapter
│   ├── notify/channels.py       # 6 notification channels
│   ├── captcha/solvers.py       # 3 CAPTCHA solver backends
│   └── utils/
│       ├── http.py              # rate-limited HTTP session
│       └── logger.py            # Rich console logging
├── config/config.example.yaml   # Annotated example config
├── tests/                       # pytest test suite
├── Dockerfile
├── docker-compose.yml
├── .github/workflows/ci.yml     # GitHub Actions CI
├── pyproject.toml               # Package metadata
└── README.md
```

## ⚙️ Configuration Reference

| Section | Key | Description | Default |
|---------|-----|-------------|---------|
| `auth` | `student_id` | Your school ID / username | — |
| `auth` | `password` | Password (use `${ENV_VAR}` for security) | — |
| `booking` | `date_offset` | Book N days ahead | `1` |
| `booking` | `preferred_times` | Time slots by priority | `[]` |
| `booking` | `preferred_courts` | Court numbers by priority | `[]` |
| `schedule` | `open_time` | When booking opens (HH:MM:SS) | `20:00:00` |
| `schedule` | `fire_early_ms` | Compensate network latency (ms) | `80` |
| `advanced` | `retry_count` | Attempts per candidate | `3` |
| `advanced` | `time_sync` | Enable NTP sync | `true` |
| `advanced` | `dry_run` | Fetch but don't submit | `false` |

## 🔧 Common Issues

<details>
<summary><b>WeChat won't connect through mitmproxy</b></summary>

WeChat on some Android versions blocks user-installed CA certificates. Solutions:
1. Use an older Android device (Android 7.0+ enforces certificate pinning for apps targeting API 24+)
2. Root your phone and install the certificate as a system cert
3. Use an iOS device (more permissive about user certificates)
4. Try Charles Proxy or Proxyman instead
</details>

<details>
<summary><b>API has a sign/signature parameter</b></summary>

If requests include a `sign` field (e.g., MD5 hash), the signature algorithm is embedded in the mini program's JavaScript. You'll need to extract it:

```bash
# Use wxappUnpacker to get the mini program source
git clone https://github.com/qwerty472123/wxappUnpacker.git
# Then analyze the unpacked JS for signature logic
```

Add the signature function to the `wechat_miniapp.py` adapter's `submit_booking` method.
</details>

<details>
<summary><b>Token expires quickly</b></summary>

If your auth token expires during the wait, set `pre_fetch_seconds` high enough to catch token expiry and re-authenticate. The scheduler refreshes auth before pre-fetching.
</details>

## 🧪 Development

```bash
# Install with dev tools
pip install -e ".[dev]"

# Run tests
pytest tests/ -v --cov=court_bot

# Lint
ruff check src/ tests/

# Type check
mypy src/
```

## 📄 License

MIT — see [LICENSE](LICENSE)

## ⚠️ Disclaimer

This tool is for **educational purposes**. Use it responsibly and in accordance with your school's policies. Excessive automated requests may trigger anti-bot measures. The authors are not responsible for any account restrictions or penalties resulting from use of this software.

---

<div align="center">
Made with ❤️ for students who want their court time.
</div>
