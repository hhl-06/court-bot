"""
mitmproxy 抓包脚本 — 记录 gym.njucm.edu.cn 的全部请求/响应，用于发现「取消/退款」接口。

同时:
  - 自动把 wx/login 的 authCode + token 写回 config.yaml（保持 token 新鲜）
  - 把每个请求的 method/path/请求体/响应体写到 logs/capture_cancel.log

用法:
  mitmdump -s scripts/capture_cancel.py --listen-port 8080
"""
import re
import json
from pathlib import Path
from datetime import datetime

TARGET_HOST = "gym.njucm.edu.cn"
CONFIG_PATH = Path(__file__).parent.parent / "config" / "config.yaml"
LOG_PATH = Path(__file__).parent.parent / "logs" / "capture_cancel.log"

# 请求体里可能含敏感信息，但这里就是要抓取消接口，完整记录
def _log(msg: str) -> None:
    try:
        LOG_PATH.parent.mkdir(exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass


def _fmt_body(text: str) -> str:
    if not text:
        return ""
    # 尝试美化 JSON
    try:
        return json.dumps(json.loads(text), ensure_ascii=False)
    except Exception:
        return text


def request(flow):
    if TARGET_HOST not in (flow.request.host or ""):
        return
    line = f"[{datetime.now():%H:%M:%S}] >>> {flow.request.method} {flow.request.path}"
    body = ""
    try:
        body = flow.request.get_text() or ""
    except Exception:
        try:
            body = flow.request.content.decode("utf-8", "replace")
        except Exception:
            body = ""
    _log(line)
    if body:
        _log("      BODY: " + _fmt_body(body)[:2000])


def response(flow):
    if TARGET_HOST not in (flow.request.host or ""):
        return
    status = flow.response.status_code if flow.response else "?"
    body = ""
    try:
        body = flow.response.get_text() or ""
    except Exception:
        try:
            body = flow.response.content.decode("utf-8", "replace")
        except Exception:
            body = ""
    _log(f"      <<< {status}  " + _fmt_body(body)[:1500])

    # 自动更新 config.yaml 里的 authCode + token
    url = flow.request.pretty_url
    if "authserver/wx/login" in url and flow.response and status == 200:
        try:
            req_body = flow.request.get_text() or ""
            m = re.search(r"authCode=([a-zA-Z0-9_-]+)", req_body)
            resp_data = flow.response.json()
            token_info = resp_data.get("data", {})
            access_token = token_info.get("accessToken", "")
            refresh_token = token_info.get("refreshToken", "")
            expiration = token_info.get("expiration", "")
            if m and access_token:
                _update_config(m.group(1), access_token, refresh_token, expiration)
                print(f"\n[OK] 抓到新 token，已写入 config.yaml (authCode={m.group(1)})")
        except Exception as e:
            _log(f"  [warn] 更新 config 失败: {e}")


def _update_config(auth_code, access_token, refresh_token, expiration):
    if not CONFIG_PATH.exists():
        return
    content = CONFIG_PATH.read_text(encoding="utf-8")
    for old_val, new_val in [
        (r'\bwechat_code:\s*"[^"]*"', f'wechat_code: "{auth_code}"'),
        (r'\btoken:\s*"[^"]*"', f'token: "{access_token}"'),
        (r'\brefresh_token:\s*"[^"]*"', f'refresh_token: "{refresh_token}"'),
        (r'\btoken_expiration:\s*"[^"]*"', f'token_expiration: "{expiration}"'),
    ]:
        content = re.sub(old_val, new_val, content)
    CONFIG_PATH.write_text(content, encoding="utf-8")
