"""
CAPTCHA / verification-code solvers.

Plug in a solver if your booking system has image captchas.
"""

from __future__ import annotations

import base64
import logging
from abc import ABC, abstractmethod

import httpx

logger = logging.getLogger(__name__)


class CaptchaSolver(ABC):
    """Abstract CAPTCHA solver."""

    @abstractmethod
    def solve(self, image_bytes: bytes) -> str:
        """Return the decoded text, or empty string on failure."""
        ...


class TtshituSolver(CaptchaSolver):
    """
    图鉴 (ttshitu.com) — affordable Chinese CAPTCHA service.

    Register at http://www.ttshitu.com, top up, and use your credentials.
    """

    API_URL = "http://api.ttshitu.com/predict"

    def __init__(self, username: str, password: str, typeid: str = "3"):
        self.username = username
        self.password = password
        self.typeid = typeid  # 3 = alphanumeric mix

    def solve(self, image_bytes: bytes) -> str:
        b64 = base64.b64encode(image_bytes).decode()
        try:
            resp = httpx.post(self.API_URL, json={
                "username": self.username,
                "password": self.password,
                "typeid": self.typeid,
                "image": b64,
            }, timeout=15)
            data = resp.json()
            if data.get("success"):
                result = data["data"]["result"]
                logger.info("Ttshitu solved: %s", result)
                return result
            logger.warning("Ttshitu failed: %s", data.get("message"))
            return ""
        except Exception as exc:
            logger.error("Ttshitu error: %s", exc)
            return ""


class DdddocrSolver(CaptchaSolver):
    """
    ddddocr — free, local, offline OCR for simple captchas.

    Install: pip install ddddocr
    Best for: simple 4-char alphanumeric captchas.
    """

    def __init__(self):
        try:
            import ddddocr
            self._ocr = ddddocr.DdddOcr(show_ad=False)
        except ImportError:
            raise ImportError(
                "ddddocr is required for this solver. "
                "Install with: pip install ddddocr"
            ) from None

    def solve(self, image_bytes: bytes) -> str:
        result = self._ocr.classification(image_bytes)
        if result:
            logger.info("ddddocr solved: %s", result)
        return result or ""


class TwoCaptchaSolver(CaptchaSolver):
    """
    2captcha.com — international CAPTCHA service.

    More expensive but supports reCAPTCHA, hCaptcha, etc.
    """

    API_URL = "https://api.2captcha.com/createTask"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def solve(self, image_bytes: bytes) -> str:
        b64 = base64.b64encode(image_bytes).decode()
        try:
            # Create task
            resp = httpx.post(self.API_URL, json={
                "clientKey": self.api_key,
                "task": {
                    "type": "ImageToTextTask",
                    "body": b64,
                },
            }, timeout=30)
            data = resp.json()
            task_id = data.get("taskId")
            if not task_id:
                logger.warning("2captcha create task failed: %s", data)
                return ""

            # Poll for result
            for _ in range(30):
                import time
                time.sleep(2)
                resp2 = httpx.post(
                    "https://api.2captcha.com/getTaskResult",
                    json={"clientKey": self.api_key, "taskId": task_id},
                    timeout=10,
                )
                r = resp2.json()
                if r.get("status") == "ready":
                    result = r["solution"]["text"]
                    logger.info("2captcha solved: %s", result)
                    return result
                if r.get("errorId") != 0:
                    logger.warning("2captcha error: %s", r)
                    return ""

            logger.warning("2captcha timeout")
            return ""
        except Exception as exc:
            logger.error("2captcha error: %s", exc)
            return ""


def create_solver(solver_type: str, **kwargs) -> CaptchaSolver | None:
    """
    Factory to create a CAPTCHA solver from a type name.

    Args:
        solver_type: "ttshitu" | "ddddocr" | "2captcha"
        **kwargs: credentials (username, password, api_key, etc.)
    """
    registry = {
        "ttshitu": TtshituSolver,
        "ddddocr": DdddocrSolver,
        "2captcha": TwoCaptchaSolver,
    }
    cls = registry.get(solver_type)
    if cls is None:
        logger.warning("Unknown captcha solver: %s", solver_type)
        return None
    return cls(**kwargs)
