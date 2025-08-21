"""Streamlit app for summarizing social news.

- Google Sheet에서 CSV로 데이터를 읽어와
  날짜, 토픽 분류, 요약/뉴스레터를 필터/표시
- 하단에 구글폼 구독 버튼
- tz-naive / tz-aware 혼합 입력 모두 안전하게 처리
"""

from __future__ import annotations

import datetime as _dt
import pandas as _pd
import streamlit as _st

# -----------------------------------------------------------------------------
# Configuration

SHEET_ID: str = "1_HwpbhcZJHqgK0rkl6aRlYOKGGNpL2MAhZ5TDorxJmg"
SHEET_GID: int | str = 0

CSV_URL_TEMPLATE: str = (
    "https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
)

NEWSLETTER_FORM_URL: str = "https://forms.gle/vgY7JfPXpCfudaay7"

REQUIRED_COLS = ["날짜", "제목", "본문", "토픽 분류", "요약", "뉴스레터"]


@_st.cache_data(ttl=300)
def load_sheet() -> _pd.DataFrame:
    """CSV 로드 + 컬럼 정리 + 날짜 표준화(가능하면 tz-naive로)."""
    csv_url = CSV_URL_TEMPLATE.format(sheet_id=SHEET_ID, gid=SHEET_GID)

    try:
        df = _pd.read_csv(csv_url, encoding="utf-8", on_bad_lines="skip")
    except Exception as exc:
        _st.error(
            "데이터를 불러오는 데 실패했습니다. 스프레드시트 공개 설정(보기 권한) 또는 URL을 확인해 주세요.\n"
            f"오류 메시지: {exc}"
        )
        return _pd.DataFrame(columns=REQUIRED_COLS)

    # 컬럼 이름 정규화
    df.columns = df.columns.astype(str).str.strip()
    for c in REQUIRED_COLS:
        if c not in df.columns:
            df[c] = _pd.NA

    # 날짜: 가능한 한 tz-naive (Asia/Seoul)로 통일
    # 1) 우선 UTC 기준 tz-aware로 파싱 시도
    s = _pd.to_datetime(df["날짜"], errors="coerce", utc=True)

    # 2) Asia/Seoul로 변환
    try:
        s = s.dt.tz_convert("Asia/Seoul")
        # 3) tz 제거(naive) — 여기서 tz를 떼면 이후 비교가 단순해짐
        s = s.dt.tz_localize(None)
    except Exception:
        # 혹시 tz 변환이 실패하면 남은 값은 그대로 두되, 나중에 filter에서 tz-aware/naive를 동적으로 맞춤
        pass

    df["날짜"] = s
    return df


def _coerce_range_like_series_tz(
    start: _dt.date,
    end: _dt.date,
    series: _pd.Series,
) -> tuple[_pd.Timestamp, _pd.Timestamp]:
    """시리즈의 tz 상태에 맞춰 (start, end) 비교값을 생성.

    - series 가 tz-aware 이면: start/end 를 같은 tz로 tz_localize
    - series 가 tz-naive 이면: start/end 도 tz-naive 로 생성
    """
    start_ts = _pd.Timestamp(start)
    end_ts = _pd.Timestamp(end) + _pd.Timedelta(days=1) - _pd.Timedelta(seconds=1)

    tz = None
    try:
        tz = getattr(series.dt, "tz", None)
    except Exception:
        tz = None

    if tz is not None:
        # tz-aware 비교 필요
        # start/end가 이미 tz가 있다면 tz_convert, 없으면 tz_localize
        if start_ts.tzinfo is None:
            start_ts = start_ts.tz_localize(tz)
        else:
            start_ts = start_ts.tz_convert(tz)
        if end_ts.tzinfo is None:
            end_ts = end_ts.tz_localize(tz)
        else:
            end_ts = end_ts.tz_convert(tz)

    # tz-naive 시리즈면 그대로 naive 비교값 사용
    return start_ts, end_ts


def filter_data(
    df: _pd.DataFrame,
    topics: list[str] | None,
    date_range: tuple[_dt.date, _dt.date] | None,
) -> _pd.DataFrame:
    """토픽/날짜 필터. tz-naive/aware 혼합도 안전 처리."""
    filtered = df.copy()

    if topics:
        filtered = filtered[filtered["토픽 분류"].isin(topics)]

    if date_range:
        start, end = date_range
        # '날짜'가 tz-naive로 통일되어 있으면 그대로,
        # 아니면 tz-aware이면 아래 함수가 start/end를 맞춰줌
        start_dt, end_dt = _coerce_range_like_series_tz(start, end, filtered["날짜"])

        mask = filtered["날짜"].notna()
        filtered = filtered[mask & (filtered["날짜"] >= start_dt) & (filtered["날짜"] <= end_dt)]

    filtered = filtered.sort_values("날짜", ascending=False, na_position="last")
    return filtered


def _format_when_display(ts: _pd.Timestamp) -> str:
    """화면 표시용 날짜 포맷. tz-aware면 Asia/Seoul로 보여줌."""
    if not isinstance(ts, _pd.Timestamp) or _pd.isna(ts):
        return ""
    try:
        if ts.tzinfo is not None:
            return ts.tz_convert("Asia/Seoul").strftime("%Y-%m-%d %H:%M")
        return ts.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ""


