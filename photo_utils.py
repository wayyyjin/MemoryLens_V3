from __future__ import annotations

import io
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Any

from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
from geopy.geocoders import Nominatim


@dataclass
class PhotoItem:
    file_name: str
    image: Image.Image
    time: Optional[datetime]
    time_text: str
    gps: Optional[dict]
    address: str


def get_exif(image: Image.Image) -> dict:
    try:
        raw = image._getexif()
        if not raw:
            return {}
        return {TAGS.get(k, k): v for k, v in raw.items()}
    except Exception:
        return {}


def get_photo_time(exif: dict) -> Optional[datetime]:
    for key in ["DateTimeOriginal", "DateTimeDigitized", "DateTime"]:
        if key in exif:
            try:
                return datetime.strptime(str(exif[key]), "%Y:%m:%d %H:%M:%S")
            except Exception:
                pass
    return None


def _ratio_to_float(x: Any) -> float:
    try:
        return float(x)
    except Exception:
        return x.numerator / x.denominator


def convert_to_degrees(value) -> float:
    d, m, s = value
    return _ratio_to_float(d) + _ratio_to_float(m) / 60 + _ratio_to_float(s) / 3600


def get_gps_info(exif: dict) -> Optional[dict]:
    gps_data = exif.get("GPSInfo")
    if not gps_data:
        return None
    gps = {GPSTAGS.get(k, k): v for k, v in gps_data.items()}
    try:
        lat = convert_to_degrees(gps["GPSLatitude"])
        lon = convert_to_degrees(gps["GPSLongitude"])
        if gps.get("GPSLatitudeRef") != "N":
            lat = -lat
        if gps.get("GPSLongitudeRef") != "E":
            lon = -lon
        return {"lat": lat, "lon": lon}
    except Exception:
        return None


def format_korean_time(dt: Optional[datetime]) -> str:
    if not dt:
        return "촬영 시간 없음"
    ampm = "오전" if dt.hour < 12 else "오후"
    hour = dt.hour % 12 or 12
    return f"{ampm} {hour}시 {dt.minute:02d}분"


def clean_address(address: str) -> str:
    if not address:
        return "위치 정보 없음"
    parts = [p.strip() for p in address.split(",") if p.strip()]
    keep = []
    keywords = [
        "특별자치도", "특별시", "광역시", "도", "시", "군", "구", "동", "읍", "면", "리",
        "항", "해변", "시장", "거리", "카페", "공원", "역", "대학교", "식당", "해수욕장"
    ]
    for p in parts:
        if any(x in p for x in keywords):
            keep.append(p)
    keep = list(dict.fromkeys(keep))
    return " ".join(keep[:6]) if keep else address


def gps_to_address(lat: float, lon: float) -> str:
    try:
        geolocator = Nominatim(user_agent="memory_lens_photo_diary_agent")
        location = geolocator.reverse((lat, lon), language="ko", exactly_one=True, timeout=10)
        time.sleep(1)
        if location:
            return clean_address(location.address)
    except Exception:
        pass
    return f"위도 {lat:.6f}, 경도 {lon:.6f}"


def make_thumbnail(image: Image.Image, max_size: int = 300) -> Image.Image:
    img = image.copy()
    img.thumbnail((max_size, max_size))
    return img


def image_to_jpeg_bytes(image: Image.Image, max_size: int = 1280, quality: int = 82) -> bytes:
    img = image.copy().convert("RGB")
    img.thumbnail((max_size, max_size))
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=quality)
    return buffer.getvalue()


def load_photos(uploaded_files) -> list[PhotoItem]:
    photos: list[PhotoItem] = []
    for file in uploaded_files:
        image = Image.open(file)
        exif = get_exif(image)
        dt = get_photo_time(exif)
        gps = get_gps_info(exif)
        address = gps_to_address(gps["lat"], gps["lon"]) if gps else "위치 정보 없음"
        photos.append(PhotoItem(
            file_name=file.name,
            image=image.copy(),
            time=dt,
            time_text=format_korean_time(dt),
            gps=gps,
            address=address,
        ))
    photos.sort(key=lambda p: p.time or datetime.max)
    return photos
