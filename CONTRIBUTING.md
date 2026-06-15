# Contributing to Court Bot

Thanks for your interest in contributing! 🎉

## Ways to Contribute

### 1. Add a Platform Adapter

The most valuable contribution is adding support for a new booking system.

1. Create a new file in `src/court_bot/platforms/` (e.g., `my_university.py`)
2. Subclass `BasePlatform` and implement all abstract methods
3. Register it in `src/court_bot/platforms/__init__.py`
4. Add tests in `tests/`
5. Submit a PR with a description of the system

### 2. Improve Existing Adapters

- Better error handling for edge cases
- Support for additional auth methods (OAuth, SSO, CAS)
- More robust JSON response parsing
- Adding unit tests with mock HTTP responses

### 3. Add Notification Channels

New notification providers are always welcome:

1. Add a `_yourchannel(self, title, body) -> bool | None` method to `Notifier`
2. Add the config field to `NotifyConfig` in `core/config.py`
3. Return `None` if not configured, `True` on success, `False` on failure

### 4. Report Bugs / Request Features

Open an issue with:
- Your school's booking system type (WeChat mini program / website / custom)
- Steps to reproduce
- Any error logs or screenshots

## Development Setup

```bash
# Clone and install with dev dependencies
git clone https://github.com/yourusername/court-bot.git
cd court-bot
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Type checking
mypy src/

# Linting
ruff check src/ tests/
```

## Code Style

- Python 3.10+ compatible
- Type hints on all public methods
- Docstrings in Google style
- 100 character line limit
- Follow existing patterns in the codebase

## PR Checklist

- [ ] Tests pass (`pytest tests/ -v`)
- [ ] New code has type hints
- [ ] New platform/method has a docstring
- [ ] Updated README if adding major features
- [ ] No breaking changes to the `BasePlatform` interface
