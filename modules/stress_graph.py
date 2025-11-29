import streamlit as st
import json
import os
import pandas as pd
import altair as alt
from datetime import datetime, timedelta

FILE_PATH = "data/stress_log.json"


def load_stress_data():
    """스트레스 기록 데이터를 로드합니다."""
    os.makedirs("data", exist_ok=True)

    if not os.path.exists(FILE_PATH):
        with open(FILE_PATH, "w", encoding="utf-8") as f:
            json.dump([], f)

    with open(FILE_PATH, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            data = []

    # timestamp 컬럼을 확실히 만들어줌
    for item in data:
        if "date" in item:
            try:
                item["timestamp"] = datetime.strptime(item["date"], "%Y-%m-%d %H:%M:%S")
            except:
                try:
                    item["timestamp"] = datetime.strptime(item["date"], "%Y-%m-%d")
                except:
                    item["timestamp"] = datetime.now()
        else:
            item["timestamp"] = datetime.now()

    return data


def save_stress_data(new_record):
    """새로운 스트레스 기록을 저장합니다."""
    data = load_stress_data()

    # timestamp 추가
    record_timestamp = datetime.strptime(new_record["date"], "%Y-%m-%d %H:%M:%S")
    new_record["timestamp"] = new_record["date"]

    data.append(new_record)

    # datetime 저장 불가 → 문자열로 변환
    for item in data:
        if isinstance(item.get("timestamp"), datetime):
            item["timestamp"] = item["timestamp"].strftime("%Y-%m-%d %H:%M:%S")

    with open(FILE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def render_stress_tab():
    """스트레스 기록 입력"""
    st.subheader("스트레스 지수 기록")

    col1, col2 = st.columns([3, 1])

    with col1:
        stress_value = st.slider("현재 스트레스 지수 (1-10)",
                                 min_value=1.0, max_value=10.0, value=5.0, step=0.5)

    with col2:
        now = datetime.now()
        selected_time = st.time_input("시간 선택", now.time())

    if st.button("기록 저장"):
        record_time = datetime.combine(now.date(), selected_time)

        new_record = {
            "date": record_time.strftime("%Y-%m-%d %H:%M:%S"),
            "stress": float(stress_value)
        }

        save_stress_data(new_record)

        st.success(f"{record_time.strftime('%Y-%m-%d %H:%M')} 저장됨")
        st.rerun()


def render_stress_analysis_tab():
    """app.py에서 호출하는 분석 함수 (필요시 app.py의 구조와 동일하게 수정 가능)"""
    st.info("분석은 app.py에서 진행됩니다.")
    return None, None
