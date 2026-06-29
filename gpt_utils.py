from __future__ import annotations

import base64
import json
import re
from typing import Any

from openai import OpenAI

from event_utils import EventItem, event_time_text
from photo_utils import image_to_jpeg_bytes


EVENT_MODEL = "gpt-4o"
SUMMARY_MODEL = "gpt-4o-mini"


def _image_content(event: EventItem, max_images: int = 8) -> list[dict[str, Any]]:
    content = []
    for idx, photo in enumerate(event.photos[:max_images], start=1):
        b64 = base64.b64encode(image_to_jpeg_bytes(photo.image)).decode("utf-8")
        content.append({
            "type": "input_image",
            "image_url": f"data:image/jpeg;base64,{b64}",
        })
    return content


def _extract_json(text: str) -> dict[str, str]:
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    return {
        "title": "하루의 한 장면",
        "location_label": "장소 추정 어려움",
        "activity_label": "활동 추정",
        "record": text.strip(),
    }


def analyze_event(client: OpenAI, event: EventItem, event_index: int, user_name: str) -> dict[str, str]:
    time_text = event_time_text(event)
    address = event.address
    note = event.note.strip() or "사용자 메모 없음"

    prompt = f"""
너는 사진 기반 라이프로그를 작성하는 고급 AI Agent다.
너의 목표는 사진 여러 장을 '하나의 이벤트'로 묶어 해석하고, 1년 뒤에도 그날 상황이 떠오르는 자연스러운 기록을 만드는 것이다.

[중요한 전제]
- 아래 사진들은 개별 사진이 아니라 하나의 이벤트에 속한다.
- 사진이 여러 장이면 각각 설명하지 말고, 하나의 활동 흐름으로 통합해라.
- 사용자의 이벤트 메모는 정답에 가까운 힌트다. 반드시 참고하되, 문장을 그대로 복사하지 마라.
- 사진만 보고 사람의 신원을 단정하지 마라. 단, 메모에 가족/친구/본인/동료라고 적혀 있으면 그 관계 정보는 사용할 수 있다.

[입력 정보]
사용자 이름: {user_name}
이벤트 번호: {event_index}
시간: {time_text}
EXIF 기반 위치: {address}
사진 수: {len(event.photos)}장
사용자 이벤트 메모(힌트): {note}

[분석 기준]
1. 사진 속 장면, 음식, 간판, 메뉴판, 물건, 풍경, 복장, 움직임을 모두 종합해라.
2. 시간과 위치를 함께 고려해서 오전/오후 활동의 맥락을 만들어라.
3. 낚시, 축구, 등산, 쇼핑, 카페 작업, 식사처럼 시간이 오래 걸리는 활동은 시작/끝 사진만 있어도 이어진 활동으로 서술해라.
4. 장소명은 확실하면 구체적으로 쓰고, 불확실하면 '~근처', '~로 보이는 곳'이라고 써라.
5. 메모 내용은 결과에 그대로 노출하지 말고, 자연스러운 문장으로 재구성해라.
6. 사용자가 쓴 일기처럼 쓰는 것이 아니라, 어떤 활동을 한 것인지 기록을 해주는 것임을 명심해라.

[출력]
반드시 JSON만 출력해라. 마크다운 금지.
키는 반드시 아래 4개만 사용해라.
{{
  "title": "이 이벤트를 8~18자 한국어 제목으로 요약",
  "location_label": "사용자에게 보여줄 자연스러운 장소명",
  "activity_label": "카페/식사/낚시/운동/산책/이동 등 활동 라벨",
  "record": "{user_name}님은 ... 으로 시작하는 5~8문장 자연스러운 기록. 메모 원문을 그대로 복사하지 말 것. 추측은 추측처럼 표현할 것."
}}
"""

    content = [{"type": "input_text", "text": prompt}]
    content.extend(_image_content(event, max_images=8))

    response = client.responses.create(
        model=EVENT_MODEL,
        input=[{"role": "user", "content": content}],
    )
    data = _extract_json(response.output_text)
    return {
        "title": str(data.get("title", "하루의 한 장면")).strip(),
        "location_label": str(data.get("location_label", address)).strip(),
        "activity_label": str(data.get("activity_label", "활동")).strip(),
        "record": str(data.get("record", response.output_text)).strip(),
    }


def summarize_day(client: OpenAI, analyzed_events: list[dict[str, str]], user_name: str, day_memo: str) -> str:
    joined = "\n\n".join(
        f"[{i+1}] {ev.get('title')} / {ev.get('location_label')} / {ev.get('activity_label')}\n{ev.get('record')}"
        for i, ev in enumerate(analyzed_events)
    )

    prompt = f"""
너는 하루를 정리하는 AI Life Logger다.
아래 이벤트 기록을 바탕으로 하루 전체 요약을 작성해라.

사용자 이름: {user_name}
사용자 전체 메모(힌트): {day_memo if day_memo.strip() else '없음'}

이벤트 기록:
{joined}

작성 규칙:
- 반드시 "{user_name}님은 오늘"로 시작해라.
- 이벤트 순서를 따라 시간 흐름이 느껴지게 써라.
- 전체 메모는 참고하되 원문을 그대로 복사하지 마라.
- 7~11문장으로 써라.
- 너무 기계적인 나열이 아니라, 하루를 회상하는 자연스러운 문장으로 써라.
- 불확실한 내용은 '~로 보여요', '~했을 가능성이 있어요'처럼 표현해라.
- 느낀점은 쓰지마라. 느낀점은 사용자가 느끼는 것이지, 네가 추론해서 작성하는 것이 절대 아니다.
- 너는 따뜻한 이야기꾼이다. "사진을 보니 ~를 하신 것 같아요! ~하셨다고 기록하셨는데 정말 즐거웠을 것 같아요." 이런식으로 "해요 체로" 쓸 것이다.

"""
    response = client.responses.create(model=SUMMARY_MODEL, input=prompt)
    return response.output_text.strip()
