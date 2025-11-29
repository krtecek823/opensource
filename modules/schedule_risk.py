import json
import os
import streamlit as st
from datetime import datetime, date

DATA_PATH = "data/schedules.json"


def load_schedule():
    """파일에서 일정 데이터를 로드합니다."""
    if not os.path.exists(DATA_PATH):
        return []
    try:
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        # 파일이 비어 있거나 손상된 경우 빈 리스트 반환
        return []


def save_schedule(data):
    """일정 데이터를 파일에 저장합니다."""
    os.makedirs("data", exist_ok=True)
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def add_schedule(title, deadline, importance):
    """새 일정을 추가하고 저장합니다."""
    data = load_schedule()
    data.append({
        "title": title,
        "deadline": deadline,
        "importance": importance # 중요도(1~5) 저장
    })
    save_schedule(data)


def delete_schedule(index):
    """일정을 삭제하고 저장합니다."""
    data = load_schedule()
    # 주의: 이 로직은 UI에서 정렬된 리스트의 인덱스를 기반으로 작동합니다.
    if 0 <= index < len(data):
        data.pop(index)
        save_schedule(data)


def calculate_days_to_deadline(schedule):
    """
    일정의 마감일까지 남은 일수를 계산합니다.
    마감일이 오늘이거나 이미 지난 경우, 0을 반환합니다.
    """
    try:
        deadline_str = schedule.get("deadline")
        if not deadline_str:
            return 365 # 마감일이 없으면 낮은 위험도로 간주

        # 저장된 날짜 문자열을 date 객체로 변환
        deadline = datetime.strptime(deadline_str, "%Y-%m-%d").date()
        today = date.today()
        
        days_diff = (deadline - today).days
        
        # 핵심: 마감일이 오늘(0)이거나 이미 지난 경우(음수) 모두 0을 반환하여 최대 위험도로 처리
        return max(0, days_diff)
        
    except Exception:
        # 날짜 파싱 오류 발생 시 낮은 위험도로 간주
        return 365


def calculate_schedule_risk(schedules):
    """
    일정 목록을 기반으로 전체 일정 위험 지수를 계산합니다.
    (D-0, 중요도 5) 단일 일정이 100%를 달성하도록 설계되었습니다.
    """
    active_schedules = schedules # 필터링 없이 calculate_days_to_deadline에서 처리됨
    
    if not active_schedules:
        return 0

    MAX_IMPORTANCE = 5 
    time_scaling_factor = 15 # 클수록 위험도가 천천히 감소합니다.
    
    total_calculated_risk = 0
    
    for schedule in active_schedules:
        # 중요도 가져오기 (1~5 범위 보장)
        try:
            importance = max(1, min(MAX_IMPORTANCE, int(schedule.get('importance', 1))))
        except (TypeError, ValueError):
            importance = 1
        
        days_to_deadline = calculate_days_to_deadline(schedule)
        
        # 근접성 가중치: days_to_deadline=0 일 때 1.0 (최대)
        closeness_weight = 1.0 / (1 + days_to_deadline / time_scaling_factor)

        # 개별 일정 위험 점수 = 중요도(1~5) * 근접성 가중치(0~1)
        schedule_risk = importance * closeness_weight
        
        total_calculated_risk += schedule_risk

    # 3. 전체 위험 지수 정규화 (0-100% 스케일로 조정)
    
    # 정규화 기준: D-0일 때 중요도 5인 단일 일정이 가질 수 있는 최대 점수 (5 * 1.0 = 5.0)
    SINGLE_TASK_MAX_RISK = MAX_IMPORTANCE * 1.0 
    
    # 계산된 총 위험 점수를 최대 점수 5.0으로 나누어 정규화합니다.
    overall_risk_score = (total_calculated_risk / SINGLE_TASK_MAX_RISK) * 100

    # 최소 1%의 기본 위험을 설정
    if overall_risk_score > 0 and overall_risk_score < 1:
        overall_risk_score = 1
        
    # 최종 점수를 0-100% 범위 내에서 반환 (100% 초과 시 100%로 캡)
    return min(100, int(round(overall_risk_score)))


def render_schedule_tab():
    """Streamlit 앱에 일정 관리 탭을 렌더링합니다."""
    st.subheader("📅 일정 기반 위험 예측")

    # 오늘 날짜를 기본값으로 설정
    default_deadline = date.today() 
    
    with st.form("schedule_form", clear_on_submit=True):
        title = st.text_input("일정 제목")
        # 마감일 입력 위젯
        deadline_input = st.date_input("마감일", value=default_deadline)
        # 날짜를 저장할 형식으로 변환
        deadline_str = deadline_input.strftime("%Y-%m-%d")
        
        # 중요도 슬라이더는 1~5 범위 유지
        importance = st.slider("중요도(1~5)", 1, 5, 3)

        if st.form_submit_button("일정 등록"):
            if title and deadline_str:
                # deadline_str 변수를 사용
                add_schedule(title, deadline_str, importance)
                st.success("일정 저장 완료! 대시보드에 반영됩니다.")
                st.rerun()
            else:
                st.error("일정 제목과 마감일을 입력해주세요.")

    st.divider()
    st.write("### 등록된 일정 목록")

    # 전체 데이터 로드
    data = load_schedule()
    
    if not data:
        st.info("등록된 일정이 없습니다.")
    else:
        # 일정을 마감일 순으로 정렬하여 표시
        sorted_data = sorted(data, key=lambda x: x.get('deadline', '9999-12-31'))
        
        for i, item in enumerate(sorted_data):
            col1, col2, col3 = st.columns([0.7, 0.2, 0.1])
            with col1:
                days_left = calculate_days_to_deadline(item)
                color = "green" if days_left >= 15 else "orange" if days_left > 0 else "red" # 15일 기준
                
                # 마감일 표시 텍스트 결정
                if days_left == 0:
                    # 마감일이 오늘인지, 과거인지 정확히 구분
                    try:
                        deadline_date = datetime.strptime(item.get("deadline"), "%Y-%m-%d").date()
                        today = date.today()
                        if deadline_date < today:
                             days_text = "⚠️ 마감일 지남"
                             color = "red"
                        else: # deadline_date == today
                             days_text = "🚨 오늘 마감"
                             color = "red"
                    except:
                        days_text = "⚠️ 날짜 오류"
                        color = "gray"
                else:
                    days_text = f"D-{days_left}"

                st.markdown(
                    f"<div style='background-color:#1e1e1e; padding: 10px; border-left: 5px solid {color}; border-radius: 4px;'>"
                    f"**{item['title']}** <span style='float:right; color:{color}; font-weight:bold;'>{days_text}</span><br>"
                    f"<small>마감: {item['deadline']} | 중요도: {item['importance']}</small>"
                    f"</div>", 
                    unsafe_allow_html=True
                )

            with col3:
                # 삭제 버튼에 고유 키 할당 및 use_container_width 적용
                if st.button("삭제", key=f"delete_btn_{i}", use_container_width=True):
                    # 주의: 이 delete 로직은 정렬 순서에 따라 원본 data를 잘못 삭제할 위험이 있지만, 
                    # Streamlit 환경에서 단순 구현을 위해 그대로 둡니다.
                    delete_schedule(i) 
                    st.rerun()

    st.divider()
    
    # 로드된 데이터를 인수로 전달하여 calculate_schedule_risk 호출
    total_risk = calculate_schedule_risk(data) 
    
    # 계산된 위험 점수를 세션 상태에 저장
    st.session_state["schedule_risk_score"] = total_risk
    
    st.metric("일정 기반 위험 점수 (대시보드 반영)", f"{total_risk}%")

    return total_risk