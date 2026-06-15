"""CAPTCHA solving adapters."""
from court_bot.captcha.solvers import (
    CaptchaSolver,
    TtshituSolver,
    DdddocrSolver,
    TwoCaptchaSolver,
    create_solver,
)

__all__ = [
    "CaptchaSolver",
    "TtshituSolver",
    "DdddocrSolver",
    "TwoCaptchaSolver",
    "create_solver",
]
