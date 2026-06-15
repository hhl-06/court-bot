"""
Platform abstraction layer.

Each booking platform (WeChat Mini Program, web portal, custom API, etc.)
implements the BasePlatform interface so the scheduler can work uniformly.

To add a new platform:
  1. Create a new module in this package
  2. Subclass BasePlatform
  3. Implement all abstract methods
  4. Register it in PLATFORM_REGISTRY
"""

from court_bot.platforms.base import BasePlatform
from court_bot.platforms.wechat_miniapp import WechatMiniAppPlatform
from court_bot.platforms.web_portal import WebPortalPlatform
from court_bot.platforms.custom_api import CustomAPIPlatform

PLATFORM_REGISTRY: dict[str, type[BasePlatform]] = {
    "wechat_miniapp": WechatMiniAppPlatform,
    "web_portal": WebPortalPlatform,
    "custom_api": CustomAPIPlatform,
}


def get_platform(name: str) -> type[BasePlatform]:
    """Look up a platform class by name. Raises KeyError if not found."""
    if name not in PLATFORM_REGISTRY:
        available = ", ".join(PLATFORM_REGISTRY)
        raise KeyError(f"Unknown platform '{name}'. Available: {available}")
    return PLATFORM_REGISTRY[name]


__all__ = [
    "BasePlatform",
    "WechatMiniAppPlatform",
    "WebPortalPlatform",
    "CustomAPIPlatform",
    "PLATFORM_REGISTRY",
    "get_platform",
]
