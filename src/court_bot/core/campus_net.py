"""
校园网自动登录 — 南京中医药大学 Dr.COM 认证系统

登录接口: POST http://net.njucm.edu.cn/api/portal/v1/login
认证方式: PAP (明文密码)
"""

import logging

import httpx

logger = logging.getLogger(__name__)

PORTAL_URL = "http://net.njucm.edu.cn"
LOGIN_ENDPOINT = "/api/portal/v1/login"


def campus_network_login(username: str, password: str, domain: str = "") -> bool:
    """
    登录校园网认证系统。

    Args:
        username: 学号
        password: 校园网密码
        domain: 运营商，留空为校园网

    Returns:
        True if login successful
    """
    if not username or not password:
        logger.warning("未配置校园网账号，跳过自动登录")
        return False

    logger.info("正在登录校园网 (%s)...", username)

    try:
        resp = httpx.post(
            f"{PORTAL_URL}{LOGIN_ENDPOINT}",
            json={
                "domain": domain,
                "username": username,
                "password": password,
            },
            timeout=10,
        )
        data = resp.json()

        reply_code = data.get("reply_code", -1)
        if reply_code == 0:
            logger.info("校园网登录成功 ✓")
            return True

        # reply_code 255 = already logged in
        if reply_code == 255:
            logger.info("校园网已在线, 无需重复登录")
            return True

        logger.warning("校园网登录失败: reply_code=%s, msg=%s",
                       reply_code, data.get("reply_msg", ""))
        return False

    except Exception as e:
        logger.error("校园网登录异常: %s", e)
        return False
