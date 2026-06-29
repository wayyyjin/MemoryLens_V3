from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from photo_utils import PhotoItem, format_korean_time


@dataclass
class EventItem:
    photos: list[PhotoItem]
    note: str = ""
    ai_title: str = ""
    ai_record: str = ""
    ai_location: str = ""
    ai_activity: str = ""

    @property
    def start_time(self) -> Optional[datetime]:
        return self.photos[0].time if self.photos else None

    @property
    def end_time(self) -> Optional[datetime]:
        return self.photos[-1].time if self.photos else None

    @property
    def address(self) -> str:
        for p in self.photos:
            if p.address != "위치 정보 없음":
                return p.address
        return "위치 정보 없음"


def haversine_meters(gps1: Optional[dict], gps2: Optional[dict]) -> Optional[float]:
    if not gps1 or not gps2:
        return None
    r = 6371000
    lat1 = math.radians(gps1["lat"])
    lat2 = math.radians(gps2["lat"])
    dlat = math.radians(gps2["lat"] - gps1["lat"])
    dlon = math.radians(gps2["lon"] - gps1["lon"])
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c


def event_time_text(event: EventItem) -> str:
    start = event.start_time
    end = event.end_time
    if not start:
        return "촬영 시간 없음"
    if not end or start == end:
        return format_korean_time(start)
    return f"{format_korean_time(start)} ~ {format_korean_time(end)}"


def group_photos(
    photos: list[PhotoItem],
    short_gap_minutes: int = 8,
    long_activity_gap_minutes: int = 180,
    short_distance_meters: int = 180,
    long_distance_meters: int = 600,
) -> list[EventItem]:
    events: list[EventItem] = []
    for photo in photos:
        if not events:
            events.append(EventItem([photo]))
            continue

        last_event = events[-1]
        last_photo = last_event.photos[-1]

        if not photo.time or not last_photo.time:
            events.append(EventItem([photo]))
            continue

        gap = abs((photo.time - last_photo.time).total_seconds()) / 60
        distance = haversine_meters(photo.gps, last_photo.gps)

        same_place_short = True if distance is None else distance <= short_distance_meters
        same_place_long = True if distance is None else distance <= long_distance_meters
        same_addr = photo.address != "위치 정보 없음" and photo.address == last_photo.address

        # 짧은 시간 연속 촬영은 같은 이벤트
        if gap <= short_gap_minutes and same_place_short:
            last_event.photos.append(photo)
            continue

        # 같은 장소에서 긴 활동이 이어진 것으로 볼 수 있으면 같은 이벤트
        if gap <= long_activity_gap_minutes and (same_place_long or same_addr):
            last_event.photos.append(photo)
            continue

        events.append(EventItem([photo]))
    return events