def main() -> None:
    _st.set_page_config(page_title="오늘의 사회 스낵", layout="wide")
    # 라이트모드 CSS 강제 적용
    _st.markdown(
        """
        <style>
        body, .stApp, [data-testid='stAppViewContainer'], [data-testid='stSidebar'], [data-testid='stHeader'],
        h1, h2, h3, h4, h5, h6, p, div, span, label, input, textarea, .markdown-text-container, .stMarkdown, .stText, .stCaption,
        .css-1v0mbdj, .css-10trblm, .css-1c7y2kd, .css-1d391kg, .css-1dp5vir, .css-1v3fvcr, .css-1y4p8pa, .css-1w2yozk {
            background-color: #ffffff !important;
            color: #262730 !important;
        }
        /* 버튼 내부 배경만 투명, 바깥쪽(테두리 등)은 유지 */
        .stButton>button {
            background-color: transparent !important;
            color: #222 !important;
            box-shadow: 0 0 0 4px #2c2c36 !important;
            border: none !important;
            padding: 0.5em 1em !important;
        }
        /* 드롭다운 옵션 hover 시 검은 배경, 나머지는 투명하게 */
        .stMultiSelect .css-1n76uvr, .stMultiSelect .css-1n76uvr:hover {
            background-color: transparent !important;
        }
        .stMultiSelect .css-1n76uvr[aria-selected="true"],
        .stMultiSelect .css-1n76uvr:hover {
            background-color: #222 !important;
            color: #fff !important;
        }
        </style>
        """,
        unsafe_allow_html=True
    )
    # 라이트모드 CSS 강제 적용
    _st.markdown(
        """
        <style>
        body, .stApp, [data-testid='stAppViewContainer'], [data-testid='stSidebar'], [data-testid='stHeader'],
        h1, h2, h3, h4, h5, h6, p, div, span, label, input, textarea, .markdown-text-container, .stMarkdown, .stText, .stCaption,
        .css-1v0mbdj, .css-10trblm, .css-1c7y2kd, .css-1d391kg, .css-1dp5vir, .css-1v3fvcr, .css-1y4p8pa, .css-1w2yozk {
            background-color: #ffffff !important;
            color: #262730 !important;
        }
        /* 버튼 내부 배경만 투명, 바깥쪽(테두리 등)은 유지 */
        .stButton>button {
            background-color: transparent !important;
            color: #222 !important;
            box-shadow: 0 0 0 4px #2c2c36 !important;
            border: none !important;
            padding: 0.5em 1em !important;
        }
        /* 드롭다운 옵션 hover 시 검은 배경, 기본 흰 배경 제거 */
        .stMultiSelect .css-1n76uvr, .stMultiSelect .css-1n76uvr:hover {
            background-color: transparent !important;
        }
        .stMultiSelect .css-1n76uvr[aria-selected="true"],
        .stMultiSelect .css-1n76uvr:hover {
            background-color: #222 !important;
            color: #fff !important;
        }
        </style>
        """,
        unsafe_allow_html=True
    )
    _st.title("오늘의 사회 스낵")

    data = load_sheet()
    if data.empty:
        _st.info("표시할 데이터가 없습니다. 스프레드시트에 데이터가 있는지 확인해 주세요.")
        return

    _st.sidebar.header("필터")

    topics = sorted(t for t in data["토픽 분류"].dropna().unique().tolist() if isinstance(t, str))
    selected_topics = _st.sidebar.multiselect("토픽 분류", options=topics, default=[])

    if data["날짜"].notnull().any():
        min_date = data["날짜"].min()
        max_date = data["날짜"].max()
        # Timestamp → date
        min_date = min_date.date() if isinstance(min_date, _pd.Timestamp) else _dt.date.today()
        max_date = max_date.date() if isinstance(max_date, _pd.Timestamp) else _dt.date.today()
    else:
        today = _dt.date.today()
        min_date, max_date = today, today

    selected_range = _st.sidebar.date_input(
        "날짜 범위",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
    )
    if isinstance(selected_range, _dt.date):
        date_range = (selected_range, selected_range)
    else:
        date_range = tuple(selected_range) if selected_range else (min_date, max_date)

    # 뉴스레터 구독 버튼 제거됨

    filtered_data = filter_data(data, selected_topics, date_range)

    _st.subheader("뉴스레터")
    if filtered_data.empty:
        _st.warning("선택한 조건에 해당하는 뉴스가 없습니다.")
    else:
        for _, row in filtered_data.iterrows():
            title = row.get("제목", "제목 없음") or "제목 없음"
            date_display = _format_when_display(row.get("날짜"))

            _st.markdown(f"### {title}")
            if date_display:
                _st.caption(date_display)

            with _st.expander("요약 보기", expanded=False):
                _st.markdown(row.get("요약", "") or "")

            _st.markdown(row.get("뉴스레터", "") or "")
            _st.markdown("---")


if __name__ == "__main__":
    # Streamlit 실행 권장:
    #   streamlit run /Users/gim-yelim/Desktop/streamlit/streamlit_app.py
    main()
