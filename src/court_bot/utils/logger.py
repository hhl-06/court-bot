"""Logging setup with Rich handler for beautiful console output."""

import logging
from pathlib import Path
from datetime import datetime

from rich.logging import RichHandler
from rich.console import Console


def setup_logging(
    level: str = "INFO",
    log_dir: str = "logs",
    console: Console | None = None,
) -> Path:
    """
    Configure logging with both console (Rich) and file handlers.

    Returns the path to the log file created for this session.
    """
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    log_file = log_path / f"court_bot_{datetime.now():%Y%m%d_%H%M%S}.log"

    # File handler: detailed, plain text
    file_fmt = logging.Formatter(
        "%(asctime)s.%(msecs)03d | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fh = logging.FileHandler(str(log_file), encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(file_fmt)

    # Console handler: Rich output (with CJK-safe encoding)
    try:
        _console = console or Console(encoding="utf-8", force_terminal=True)
    except Exception:
        _console = Console()
    ch = RichHandler(
        console=_console,
        show_time=True,
        show_level=True,
        show_path=False,
        rich_tracebacks=False,  # avoid encoding issues on Windows GBK
    )
    ch.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Root logger
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(fh)
    root.addHandler(ch)

    # Quiet down noisy third-party loggers
    for noisy in ["httpx", "httpcore", "urllib3", "apscheduler"]:
        logging.getLogger(noisy).setLevel(logging.WARNING)

    return log_file
