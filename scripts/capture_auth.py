"""
mitmproxy capture script — auto-extract wechat_code
Only listens for gym.njucm.edu.cn/authserver/wx/login
"""
import re
from pathlib import Path


CONFIG_PATH = Path(__file__).parent.parent / "config" / "config.yaml"


def response(flow):
    """Capture login response, extract authCode + token, write to config."""
    url = flow.request.pretty_url

    if "authserver/wx/login" not in url:
        return

    # Extract authCode from request body
    body = flow.request.get_text()
    match = re.search(r"authCode=([a-zA-Z0-9_-]+)", body)
    if not match:
        return
    auth_code = match.group(1)

    # Extract token from response
    resp_data = flow.response.json()
    token_info = resp_data.get("data", {})
    access_token = token_info.get("accessToken", "")
    refresh_token = token_info.get("refreshToken", "")
    expiration = token_info.get("expiration", "")

    print()
    print("=" * 60)
    print(f"  [OK] authCode: {auth_code}")
    print(f"  Token:     {access_token}")
    print(f"  Refresh:   {refresh_token}")
    print(f"  Expires:   {expiration}")
    print("=" * 60)
    print()

    # Write to config.yaml
    if CONFIG_PATH.exists():
        content = CONFIG_PATH.read_text(encoding="utf-8")
        for old_val, new_val in [
            (r'\bwechat_code:\s*"[^"]*"', f'wechat_code: "{auth_code}"'),
            (r'\btoken:\s*"[^"]*"', f'token: "{access_token}"'),
            (r'\brefresh_token:\s*"[^"]*"', f'refresh_token: "{refresh_token}"'),
            (r'\btoken_expiration:\s*"[^"]*"', f'token_expiration: "{expiration}"'),
        ]:
            content = re.sub(old_val, new_val, content)
        CONFIG_PATH.write_text(content, encoding="utf-8")
        print("  [OK] config.yaml auto-updated!")
        print()
        print("  Test command:")
        print("    cd D:\\Projects\\court-bot")
        print("    python -m court_bot.cli.main --config config\\config.yaml run --now --dry-run")
        print()
