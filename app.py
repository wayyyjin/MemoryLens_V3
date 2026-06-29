import streamlit as st
from openai import OpenAI

from photo_utils import load_photos, make_thumbnail
from event_utils import group_photos, event_time_text
from gpt_utils import analyze_event, summarize_day

st.set_page_config(page_title="Memory Lens", page_icon="📸", layout="wide")

st.title("📸 Memory Lens")
st.subheader("사진으로 하루를 기억해주는 AI Agent")
st.write("---")


def get_api_key():
    try:
        return st.secrets["OPENAI_API_KEY"]
    except Exception:
        return None


api_key = get_api_key()
if not api_key:
    st.error("OpenAI API Key가 설정되지 않았습니다.")
    st.info('Streamlit Cloud의 Secrets에 `OPENAI_API_KEY="sk-proj-..."` 형태로 입력하세요.')
    st.stop()

client = OpenAI(api_key=api_key)

with st.sidebar:
    st.header("⚙️ 분석 설정")
    short_gap = st.slider("짧은 연속 촬영 묶기(분)", 3, 20, 8)
    long_gap = st.slider("같은 장소 장시간 활동 묶기(분)", 30, 300, 180, step=30)
    short_dist = st.slider("짧은 이벤트 거리 기준(m)", 50, 500, 180, step=10)
    long_dist = st.slider("장시간 활동 거리 기준(m)", 100, 1500, 600, step=50)
    st.caption("예: 낚시/축구처럼 오래 이어지는 활동은 같은 장소라면 넓게 묶을 수 있습니다.")

user_name = st.text_input("사용자 이름(별명)을 작성해주세요.", value="", placeholder="예: 홍길동")
if not user_name.strip():
    user_name = "사용자"

day_memo = st.text_area(
    "오늘 하루 어떠셨나요?  하루의 느낌을 문장으로 기록해보세요.",
    placeholder="예: 차가운 물 한 잔이 반가워지는 계절이 온 것 같아.",
    height=90,
)

uploaded_files = st.file_uploader(
    "오늘의 사진을 업로드하세요. (데모버전이라 10장 이내로 할 것)",
    type=["jpg", "jpeg", "png"],
    accept_multiple_files=True,
)

if not uploaded_files:
    st.info("사진을 업로드하시면 하루를 큰 이벤트 단위로 분석하여 기록해드립니다.")
    st.stop()

with st.spinner("사진의 촬영 시간과 위치 정보를 읽는 중입니다..."):
    photos = load_photos(uploaded_files)

with st.spinner("사진을 이벤트 단위로 묶는 중입니다..."):
    events = group_photos(
        photos,
        short_gap_minutes=short_gap,
        long_activity_gap_minutes=long_gap,
        short_distance_meters=short_dist,
        long_distance_meters=long_dist,
    )

st.success(f"총 {len(photos)}장의 사진을 {len(events)}개의 이벤트로 묶었습니다.")


st.write("---")
st.write("## 📝 어떤 하루를 보내셨나요?")
st.caption("각 사진이 어떤 상황이었는지 대략적으로 적어주세요. 사용자의 메모를 통해 더 정확한 추론을 하여 기록해드립니다")

for idx, event in enumerate(events, start=1):
    with st.expander(f"Event {idx} | {event_time_text(event)} | {event.address} | 사진 {len(event.photos)}장", expanded=False):
        cols = st.columns(min(len(event.photos), 6))
        for i, photo in enumerate(event.photos):
            with cols[i % len(cols)]:
                st.image(make_thumbnail(photo.image, 260), caption=photo.time_text, width="content")
        event.note = st.text_area(
            f"Event {idx} 메모",
            placeholder="예: 부모님과 드라이브를 하며 찍은 풍경 사진.",
            key=f"event_note_{idx}",
            height=90,
        ).strip()

st.write("---")

if st.button("🚀 AI 사진 일기 생성", type="primary"):
    analyzed_events = []
    progress = st.progress(0)
    status = st.empty()

    for idx, event in enumerate(events, start=1):
        status.write(f"Event {idx}/{len(events)} 분석 중...")
        try:
            result = analyze_event(client, event, idx, user_name)
        except Exception as e:
            result = {
                "title": f"Event {idx}",
                "location_label": event.address,
                "activity_label": "분석 실패",
                "record": f"이 이벤트 분석 중 오류가 발생했습니다: {e}",
            }
        analyzed_events.append(result)
        progress.progress(idx / len(events))

    status.write("하루 전체 요약 생성 중...")
    try:
        day_summary = summarize_day(client, analyzed_events, user_name, day_memo)
    except Exception as e:
        day_summary = f"하루 요약 생성 중 오류가 발생했습니다: {e}"

    st.write("# 📷 사진 일기")

    diary_text_parts = []
    for idx, (event, result) in enumerate(zip(events, analyzed_events), start=1):
        st.write(f"## Event {idx}. {result['title']}")
        st.caption(f"{event_time_text(event)} · {result['location_label']} · {result['activity_label']}")

        cols = st.columns(min(len(event.photos), 6))
        for i, photo in enumerate(event.photos):
            with cols[i % len(cols)]:
                st.image(make_thumbnail(photo.image, 300), caption=photo.time_text, width="content")

        st.markdown(result["record"])
        st.write("---")

        diary_text_parts.append(
            f"Event {idx}. {result['title']}\n"
            f"시간: {event_time_text(event)}\n"
            f"위치: {result['location_label']}\n"
            f"활동: {result['activity_label']}\n"
            f"기록:\n{result['record']}"
        )

    st.write("# 📖 오늘 하루를 요약해드리면요")
    st.info(day_summary)

    diary_text = "# Memory Lens 사진 일기\n\n"
    diary_text += "\n\n---\n\n".join(diary_text_parts)
    diary_text += "\n\n# AI 하루 요약\n\n" + day_summary

    st.download_button(
        label="📄 TXT로 다운로드",
        data=diary_text,
        file_name="memory_lens_diary.txt",
        mime="text/plain",
    )
