"""
南京中医药大学 (NJUCM) — 体育馆场地预约平台适配器

API 接口来自 mitmproxy 抓包分析 (2026-06-15)
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
        if auth_cfg.token:
            self._token = auth_cfg.token
            self._set_auth_header()
            self._authenticated = True
            return True

        wx_code = auth_cfg.wechat_code
        if not wx_code:
            logger.error("需要 token 或 wechat_code。在 config.auth 中配置。")
            return False
        return self._login_with_code(wx_code)

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
        self._set_auth_header()
        self._authenticated = True
        logger.info("登录成功, 有效期至 %s", data["data"].get("expiration"))
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

                # 从 rules 获取该场地的营业规则
                rules = area.get("rules", [])
                if not rules:
                    continue

                rule = rules[0]  # 取第一条规则
                open_start = rule.get("startTime", self.OPEN_START)
                open_end = rule.get("endTime", self.OPEN_END)
                unit_minutes = rule.get("unit", self.SLOT_UNIT)

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
        提交预约。

        ⚠️ 接口未在抓包中验证 (当时全满)。
        根据同类系统推测为: POST /order/place/ticket/create
        """
        start = time.monotonic()

        # 从 candidate 获取场地 area 信息
        area_id = (
            candidate.raw_slot.get("area_id", "")
            or candidate.raw_court.get("area_id", "")
        )
        place_id = candidate.court_id

        payload: dict[str, Any] = {
            "placeId": place_id,
            "placeAreaId": area_id,
            "date": date,
            "startTime": candidate.start_time,
            "endTime": candidate.end_time,
            "saleChannel": self.APP_ID,
        }

        resp = self.session.post(
            "/order/place/ticket/create",  # ← 推测接口，需验证
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
        msg = data.get("errMessage", "") or ("预约成功" if success else "预约失败")

        booking_id = ""
        if success:
            b_data = data.get("data", {})
            booking_id = b_data.get("businessOrderNo", b_data.get("orderNo", ""))

        return BookingResult(
            success=success,
            booking_id=str(booking_id),
            message=str(msg),
            court_name=candidate.court_name,
            slot_label=candidate.slot_label,
            raw_response=data,
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
