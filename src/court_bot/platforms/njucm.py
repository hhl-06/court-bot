"""
南京中医药大学 (NJUCM) — 体育馆场地预约平台适配器

API 接口来自 mitmproxy 抓包分析 (2026-06-21)
真实 API 流程: create → orderDetail → prePay → tapPay
系统由诺彩智慧场馆提供

关键 ID:
  - 小程序 AppID:  wx69041881ef731d55
  - 体育馆 ID:     1881595713595396097
  - 羽毛球场地 ID:  1881595935872536578
  - 乒乓球场地 ID:  1881596027069288449
  - 场地号:         1号(1881606335821271041) ~ 8号(1881606600058228738)
  - 营业时间:       08:30-21:30, 每60分钟一段
"""

from __future__ import annotations

import logging
import time
import secrets
import uuid
from base64 import b64encode
from datetime import datetime
from typing import Any

from court_bot.core.config import AppConfig
from court_bot.platforms.base import (
    BasePlatform, CourtInfo, SlotInfo, Candidate, BookingResult,
)
from court_bot.utils.http import SessionManager

logger = logging.getLogger(__name__)


class NJUCMPlatform(BasePlatform):
    """南京中医药大学体育馆预约平台适配器"""

    BASE_URL = "https://gym.njucm.edu.cn/gym-api"
    APP_ID = "wx69041881ef731d55"
    STADIUM_ID = "1881595713595396097"

    # 场地类型 → placeId
    PLACE_MAP: dict[str, str] = {
        "羽毛球": "1881595935872536578",
        "badminton": "1881595935872536578",
        "乒乓球": "1881596027069288449",
        "tabletennis": "1881596027069288449",
    }

    # 场地号 → placeAreaId
    AREA_NAME_MAP: dict[int, str] = {
        1: "1881606335821271041",
        2: "1881606382399016961",
        3: "1881606414166675458",
        4: "1881606462027878401",
        5: "1881606492205895681",
        6: "1881606534392205313",
        7: "1881606572421959681",
        8: "1881606600058228738",
        9: "1881606634262777857",
        10: "1881606673185918977",
        11: "1881606702785122306",
        12: "1881606738377986049",
        13: "1881606770770595842",
        14: "1881606797656084481",
        15: "1881606822591221762",
    }

    # 营业规则 (从 API rules 中获取: startTime=08:30, endTime=21:30, unit=60)
    OPEN_START = "08:30"
    OPEN_END = "21:30"
    SLOT_UNIT = 60  # 分钟

    def __init__(self, config: AppConfig):
        super().__init__(config)
        self.session = SessionManager(
            base_url=self.BASE_URL,
            timeout=config.advanced.request_timeout,
            max_retries=config.advanced.retry_count,
            rate_limit=config.advanced.rate_limit,
        )
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/132.0.0.0 Safari/537.36 "
                "MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI "
                "MiniProgramEnv/Windows WindowsWechat/WMPF "
                "WindowsWechat(0x63090a13) UnifiedPCWindowsWechat(0xf2541a1b) XWEB/19921"
            ),
            "xweb_xhr": "1",
            "Referer": f"https://servicewechat.com/{self.APP_ID}/23/page-frame.html",
        })
        self._token: str = ""
        self._area_cache: dict[str, dict] = {}  # area_id → {name, rules}

    # ── Authentication ───────────────────────────────────

    def authenticate(self) -> bool:
        auth_cfg = self.config.auth

        # 1. Pre-obtained token (fastest path)
        if auth_cfg.token:
            self._token = auth_cfg.token
            self._refresh_token = auth_cfg.refresh_token
            self._token_expiration = auth_cfg.token_expiration
            self._set_auth_header()
            self._authenticated = True
            self._check_token_expiry()
            return True

        # 2. Try refresh token (avoids re-login)
        if auth_cfg.refresh_token:
            if self._try_refresh_token(auth_cfg.refresh_token):
                return True
            logger.info("refresh token 失败，尝试 wechat_code 登录...")

        # 3. WeChat code login
        wx_code = auth_cfg.wechat_code
        if not wx_code:
            logger.error("需要 token、refresh_token 或 wechat_code。在 config.auth 中配置。")
            return False
        return self._login_with_code(wx_code)

    def _try_refresh_token(self, refresh_token: str) -> bool:
        """
        尝试用 refresh_token 刷新 access_token。

        支持两种端点 (自动尝试):
          1. /authserver/token/refresh  (OAuth2 标准)
          2. /authserver/wx/refresh     (微信常见)
        """
        endpoints = [
            "/authserver/token/refresh",
            "/authserver/wx/refresh",
        ]
        # 如果有自定义 refresh_url，优先使用
        if self.config.auth.refresh_url:
            endpoints.insert(0, self.config.auth.refresh_url)

        for ep in endpoints:
            try:
                resp = self.session.post(
                    ep,
                    json={"refreshToken": refresh_token},
                )
                if not resp:
                    continue
                data = resp.json()
                if data.get("success"):
                    token_data = data.get("data", data)
                    self._token = token_data.get("accessToken", "")
                    new_refresh = token_data.get("refreshToken", refresh_token)
                    self._token_expiration = token_data.get("expiration", "")
                    self._set_auth_header()
                    self._authenticated = True
                    # 更新 config 中的值，便于下次启动使用
                    self.config.auth.token = self._token
                    self.config.auth.refresh_token = new_refresh
                    self.config.auth.token_expiration = self._token_expiration
                    logger.info("Token 刷新成功 (via %s), 有效期至 %s", ep, self._token_expiration)
                    return True
            except Exception as e:
                logger.debug("刷新端点 %s 失败: %s", ep, e)

        return False

    def _check_token_expiry(self) -> None:
        """检测 token 是否即将过期 (< 6h)，通过通知提醒。"""
        if not hasattr(self, '_token_expiration') or not self._token_expiration:
            # 预配 token 没有 expiration 信息，静默跳过
            return
        try:
            from datetime import datetime as dt
            expiry = dt.strptime(self._token_expiration, "%Y-%m-%d %H:%M:%S")
            remaining = expiry - dt.now()
            hours = remaining.total_seconds() / 3600
            if hours < 6:
                from court_bot.notify.channels import Notifier
                notifier = Notifier(self.config.notify)
                notifier.send(
                    "⚠️ Court Bot Token 即将过期",
                    f"Token 将于 {self._token_expiration} 过期\n剩余 {hours:.1f} 小时\n请重新获取 wechat_code 更新 token",
                )
                logger.warning("Token 将在 %.1f 小时后过期，已发送通知", hours)
        except Exception as e:
            logger.debug("Token 过期检测异常: %s", e)

    def _login_with_code(self, wx_code: str) -> bool:
        basic = b64encode(self.APP_ID.encode()).decode()
        resp = self.session.post(
            "/authserver/wx/login",
            data={"authCode": wx_code},
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        if not resp:
            return False
        data = resp.json()
        if not data.get("success"):
            logger.error("登录失败: %s", data.get("errMessage"))
            return False
        self._token = data["data"]["accessToken"]
        self._refresh_token = data["data"].get("refreshToken", "")
        self._token_expiration = data["data"].get("expiration", "")
        self._set_auth_header()
        self._authenticated = True
        # 存回 config，下次启动直接用 refresh_token 续期
        self.config.auth.token = self._token
        self.config.auth.refresh_token = self._refresh_token
        self.config.auth.token_expiration = self._token_expiration
        logger.info("登录成功, 有效期至 %s (refreshToken: %s...)",
                    self._token_expiration, self._refresh_token[:12] if self._refresh_token else "无")
        return True

    def _set_auth_header(self) -> None:
        self.session.headers["Authorization"] = f"Bearer {self._token}"

    # ── Court / Slot Fetching ────────────────────────────

    def fetch_courts(self, court_type: str = "") -> list[CourtInfo]:
        resp = self.session.post(
            "/basic/api/stadium/miniGetPlaceList",
            json={"stadiumId": self.STADIUM_ID},
        )
        if not resp:
            return []
        data = resp.json()
        places = data.get("data", [])
        courts = []
        for p in places:
            name = p.get("placeName", "未知")
            if court_type and court_type not in name:
                continue
            courts.append(CourtInfo(
                court_id=p.get("placeId", ""),
                court_name=name,
                court_number=0,
                extra=p,
            ))
        logger.info("获取到 %d 个场地类型", len(courts))
        return courts

    def fetch_slots(self, date: str, court_id: str = "") -> list[SlotInfo]:
        """
        获取某日某场地类型下所有场地的可用时段。

        流程:
        1. 调 getOrdersByDateAndPlaceId → 拿到 1-8号场地 + 每个场地的 rules
        2. 从 rules 生成全天所有可能时段 (08:30-21:30, 每60分钟)
        3. 已预约的标记为 unavailable
        4. 返回按场地号+时间排序的结果
        """
        if not court_id:
            return []

        resp = self.session.post(
            "/order/place/ticket/getOrdersByDateAndPlaceId",
            json={"date": date, "placeId": court_id},
        )
        if not resp:
            return []

        data = resp.json()
        if not data.get("success"):
            logger.warning("获取时段失败: %s", data.get("errMessage"))
            return []

        order_data = data.get("data", {})
        slots: list[SlotInfo] = []

        # 遍历所有场地 (allPlace) 和半场 (halfPlace)
        for area_type_key in ("allPlace", "halfPlace"):
            for area in order_data.get(area_type_key, []):
                area_id = area.get("placeAreaId", "")
                area_name = area.get("placeAreaName", "未知")

                # 缓存场地信息
                self._area_cache[area_id] = area

                # 从 rules 获取该场地的营业规则 (可能为 null)
                rules = area.get("rules") or []
                if rules:
                    rule = rules[0]
                    open_start = rule.get("startTime", self.OPEN_START)
                    open_end = rule.get("endTime", self.OPEN_END)
                    unit_minutes = rule.get("unit", self.SLOT_UNIT)
                else:
                    # 回退到默认值 (08:30-21:30, 每60分钟)
                    open_start = self.OPEN_START
                    open_end = self.OPEN_END
                    unit_minutes = self.SLOT_UNIT

                # 生成该场地所有可能的时段
                all_possible = self._generate_time_slots(open_start, open_end, unit_minutes)

                # 收集已预约时段
                booked_set: set[str] = set()
                for order in area.get("orders") or []:
                    booked_set.add(f"{order['startTime']}-{order['endTime']}")

                # 标记可用/已约
                for start_t, end_t in all_possible:
                    key = f"{start_t}-{end_t}"
                    slots.append(SlotInfo(
                        slot_id=f"{area_id}_{start_t}_{end_t}",
                        start_time=start_t,
                        end_time=end_t,
                        available=key not in booked_set,
                        extra={
                            "area_id": area_id,
                            "area_name": area_name,
                            "place_id": court_id,
                        },
                    ))

        available_count = sum(1 for s in slots if s.available)
        logger.info("%s: %d/%d 时段可用", date, available_count, len(slots))
        return slots

    @staticmethod
    def _generate_time_slots(start: str, end: str, unit_min: int) -> list[tuple[str, str]]:
        """根据起止时间和单位生成所有时段，如 08:30, 09:30, 10:30..."""
        def _to_min(t: str) -> int:
            h, m = t.split(":")
            return int(h) * 60 + int(m)

        def _to_str(m: int) -> str:
            return f"{m // 60:02d}:{m % 60:02d}"

        start_min = _to_min(start)
        end_min = _to_min(end)
        slots = []
        cur = start_min
        while cur + unit_min <= end_min:
            slots.append((_to_str(cur), _to_str(cur + unit_min)))
            cur += unit_min
        return slots

    # ── Booking ──────────────────────────────────────────

    def submit_booking(self, candidate: Candidate, date: str) -> BookingResult:
        """
        提交预约 — 真实四段式流程:

        ① POST /order/v1/api/order/create     → businessOrderNo
        ② POST /order/v1/api/order/orderDetail → businessSubOrderNo + goodsId
        ③ POST /order/v1/api/order/prePay      → transNo
        ④ POST /order/v1/api/order/tapPay      → 完成支付
        """
        start = time.monotonic()

        area_id = (
            candidate.raw_slot.get("area_id", "")
            or candidate.raw_court.get("area_id", "")
        )
        place_id = candidate.court_id

        # ── 获取用户信息 ──────────────────────────────
        user_info = self._get_user_info()
        if not user_info:
            return BookingResult(
                success=False, message="无法获取用户信息",
                court_name=candidate.court_name,
                slot_label=candidate.slot_label,
            )
        user_id = user_info.get("userId", "")
        customer_name = user_info.get("name", "")

        # ── 获取 goodsId (从 getAreaPriceByPlaceIdAndWeek) ──
        goods_id = self._get_goods_id(place_id, area_id, candidate.start_time, candidate.end_time, date)
        if not goods_id:
            logger.warning("未找到 goodsId，下单可能失败")

        # ── ① Create ─────────────────────────────────
        serial_num = self._generate_serial_num()
        create_payload: dict[str, Any] = {
            "userId": user_id,
            "customerName": customer_name,
            "userMobile": None,
            "totalAmount": 0,
            "pressure": True,
            "businessType": "02",
            "orderSource": self.APP_ID,
            "serialNum": serial_num,
            "stadiumId": self.STADIUM_ID,
            "endDate": date,
            "startDate": date,
            "placeAreaList": [{
                "startTime": candidate.start_time,
                "endTime": candidate.end_time,
                "placeAreaId": area_id,
                "placeId": place_id,
                "stadiumId": self.STADIUM_ID,
            }],
        }

        resp = self.session.post("/order/v1/api/order/create", json=create_payload)
        if not resp:
            return BookingResult(
                success=False, message="① create 网络请求失败",
                court_name=candidate.court_name,
                slot_label=candidate.slot_label,
            )
        data = resp.json()
        if not data.get("success"):
            msg = data.get("errMessage", "create 失败")
            logger.error("① create 失败: %s", msg)
            return BookingResult(success=False, message=str(msg),
                                 court_name=candidate.court_name,
                                 slot_label=candidate.slot_label,
                                 raw_response=data)
        business_order_no = data["data"]["businessOrderNo"]
        logger.info("① create ✓ %s", business_order_no)

        # ── ② OrderDetail ────────────────────────────
        detail_resp = self.session.post("/order/v1/api/order/orderDetail", json={
            "businessOrderNo": business_order_no,
            "businessType": "02",
        })
        if not detail_resp:
            return BookingResult(
                success=False, message="② orderDetail 网络请求失败",
                court_name=candidate.court_name,
                slot_label=candidate.slot_label,
            )
        detail_data = detail_resp.json()
        if not detail_data.get("success"):
            msg = detail_data.get("errMessage", "orderDetail 失败")
            logger.error("② orderDetail 失败: %s", msg)
            return BookingResult(success=False, message=str(msg),
                                 court_name=candidate.court_name,
                                 slot_label=candidate.slot_label,
                                 raw_response=detail_data)

        # 提取 subOrderNo 和 goodsId
        sub_orders = detail_data.get("data", {}).get("businessSubOrderList", [])
        sub_order_no = sub_orders[0]["businessSubOrderNo"] if sub_orders else ""
        actual_goods_id = sub_orders[0].get("goodsId", goods_id) if sub_orders else goods_id
        goods_name = sub_orders[0].get("goodsName", "") if sub_orders else ""
        if not actual_goods_id:
            logger.error("② orderDetail 未返回 goodsId")
            return BookingResult(success=False, message="② 未获取到 goodsId",
                                 court_name=candidate.court_name,
                                 slot_label=candidate.slot_label,
                                 raw_response=detail_data)
        logger.info("② orderDetail ✓ goodsId=%s subOrder=%s", actual_goods_id, sub_order_no)

        # ── ③ PrePay ─────────────────────────────────
        client_id = self._get_or_create_client_id()
        pre_pay_payload: dict[str, Any] = {
            "businessOrderNo": business_order_no,
            "clientId": client_id,
            "remark": None,
            "user": user_info,
            "orderGoods": [{
                "actAmount": 0,
                "amount": 0,
                "businessSubOrderNo": sub_order_no,
                "freeAmount": 0,
                "goodsId": actual_goods_id,
                "goodsName": goods_name,
                "goodsNum": 1,
                "goodsType": "02",
                "agreeAmount": 0,
            }],
            "preferentialGoods": {},
            "smsNotice": False,
        }

        prepay_resp = self.session.post("/order/v1/api/order/prePay", json=pre_pay_payload)
        if not prepay_resp:
            return BookingResult(
                success=False, message="③ prePay 网络请求失败",
                court_name=candidate.court_name,
                slot_label=candidate.slot_label,
            )
        prepay_data = prepay_resp.json()
        if not prepay_data.get("success"):
            msg = prepay_data.get("errMessage", "prePay 失败")
            logger.error("③ prePay 失败: %s", msg)
            return BookingResult(success=False, message=str(msg),
                                 court_name=candidate.court_name,
                                 slot_label=candidate.slot_label,
                                 raw_response=prepay_data)
        trans_no = prepay_data["data"]["transNo"]
        amount = prepay_data["data"].get("amount", 0)
        logger.info("③ prePay ✓ transNo=%s amount=%s", trans_no, amount)

        # ── ④ TapPay (确认支付) ──────────────────────
        tap_pay_payload: dict[str, Any] = {
            "businessNo": business_order_no,
            "clientId": client_id,
            "memberCardId": "",
            "openId": None,
            "orderGoods": [{
                "actAmount": 0,
                "amount": 0,
                "businessSubOrderNo": sub_order_no,
                "freeAmount": 0,
                "goodsId": actual_goods_id,
                "goodsName": goods_name,
                "goodsNum": 1,
                "goodsType": "02",
                "agreeAmount": 0,
            }],
            "orderSource": "GYM",
            "payScene": "03,01",
            "payChannel": "03",
            "payWayCode": "ironman_student_card",
            "payWayName": "学生卡",
            "tansNo": trans_no,
            "tenantCode": "1021",
        }

        tap_resp = self.session.post("/order/v1/api/order/tapPay", json=tap_pay_payload)
        elapsed = time.monotonic() - start

        if not tap_resp:
            return BookingResult(
                success=False, message="④ tapPay 网络请求失败",
                court_name=candidate.court_name,
                slot_label=candidate.slot_label,
            )
        tap_data = tap_resp.json()
        logger.debug("预约完成 (%.2fs): %s", elapsed, tap_data)

        success = tap_data.get("success", False)
        if success:
            tap_result = tap_data.get("data", {}).get("result", False)
            if tap_result:
                logger.info("预约成功! %s | %s", candidate.court_name, candidate.slot_label)
                return BookingResult(
                    success=True,
                    booking_id=business_order_no,
                    message="预约成功",
                    court_name=candidate.court_name,
                    slot_label=candidate.slot_label,
                    raw_response=tap_data,
                )
            else:
                msg = tap_data.get("data", {}).get("errorMsg", "支付结果返回失败")
                logger.error("④ tapPay result=false: %s", msg)
                return BookingResult(success=False, message=str(msg),
                                     court_name=candidate.court_name,
                                     slot_label=candidate.slot_label,
                                     raw_response=tap_data)

        msg = tap_data.get("errMessage", "tapPay 失败")
        logger.error("④ tapPay 失败: %s", msg)
        return BookingResult(
            success=False,
            message=str(msg),
            court_name=candidate.court_name,
            slot_label=candidate.slot_label,
            raw_response=tap_data,
        )

    # ── Override: find_candidates with area support ──────

    def find_candidates(
        self,
        date: str,
        court_type: str = "",
        preferred_courts: list[int] | None = None,
        preferred_times: list[str] | None = None,
        fallback_to_any: bool = True,
        max_candidates: int = 20,
    ) -> list[Candidate]:
        """
        构建候选列表，支持场地号偏好。

        preferred_courts 在这里是场地号 (1-8)，不是场地类型。
        """
        preferred_courts = preferred_courts or []
        preferred_times = preferred_times or []

        # 确定 placeId
        place_id = ""
        for name, pid in self.PLACE_MAP.items():
            if court_type and (court_type in name or name in court_type):
                place_id = pid
                break
        if not place_id:
            courts = self.fetch_courts(court_type)
            if courts:
                place_id = courts[0].court_id
        if not place_id:
            return []

        # 获取所有时段
        slots = self.fetch_slots(date, place_id)
        available = [s for s in slots if s.available]
        if not available:
            logger.warning("没有可用时段")
            return []

        # 构建候选并排序
        scored: list[tuple[int, int, Candidate]] = []
        for slot in available:
            area_id = slot.extra.get("area_id", "")
            area_name = slot.extra.get("area_name", "")

            # 从场地名提取编号 (如 "1号场地" → 1)
            area_num = 0
            for i in range(1, 16):
                if f"{i}号" in area_name:
                    area_num = i
                    break

            # 计算偏好排名
            court_rank = preferred_courts.index(area_num) if area_num in preferred_courts else len(preferred_courts)
            time_rank = self._match_time_preference(slot.label, preferred_times)

            c = Candidate(
                court_id=place_id,
                court_name=f"羽毛球 {area_name}",
                court_number=area_num,
                slot_id=slot.slot_id,
                slot_label=slot.label,
                start_time=slot.start_time,
                end_time=slot.end_time,
                raw_court={"place_id": place_id, "area_id": area_id, "area_name": area_name},
                raw_slot={"area_id": area_id, **slot.extra},
            )
            scored.append((court_rank, time_rank, c))

        scored.sort(key=lambda x: (x[0], x[1]))

        if not fallback_to_any:
            scored = [(cr, tr, c) for cr, tr, c in scored
                      if cr < len(preferred_courts) and tr < len(preferred_times)]

        candidates = [c for _, _, c in scored[:max_candidates]]
        logger.info("找到 %d 个候选 (%s)", len(candidates), date)
        for i, c in enumerate(candidates[:8]):
            logger.info("  候选 %d: %s %s", i + 1, c.court_name, c.slot_label)

        return candidates

    @staticmethod
    def _match_time_preference(slot_label: str, preferred: list[str]) -> int:
        """
        匹配时段偏好排名。

        对每个偏好项，先精确匹配，再范围匹配。第一个命中的返回其排名。
          精确匹配: "18:30-19:30" in list → rank
          范围匹配: "18:30-20:30" 包含 "18:30-19:30" → rank of the range
        """
        def _to_min(t: str) -> int:
            h, m = t.split(":")
            return int(h) * 60 + int(m)

        slot_parts = slot_label.split("-")
        if len(slot_parts) != 2:
            return len(preferred)
        slot_start = _to_min(slot_parts[0])
        slot_end = _to_min(slot_parts[1])

        for idx, pref in enumerate(preferred):
            # 精确匹配
            if slot_label == pref:
                return idx
            # 范围匹配: slot 完全在偏好范围内
            pref_parts = pref.split("-")
            if len(pref_parts) == 2:
                pref_start = _to_min(pref_parts[0])
                pref_end = _to_min(pref_parts[1])
                if slot_start >= pref_start and slot_end <= pref_end:
                    return idx

        return len(preferred)

    # ── Utilities ────────────────────────────────────────

    def _get_user_info(self) -> dict[str, Any]:
        """获取当前登录用户信息 (缓存 30 分钟)。"""
        now = time.time()
        if hasattr(self, "_user_info_cache") and hasattr(self, "_user_info_ts"):
            if now - self._user_info_ts < 1800:
                return self._user_info_cache

        resp = self.session.get("/order/user-info/detail")
        if not resp or resp.status_code != 200:
            logger.error("获取用户信息失败")
            return {}
        data = resp.json()
        if data.get("success"):
            self._user_info_cache = data.get("data", {})
            self._user_info_ts = now
            logger.info("用户: %s (ID=%s)", self._user_info_cache.get("name"),
                        self._user_info_cache.get("userId"))
            return self._user_info_cache
        return {}

    def _get_goods_id(self, place_id: str, area_id: str,
                      start_time: str, end_time: str, date: str) -> str:
        """
        从 getAreaPriceByPlaceIdAndWeek 获取 goodsId。

        根据抓包分析，goodsId = placeAreaPriceId，通过 week 和时段匹配。
        """
        # 计算星期几 (01=周日, 02=周一, ..., 07=周六)
        # NJUCM 系统: 周日=01, ISO 周日=7
        dt = datetime.strptime(date, "%Y-%m-%d")
        week = f"{(dt.isoweekday() % 7) + 1:02d}"

        resp = self.session.get(
            "/order/place/ticket/getAreaPriceByPlaceIdAndWeek",
            params={
                "placeId": place_id,
                "week": week,
                "saleChannel": self.APP_ID,
            },
        )
        if not resp:
            return ""

        data = resp.json()
        if not data.get("success"):
            return ""

        areas_data = data.get("data", {})
        for area_type_key in ("allPlace", "halfPlace"):
            for area in areas_data.get(area_type_key, []):
                if area.get("placeAreaId") != area_id:
                    continue
                for t in area.get("times", []):
                    if t.get("startTime") == start_time and t.get("endTime") == end_time:
                        goods_id = t.get("placeAreaPriceId", "")
                        logger.info("找到 goodsId=%s (%s %s-%s week=%s)",
                                    goods_id, area.get("placeAreaName"),
                                    start_time, end_time, week)
                        return goods_id

        logger.warning("未找到匹配的 goodsId: area=%s %s-%s week=%s", area_id, start_time, end_time, week)
        return ""

    @staticmethod
    def _generate_serial_num() -> str:
        """
        生成序列号，格式: YYYYMMDDHHmmssSSS#<randomHex>

        示例: 20260621222734564#5a905c56
        """
        now = datetime.now()
        ts = now.strftime("%Y%m%d%H%M%S") + f"{now.microsecond // 1000:03d}"
        rand = secrets.token_hex(4)
        return f"{ts}#{rand}"

    def _get_or_create_client_id(self) -> str:
        """
        获取或生成 clientId。

        抓包中 clientId 为 Base64 编码的长整数 (如: NzM1MTMxOTc1OTI1MTc0Mjcy = 735131975925174272)。
        这里用 userId 的 Base64 编码作为替代，实际效果等价。
        """
        if hasattr(self, "_client_id"):
            return self._client_id

        user_info = self._get_user_info()
        user_id = user_info.get("userId", str(uuid.uuid4().int >> 96))
        # 用 userId 数值做 base64
        self._client_id = b64encode(user_id.encode()).decode()
        return self._client_id

    def get_place_id(self, court_type: str) -> str:
        for name, pid in self.PLACE_MAP.items():
            if court_type in name or name in court_type:
                return pid
        courts = self.fetch_courts(court_type)
        return courts[0].court_id if courts else ""

    def get_my_bookings(self) -> list[dict]:
        resp = self.session.get("/order/user-info/detail")
        return [resp.json()] if resp and resp.status_code == 200 else []

    def close(self) -> None:
        self.session.close()
