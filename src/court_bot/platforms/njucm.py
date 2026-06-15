"""
南京中医药大学 (NJUCM) — 体育馆场地预约平台适配器

API 接口来自 mitmproxy 抓包分析 (2026-06-15)
系统由诺彩智慧场馆提供 (nuocaimespublic.oss-cn-beijing.aliyuncs.com)

关键 ID:
  - 小程序 AppID:  wx69041881ef731d55
  - 体育馆 ID:     1881595713595396097
  - 羽毛球场地 ID:  1881595935872536578
  - 乒乓球场地 ID:  1881596027069288449
"""

from __future__ import annotations

import logging
import time
from base64 import b64encode
from typing import Any

from court_bot.core.config import AppConfig
from court_bot.platforms.base import (
    BasePlatform, CourtInfo, SlotInfo, Candidate, BookingResult,
)
from court_bot.utils.http import SessionManager

logger = logging.getLogger(__name__)


class NJUCMPlatform(BasePlatform):
    """南京中医药大学体育馆预约平台适配器"""

    # ── 固定配置 ─────────────────────────────────────────
    BASE_URL = "https://gym.njucm.edu.cn/gym-api"
    APP_ID = "wx69041881ef731d55"
    STADIUM_ID = "1881595713595396097"

    # 场地类型 → placeId 映射
    PLACE_MAP: dict[str, str] = {
        "羽毛球": "1881595935872536578",
        "badminton": "1881595935872536578",
        "乒乓球": "1881596027069288449",
        "tabletennis": "1881596027069288449",
    }

    # ─────────────────────────────────────────────────────

    def __init__(self, config: AppConfig):
        super().__init__(config)
        self.session = SessionManager(
            base_url=self.BASE_URL,
            timeout=config.advanced.request_timeout,
            max_retries=config.advanced.retry_count,
            rate_limit=config.advanced.rate_limit,
        )
        # 设置微信小程序必要的 Header
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
        self._user_info: dict[str, Any] = {}
        self._place_id_cache: dict[str, str] = {}  # court_name → placeId

    # ── Authentication ───────────────────────────────────

    def authenticate(self) -> bool:
        """
        登录流程 (微信小程序):
        1. 使用 wx.login() 获取 authCode
        2. POST /authserver/wx/login 换取 accessToken

        注意: wx.login() 的 code 只有 5 分钟有效期，且只能使用一次。
        如果你有持久化的 token，可以提前在 config 中设置 auth.token。
        """
        auth_cfg = self.config.auth

        # Strategy 1: 预置 token (跳过登录)
        if auth_cfg.token:
            logger.info("使用预置 token")
            self._token = auth_cfg.token
            self._set_auth_header()
            self._authenticated = True
            return True

        # Strategy 2: 微信 code 换 token (标准流程)
        wx_code = auth_cfg.wechat_code
        if not wx_code:
            logger.error(
                "需要微信登录 code。请在 config.auth.wechat_code 中填入 "
                "wx.login() 返回的 code，或在手机微信中抓包获取 code。\n"
                "替代方案: 在 config.auth.token 中直接填入已有的 accessToken。"
            )
            return False

        return self._login_with_code(wx_code)

    def _login_with_code(self, wx_code: str) -> bool:
        """用 wx.login() code 换取 access token"""
        logger.info("微信 code 登录中...")

        # Basic auth: base64(appId)
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
        logger.debug("Login response: %s", data)

        if not data.get("success"):
            logger.error("登录失败: %s", data.get("errMessage", "未知错误"))
            return False

        token_data = data.get("data", {})
        self._token = token_data.get("accessToken", "")
        if not self._token:
            logger.error("未获取到 accessToken")
            return False

        logger.info(
            "登录成功, token 有效期至 %s",
            token_data.get("expiration", "未知"),
        )

        self._set_auth_header()
        self._authenticated = True
        return True

    def _set_auth_header(self) -> None:
        self.session.headers["Authorization"] = f"Bearer {self._token}"

    # ── Court / Slot Fetching ────────────────────────────

    def fetch_courts(self, court_type: str = "") -> list[CourtInfo]:
        """
        获取场馆下的场地列表。

        实际 API: POST /basic/api/stadium/miniGetPlaceList
        """
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
            place_name = p.get("placeName", "未知")
            place_id = p.get("placeId", "")

            # 缓存 placeId
            self._place_id_cache[place_name] = place_id

            # 过滤场地类型 (如果指定)
            if court_type and court_type not in place_name:
                continue

            courts.append(CourtInfo(
                court_id=place_id,
                court_name=place_name,
                court_number=0,  # 场地编号在子场地中
                location=p.get("placeAddress", ""),
                extra=p,
            ))

        logger.info("获取到 %d 个场地类型", len(courts))
        return courts

    def fetch_slots(self, date: str, court_id: str = "") -> list[SlotInfo]:
        """
        获取某日某场地的已预约时段，然后推断可用时段。

        实际 API: POST /order/place/ticket/getOrdersByDateAndPlaceId

        注意：这个接口返回的是已预约的时段。
        可用时段 = 全天可选时段 - 已预约时段
        """
        if not court_id:
            logger.warning("未指定 court_id，无法查询时段")
            return []

        # 1. 获取已预约时段
        resp = self.session.post(
            "/order/place/ticket/getOrdersByDateAndPlaceId",
            json={"date": date, "placeId": court_id},
        )
        if not resp:
            return []

        data = resp.json()
        if not data.get("success"):
            return []

        booked_set: set[str] = set()
        order_data = data.get("data", {})

        # allPlace: 整场预约
        for area in order_data.get("allPlace", []):
            for order in area.get("orders", []):
                key = f"{order['startTime']}-{order['endTime']}"
                booked_set.add(key)

        # halfPlace: 半场预约
        for area in order_data.get("halfPlace", []):
            for order in area.get("orders", []):
                key = f"{order['startTime']}-{order['endTime']}"
                booked_set.add(key)

        # 2. 获取全天可选时段范围 (从 buy-rule 推断)
        all_slots = self._get_all_possible_slots(date, court_id)
        if not all_slots:
            logger.warning("无法获取可选时段列表，可能该日期未开放")
            return []

        # 3. 计算可用时段
        slots = []
        for start, end in all_slots:
            key = f"{start}-{end}"
            available = key not in booked_set
            slots.append(SlotInfo(
                slot_id=f"{court_id}_{start}_{end}",
                start_time=start,
                end_time=end,
                available=available,
            ))

        available_count = sum(1 for s in slots if s.available)
        logger.info(
            "%s: %d/%d 时段可用", date, available_count, len(slots),
        )
        return slots

    def _get_all_possible_slots(
        self, date: str, place_id: str,
    ) -> list[tuple[str, str]]:
        """
        获取某日某场地的所有可选时段。

        方案: 通过 sport-plan/home 接口获取场地配置，
        或通过 getAreaPriceByPlaceIdAndWeek 获取价格表来推断时段。
        """
        # 尝试从已预约数据获取场地区域列表
        resp = self.session.post(
            "/order/place/ticket/getOrdersByDateAndPlaceId",
            json={"date": date, "placeId": place_id},
        )
        if not resp:
            return []

        data = resp.json()
        if not data.get("success"):
            return []

        # 从返回的场地列表推断时段
        # 场馆通常在特定时段开放 (如 9:00-21:00，每小时一段)
        # 具体时段从已有订单中推断
        all_slots: list[tuple[str, str]] = []
        seen: set[str] = set()

        order_data = data.get("data", {})

        # 包含所有场地区域 (即使是已预约的也用于获取时段模板)
        for area in order_data.get("allPlace", []):
            for order in area.get("orders", []):
                slot_key = f"{order['startTime']}-{order['endTime']}"
                if slot_key not in seen:
                    seen.add(slot_key)
                    all_slots.append((order["startTime"], order["endTime"]))

        for area in order_data.get("halfPlace", []):
            for order in area.get("orders", []):
                slot_key = f"{order['startTime']}-{order['endTime']}"
                if slot_key not in seen:
                    seen.add(slot_key)
                    all_slots.append((order["startTime"], order["endTime"]))

        # 如果当天没有已预约时段 (全是空的), 尝试从运动计划获取
        if not all_slots:
            all_slots = self._get_slots_from_sport_plan(date, place_id)

        # 按时间排序
        all_slots.sort(key=lambda x: x[0])
        return all_slots

    def _get_slots_from_sport_plan(
        self, date: str, place_id: str,
    ) -> list[tuple[str, str]]:
        """从运动计划接口获取可选时段"""
        resp = self.session.get(
            "/order/sport-plan/home",
            params={"stadiumId": self.STADIUM_ID},
        )
        if not resp:
            return []

        data = resp.json()
        if not data.get("success"):
            return []

        # sport-plan/home 返回各场地的时间计划
        # 具体解析逻辑视实际返回结构调整
        slots: list[tuple[str, str]] = []
        # TODO: 根据实际返回结构解析时段
        return slots

    # ── Booking ──────────────────────────────────────────

    def submit_booking(self, candidate: Candidate, date: str) -> BookingResult:
        """
        提交预约。

        ⚠️ 预约接口未在抓包中捕获 (当时场地全满)。
        根据系统通用模式，推测接口为:
          POST /order/place/ticket/create

        如果实际接口不同，请根据一次成功的预约抓包结果调整。
        """
        start = time.monotonic()

        # ── 推测的预约请求体 ─────────────────────────────
        payload = {
            "placeId": candidate.court_id,
            "date": date,
            "startTime": candidate.start_time,
            "endTime": candidate.end_time,
            "saleChannel": self.APP_ID,
            # 可能还需要:
            # "placeAreaId": "...",
            # "stadiumId": self.STADIUM_ID,
        }

        resp = self.session.post(
            "/order/place/ticket/create",    # ← 推测的接口，需验证
            json=payload,
        )
        elapsed = time.monotonic() - start

        if not resp:
            return BookingResult(
                success=False, message="网络请求失败",
                court_name=candidate.court_name,
                slot_label=candidate.slot_label,
            )

        data = resp.json()
        logger.debug("预约响应 (%.2fs): %s", elapsed, data)

        success = data.get("success", False)
        msg = data.get("errMessage", "") or ""

        booking_id = ""
        if success:
            booking_id = data.get("data", {}).get("businessOrderNo", "")
            if not booking_id:
                booking_id = data.get("data", {}).get("orderNo", "")

        if not success and not msg:
            msg = "预约失败 (可能是系统繁忙或已约满)"

        return BookingResult(
            success=success,
            booking_id=str(booking_id),
            message=str(msg),
            court_name=candidate.court_name,
            slot_label=candidate.slot_label,
            raw_response=data,
        )

    # ── Utilities ────────────────────────────────────────

    def get_my_bookings(self) -> list[dict]:
        """查询已有预约"""
        # 从 user-info/detail 可能包含预约历史
        resp = self.session.get("/order/user-info/detail")
        if resp:
            data = resp.json()
            logger.debug("User info: %s", data)
        return []

    def get_place_id(self, court_type: str) -> str:
        """根据场地类型名获取 placeId"""
        # 先查缓存
        for name, pid in self.PLACE_MAP.items():
            if court_type in name or name in court_type:
                return pid
        # 从 API 获取
        courts = self.fetch_courts(court_type)
        if courts:
            return courts[0].court_id
        return ""

    def close(self) -> None:
        self.session.close()
