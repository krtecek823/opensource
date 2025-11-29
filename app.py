import streamlit as st
import pandas as pd
import altair as alt
import json
from datetime import datetime
import sys
import os
import time

# ---------------------------
# 모듈 임포트 (프로젝트 내부 modules 사용)
# ---------------------------
try:
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from modules import stress_graph, schedule_risk, risk_analysis, gemini_client, google_calendar
except Exception as e:
    st.error(f"필요한 모듈(stress_graph, schedule_risk 등)을 찾을 수 없습니다. ZeroDeadline 기능을 위해 해당 모듈들을 생성하거나 더미 함수로 대체해야 합니다. {e}")
    # 필요한 모듈이 없으면 실행을 중지합니다.
    st.stop() 

# ---------------------------
# 설정
# ---------------------------
st.set_page_config(layout="wide", page_title="ZeroDeadline", page_icon="🚨")

# 실제 API Key를 입력하세요. 
API_KEY = "AIzaSyCLA6mWtjJ4D5rQR_IrdmaYjJUfHiEI1fY" 
RISK_HISTORY_FILE = "data/risk_history.json"

if not API_KEY or not API_KEY.startswith("AIza"):
    st.error("API_KEY가 설정되지 않았거나 올바르지 않습니다. app.py의 API_KEY를 확인하세요.")
    st.stop()

MODEL_NAME = "models/gemini-2.5-flash"

try:
    model = gemini_client.init_gemini(API_KEY, MODEL_NAME)
except Exception as e:
    st.error(f"Gemini 초기화 실패: {e}")
    st.stop()

# ---------------------------
# 위험 기록 관리 함수
# ---------------------------
def load_risk_history():
    """위험 기록 파일에서 데이터를 로드합니다."""
    if not os.path.exists(RISK_HISTORY_FILE):
        return []
    try:
        with open(RISK_HISTORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return []

def save_current_risk(combined_score):
    """현재 통합 위험 지수를 기록 파일에 저장합니다."""
    history = load_risk_history()
    current_time_str = datetime.now().isoformat()
    new_entry = {"timestamp": current_time_str, "risk": combined_score}

    if history:
        last_entry = history[-1]
        # 직전 기록과 점수가 같으면 저장하지 않아 불필요한 데이터를 줄임
        if last_entry.get("risk") == combined_score:
            return

    history.append(new_entry)
    # 최대 30개 항목만 유지
    if len(history) > 30:
        history = history[-30:]

    os.makedirs(os.path.dirname(RISK_HISTORY_FILE), exist_ok=True)
    try:
        with open(RISK_HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=4)
    except IOError as e:
        st.error(f"위험 기록 저장 실패: {e}")

# ---------------------------
# 세션 초기화
# ---------------------------
if "chat_history" not in st.session_state:
    st.session_state.chat_history = [{"role": "assistant", "text": "안녕하세요! ZeroDeadline에 오신 것을 환영합니다."}]

if "user_data" not in st.session_state:
    st.session_state.user_data = {
        '학업': {'GPA': 3.5, '이번 학기 학점': 'B+', '최근 성적 변화': -0.2},
        '건강': {'일일 수면 시간': 6.5, '주당 운동 횟수': 2, '스트레스 지수 (10점 만점)': 7},
        '재정': {'월 평균 수입': 250, '월 평균 지출': 200, '순자산 변화율 (3개월)': 5}
    }

# schedules 키가 없으면 빈 리스트로 초기화 (일정 위험 계산의 오류 방지)
if "schedules" not in st.session_state.user_data:
    st.session_state.user_data["schedules"] = []

if "previous_combined_risk" not in st.session_state:
    st.session_state.previous_combined_risk = 0

# 현재 페이지 상태 관리
if "active_page" not in st.session_state:
    st.session_state.active_page = "dashboard"

# ---------------------------
# 위험 브리핑 코멘트
# ---------------------------
def get_risk_comment(combined_score):
    """통합 위험 점수에 따른 브리핑 텍스트와 레벨을 반환합니다."""
    if combined_score <= 30:
        return "현재 위험 상태는 **매우 안정적**입니다.", "success"
    elif combined_score <= 60:
        return "현재 위험 상태는 **양호**하지만 주의가 필요합니다.", "info"
    elif combined_score <= 80:
        return "현재 위험 상태는 **관심** 단계입니다. 일정 위험과 높은 스트레스는 위험도를 높입니다. 수면 시간을 늘리고 가벼운 운동 또는 명상 등의 스트레스 관리가 필요합니다.", "warning"
    else:
        return "현재 위험 상태는 **경고** 단계입니다! 즉각적인 조치가 필요합니다. 모든 위험 요인에 대한 심층 분석을 확인하고 개선 계획을 세우세요.", "error"

# ---------------------------
# 위험 단계별 색상 코드
# ---------------------------
def get_risk_color_code(risk_level):
    """위험 레벨에 따른 HEX 색상 코드를 반환합니다."""
    if risk_level == "success":
        return "#198754" # 진한 초록 (매우 안정적)
    elif risk_level == "info":
        return "#0dcaf0" # 하늘색 (양호)
    elif risk_level == "warning":
        return "#ffc107" # 주황 (관심)
    elif risk_level == "error":
        return "#dc3545" # 빨강 (경고)
    return "#333333" # 기본

# ---------------------------
# 페이지 이동 함수
# ---------------------------
def navigate_to(page_name):
    """지정된 페이지로 이동하고 페이지를 새로고침하는 함수"""
    st.session_state.active_page = page_name
    st.rerun()

# =================================================================
# 통합 위험 지수 계산 로직
# =================================================================
# 기본 위험 점수 계산 (모든 페이지에서 사용됨)
basic_score, basic_text = risk_analysis.analyze_basic_risk(st.session_state.user_data)

# 일정 기반 위험 점수 계산
schedules_for_calc = st.session_state.user_data.get("schedules", [])
try:
    schedule_score = schedule_risk.calculate_schedule_risk(schedules_for_calc)
except TypeError:
    # 모듈 함수가 인자를 받지 않는 경우를 대비한 호환성 처리
    try:
        schedule_score = schedule_risk.calculate_schedule_risk()
    except Exception:
        schedule_score = 0

# 스트레스 데이터 로드 및 평균 계산
df_stress = stress_graph.load_stress_data()
avg_stress = 5.0 

if df_stress:
    pdf = pd.DataFrame(df_stress)
    if "stress" in pdf.columns and not pdf["stress"].empty:
        try:
            # 스트레스 점수의 평균을 계산 (10점 만점 기준)
            avg_stress_calc = round(pdf["stress"].astype(float).mean(), 2)
            avg_stress = avg_stress_calc if avg_stress_calc is not None else 5.0
        except Exception:
            pass

# 통합 위험 지수 계산 (가중치: 기본 50%, 일정 30%, 스트레스 20%)
stress_val = avg_stress if isinstance(avg_stress, (int, float)) else 5.0
try:
    # 스트레스 점수는 10점 만점이므로 10을 곱하여 100점 만점 기준으로 변환 후 20% 가중
    combined = int((basic_score * 0.5) + (schedule_score * 0.3) + (stress_val * 10 * 0.2))
    combined = min(100, max(0, combined)) # 0~100 범위 보장
except Exception:
    combined = basic_score

# 위험 레벨 및 색상 계산
risk_comment_text, risk_level = get_risk_comment(combined)
risk_color = get_risk_color_code(risk_level)

# 이전 대비 변화량 계산
previous_risk = st.session_state.previous_combined_risk
delta_risk = combined - previous_risk

# 위험 기록 저장 및 세션 업데이트
st.session_state.previous_combined_risk = combined
save_current_risk(combined)


# ---------------------------
# 레이아웃
# ---------------------------
st.sidebar.title("🚨 ZeroDeadline Controls")
st.header("ZeroDeadline — 인생 위험 대시보드")

# ---------------------------
# 통합 위험 변화 메트릭을 사이드바에 항시 표시
# ---------------------------
with st.sidebar:
    st.markdown("---")
    st.subheader("통합 위험 변화")
    st.metric(
        label="현재 통합 위험 지수",
        value=f"{combined}%",
        delta=f"{delta_risk:.1f}%",
        delta_color="inverse"
    )
    st.write(f"_(이전 위험 지수: {previous_risk}%)_")
    st.markdown("---")
    
# ---------------------------
# 메인 내비게이션 (st.radio 사용)
# ---------------------------
page_names = ["대시보드", "스트레스 기록", "일정 관리 & 위험 예측", "AI 분석(요약/개선안)", "챗봇"]
page_keys = ["dashboard", "stress", "schedule", "ai", "chatbot"]

# 현재 active_page에 해당하는 인덱스를 찾아 기본값으로 설정
current_index = page_keys.index(st.session_state.active_page)

selected_page_name = st.radio(
    "페이지 선택:",
    page_names,
    index=current_index,
    horizontal=True
)

# 라디오 버튼 클릭 시 active_page 상태 업데이트
if selected_page_name:
    st.session_state.active_page = page_keys[page_names.index(selected_page_name)]

# ---------------------------
# 사이드바 하단
# ---------------------------
st.sidebar.markdown("<br>", unsafe_allow_html=True)
st.sidebar.markdown("---")


# ---------------------------
# 챗봇 플로팅 버튼 (메인 컨텐츠 영역 오른쪽 하단에 위치)
# ---------------------------
# 챗봇 페이지일 때는 이 버튼을 숨깁니다.
if st.session_state.active_page != "chatbot":
    # 3개의 컬럼을 만들어 마지막 컬럼에 버튼을 위치시켜 오른쪽으로 정렬합니다.
    col_empty1, col_empty2, col_chat_btn = st.columns([1, 1, 0.4]) 
    
    with col_chat_btn:
        # 버튼을 누르면 챗봇 페이지로 이동
        if st.button("🧑‍💻 AI 상담 요청", use_container_width=True, key="floating_chatbot_btn"):
            navigate_to("chatbot")


# ---------------------------
# 메인 컨텐츠 (조건부 렌더링 시작)
# ---------------------------
if st.session_state.active_page == "dashboard":
# =================================================================
# Page 0: 대시보드
# =================================================================
    st.subheader("종합 위험 현황")
    
    avg_stress_display = f"{avg_stress}" if isinstance(avg_stress, (int, float)) else "기록 없음"

    col1, col2, col3 = st.columns(3)
    col1.metric("기본 위험 점수 (데이터 기반)", f"{basic_score}%")
    col2.metric("일정 기반 위험 점수", f"{schedule_score}%")
    col3.metric("최근 평균 스트레스", avg_stress_display)

    st.divider()
    
    # 통합 위험 지수 색상 변경 적용
    st.write("#### 통합 위험 지수")
    st.markdown(
        f"<div style='background-color: {risk_color}; padding: 15px; border-radius: 10px; color: white; text-align: center;'>"
        f"<span style='font-size: 1.2rem; font-weight: bold;'>통합 위험 지수</span>"
        f"<h1 style='margin: 0; font-size: 3rem;'>{combined}%</h1>"
        "</div>",
        unsafe_allow_html=True
    )

    st.write("#### 위험 브리핑 (기본)")

    if risk_level == "success":
        st.success(risk_comment_text)
    elif risk_level == "info":
        st.info(risk_comment_text)
    elif risk_level == "warning":
        st.warning(risk_comment_text)
    elif risk_level == "error":
        st.error(risk_comment_text)
    else:
        st.info(risk_comment_text)

    st.write("#### 주요 위험 요인 기여도")

    stress_val_safe = avg_stress if isinstance(avg_stress, (int, float)) else 5.0
    # 스트레스 레벨 기여도 (최대 100점 중 20%)를 위한 점수 변환
    stress_level_score = (stress_val_safe * 10) 
    chart_data = pd.DataFrame({
        '위험 요인': ['기본 위험', '일정 위험', '스트레스 레벨'],
        '위험 점수': [basic_score, schedule_score, stress_level_score]
    })

    base = alt.Chart(chart_data).encode(
        theta=alt.Theta("위험 점수", stack=True)
    )

    # 파이/도넛 차트 생성
    pie = base.mark_arc(outerRadius=150, innerRadius=100).encode(
        color=alt.Color("위험 요인", legend=alt.Legend(title="위험 요인")),
        order=alt.Order("위험 점수", sort="descending"),
        tooltip=["위험 요인", alt.Tooltip("위험 점수", format=".1f")]
    )

    chart = (pie).properties(
        height=400
    ).configure_view(
        strokeWidth=0
    )

    col_l, col_c, col_r = st.columns([2, 3, 2])
    with col_c:
        st.altair_chart(chart, use_container_width=True)

    # 통합 위험 지수 변동 추이
    st.markdown("---")
    st.subheader("통합 위험 지수 변동 추이")
    risk_history = load_risk_history()

    if len(risk_history) > 1:
        df_risk_trend = pd.DataFrame(risk_history)
        df_risk_trend['timestamp'] = pd.to_datetime(df_risk_trend['timestamp'])
        
        risk_trend_chart = alt.Chart(df_risk_trend).mark_line(point=True).encode(
            x=alt.X('timestamp:T', axis=alt.Axis(title='시간', format="%m-%d %H:%M", labelAngle=0)),
            y=alt.Y('risk:Q', axis=alt.Axis(title='통합 위험 지수 (%)'), scale=alt.Scale(domain=[0, 100])),
            tooltip=[alt.Tooltip('timestamp', title='시간', format="%Y-%m-%d %H:%M"), alt.Tooltip('risk', title='위험 지수 (%)')],
            color=alt.value("#f87171")
        ).properties(
            height=300
        )
        
        st.altair_chart(risk_trend_chart, use_container_width=True)
        st.caption(f"총 {len(risk_history)}개의 위험 기록 데이터가 저장되었습니다.")
    else:
        st.info("위험 지수 변동 추이를 확인하려면 기록된 데이터가 최소 2개 이상 필요합니다. 활동을 통해 데이터를 생성해보세요.")
        st.caption(f"현재 {len(risk_history)}개의 위험 기록 데이터가 저장되었습니다.")


elif st.session_state.active_page == "stress":
# =================================================================
# Page 1: 스트레스 기록 & 그래프
# =================================================================
    # 스트레스 기록 UI 렌더링 (modules/stress_graph.py 에 정의된 함수 사용)
    df_stress_ui_result = stress_graph.render_stress_tab()

    st.markdown("---")
    st.subheader("스트레스 지수 변동 추이 분석")

    df_stress = stress_graph.load_stress_data()

    if df_stress and len(df_stress) > 0:
        pdf_stress = pd.DataFrame(df_stress)

        # 시간 컬럼 감지
        if 'timestamp' in pdf_stress.columns:
            time_col = 'timestamp'
        elif 'date' in pdf_stress.columns:
            time_col = 'date'
        else:
            time_col = None

        if time_col and 'stress' in pdf_stress.columns:
            # 명확히 datetime 으로 변환
            pdf_stress[time_col] = pd.to_datetime(pdf_stress[time_col], errors='coerce')
            pdf_stress = pdf_stress.dropna(subset=[time_col]) # 유효하지 않은 datetime 행 제거
            
            if pdf_stress.empty:
                st.warning("유효한 시간 정보가 포함된 스트레스 데이터가 없습니다.")
                st.write("※ 그래프 데이터는 data/stress_log.json에 저장됩니다.")
                st.stop()
            
            pdf_stress['stress'] = pdf_stress['stress'].astype(float)
            pdf_stress = pdf_stress.sort_values(by=time_col).reset_index(drop=True)

            # 월별 비교 Metric
            st.markdown("### 월별 스트레스 변화")
            now = datetime.now()
            current_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            # 지난 달의 시작일 계산
            last_month_start = (current_month_start.replace(day=1) - pd.DateOffset(months=1)).replace(day=1)

            current_month_data = pdf_stress[pdf_stress[time_col] >= current_month_start]
            last_month_end = current_month_start
            last_month_data = pdf_stress[(pdf_stress[time_col] >= last_month_start) & (pdf_stress[time_col] < last_month_end)]

            current_month_name = f"{now.month}월"
            last_month_name = f"{last_month_start.month}월"

            avg_current_month = round(current_month_data['stress'].mean(), 2) if not current_month_data.empty else 0.0
            avg_last_month = round(last_month_data['stress'].mean(), 2) if not last_month_data.empty else 0.0
            monthly_delta = avg_current_month - avg_last_month

            col_m1, col_m2, col_m3 = st.columns(3)
            col_m1.metric(f"{current_month_name} 평균 스트레스", f"{avg_current_month:.1f}점")
            col_m2.metric(f"{last_month_name} 평균 스트레스", f"{avg_last_month:.1f}점")
            col_m3.metric("월별 변화", f"{monthly_delta:.1f}점", delta_color="inverse")

            st.markdown("---")

            # 기간별 추이 시각화
            st.markdown("### 기간별 스트레스 추이 시각화")
            trend_option = st.radio(
                "기간별 추이 선택:",
                ('개별 기록 추이', '일별 평균 추이', '주차별 평균 추이', '월별 평균 추이'),
                index=0,
                horizontal=True,
                key='stress_trend_radio'
            )

            # 그래프 생성 함수 (X축 타입에 따라 회전/타입 명시)
            def create_stress_chart(df, x_field, x_title, x_format="", x_type='T', domain_min=None, domain_max=None, tick_count=None):
                """
                x_type: 'T' = temporal, 'N' = nominal
                """
                
                # datetime 객체를 ISO 8601 문자열로 변환 (Altair Temporal Scale용)
                if isinstance(domain_min, datetime):
                    domain_min = domain_min.isoformat()
                if isinstance(domain_max, datetime):
                    domain_max = domain_max.isoformat()
                        
                x_scale = alt.Scale(domain=[domain_min, domain_max]) if domain_min and domain_max else alt.Undefined

                if x_type == 'T':
                    x_axis = alt.Axis(title=x_title, labelAngle=0, format=x_format, tickCount=tick_count)
                    x_encoding = alt.X(f"{x_field}:T", axis=x_axis, scale=x_scale)
                    tooltip_x = alt.Tooltip(f"{x_field}:T", title=x_title, format=x_format)
                else: # Nominal Type
                    # 명목형(Nominal) X축의 정렬 순서를 명시하기 위해 복사본을 만들어 정렬합니다.
                    df_copy = df.copy()
                    if x_field in df_copy.columns:
                         df_copy[x_field] = df_copy[x_field].astype(str)
                         sort_order = df_copy[x_field].tolist()
                    else:
                         sort_order = None # 정렬 순서 없음
                         
                    x_encoding = alt.X(f"{x_field}:N", sort=sort_order, axis=alt.Axis(title=x_title, labelAngle=0))
                    tooltip_x = alt.Tooltip(f"{x_field}:N", title=x_title)

                chart = alt.Chart(df).mark_line(point=True).encode(
                    x=x_encoding,
                    y=alt.Y('stress:Q', axis=alt.Axis(title='평균 스트레스 지수 (10점)', format=".1f"), scale=alt.Scale(domain=[0, 10])),
                    tooltip=[tooltip_x, alt.Tooltip('stress:Q', title='스트레스 지수 (10점)', format=".1f")],
                    color=alt.value("#3b82f6")
                ).properties(
                    height=300
                ) 

                return chart

            chart = None
            if trend_option == '개별 기록 추이':
                # 개별 기록은 시간을 기준으로 시각화합니다.
                df_plot = pdf_stress[[time_col, 'stress']].copy()
                
                # time_of_day 필드를 생성하여 24시간 주기로 매핑
                today = datetime.now().date()
                df_plot['time_of_day'] = df_plot[time_col].apply(
                    lambda t: datetime.combine(today, t.time())
                )
                
                domain_min_dt = datetime.combine(today, datetime.min.time())
                domain_max_dt = datetime.combine(today, datetime.max.time())
                
                chart = create_stress_chart(
                    df_plot,
                    'time_of_day',
                    '시간 (24시간 기준)',
                    '%H:%M', 
                    x_type='T',
                    domain_min=domain_min_dt, 
                    domain_max=domain_max_dt, 
                    tick_count='hour' 
                )
                st.caption("※ 이 그래프는 24시간 주기 내에서의 기록 시간대를 보여줍니다.")


            elif trend_option == '일별 평균 추이':
                # 일별 평균은 날짜(date) 기준으로 그룹핑
                df_daily = pdf_stress.set_index(time_col)['stress'].resample('D').mean().reset_index()
                df_daily.columns = [time_col, 'stress']
                df_daily['day_label'] = pd.to_datetime(df_daily[time_col]).dt.strftime('%Y-%m-%d')
                df_daily = df_daily.sort_values(time_col).reset_index(drop=True).dropna(subset=['stress'])
                
                chart = create_stress_chart(
                    df_daily[['day_label', 'stress']].rename(columns={'day_label': 'day_label'}),
                    'day_label',
                    '날짜',
                    '',
                    x_type='N'
                )

            elif trend_option == '주차별 평균 추이':
                # 주차별 평균은 월요일을 시작으로 하는 주(W-MON) 기준으로 그룹핑
                df_weekly = pdf_stress.set_index(time_col)['stress'].resample('W-MON').mean().reset_index()
                df_weekly.columns = [time_col, 'stress']
                df_weekly['week_label'] = df_weekly[time_col].dt.strftime('%Y년 %W주차')
                df_weekly = df_weekly.sort_values(time_col).reset_index(drop=True).dropna(subset=['stress'])

                chart = create_stress_chart(
                    df_weekly[['week_label', 'stress']].rename(columns={'week_label': 'week_label'}),
                    'week_label',
                    '주차',
                    '',
                    x_type='N'
                )

            elif trend_option == '월별 평균 추이':
                # 월별 평균은 월(M) 기준으로 그룹핑
                df_monthly = pdf_stress.set_index(time_col)['stress'].resample('M').mean().reset_index()
                df_monthly.columns = [time_col, 'stress']
                df_monthly['month_label'] = df_monthly[time_col].dt.strftime('%Y년 %m월')
                df_monthly = df_monthly.sort_values(time_col).reset_index(drop=True).dropna(subset=['stress'])

                chart = create_stress_chart(
                    df_monthly[['month_label', 'stress']].rename(columns={'month_label': 'month_label'}),
                    'month_label',
                    '월',
                    '',
                    x_type='N'
                )

            if chart:
                st.altair_chart(chart, use_container_width=True)
                if trend_option == '주차별 평균 추이':
                    st.caption("※ '주차별 평균 추이'는 해당 주차(7일) 동안 기록된 모든 점수의 평균 1개를 점으로 표시합니다. 여러 주에 걸쳐 기록해야 추이(선)가 나타납니다.")
                else:
                    st.caption(f"총 {len(df_stress)}개의 스트레스 기록 데이터가 저장되었습니다.")
            
        else:
            st.warning("스트레스 데이터에 시간 정보('timestamp' 또는 'date') 또는 'stress' 컬럼이 포함되어 있지 않아 그래프를 그릴 수 없습니다.")
    else:
        st.info("기록된 스트레스 데이터가 없습니다. 스트레스 기록을 추가해 주세요.")

    st.write("※ 그래프 데이터는 data/stress_log.json에 저장됩니다.")


elif st.session_state.active_page == "schedule":
# =================================================================
# Page 2: 일정 관리 & 위험 예측 + Google Calendar
# =================================================================
    st.subheader("일정 관리 & 위험 예측")

    # --- 일정 등록 폼 (세션의 user_data['schedules']에 저장) ---
    with st.form("add_schedule_form", clear_on_submit=True):
        col_a, col_b, col_c = st.columns([3,2,1])
        with col_a:
            title = st.text_input("일정 제목", placeholder="예: 과제 제출")
        with col_b:
            due_date = st.date_input("마감일", value=datetime.now().date())
        with col_c:
            importance = st.selectbox("중요도", options=[1,2,3,4,5], index=2)

        submitted = st.form_submit_button("일정 등록")
        if submitted:
            new_item = {
                "제목": title if title else "제목 없음",
                "마감일": due_date.strftime("%Y-%m-%d"),
                "중요도": int(importance)
            }
            st.session_state.user_data["schedules"].append(new_item)
            st.success("일정이 등록되었습니다.")
            st.rerun()


    st.markdown("---")

    # --- 등록된 일정 목록 + 삭제 버튼 ---
    st.subheader("등록된 일정 목록")
    schedules = st.session_state.user_data.get("schedules", [])

    if not schedules:
        st.info("등록된 일정이 없습니다.")
    else:
        for idx, item in enumerate(schedules):
            c1, c2, c3 = st.columns([5,2,1])
            with c1:
                st.markdown(f"**{item.get('제목','제목 없음')}**")
                st.write(f"마감일: {item.get('마감일','-')}  |  중요도: {item.get('중요도',1)}")
            with c3:
                # 삭제 버튼 클릭 시 해당 일정 삭제
                if st.button("삭제", key=f"del_{idx}"):
                    schedules.pop(idx)
                    st.session_state.user_data["schedules"] = schedules
                    st.success("일정을 삭제했습니다.")
                    st.experimental_rerun()

    st.markdown("---")

    # --- 일정 기반 위험도 계산 및 표시 ---
    schedules_for_calc = st.session_state.user_data.get("schedules", [])
    try:
        # modules/schedule_risk.py의 함수 호출
        schedule_score = schedule_risk.calculate_schedule_risk(schedules_for_calc)
    except TypeError:
        # 모듈 함수가 인자를 받지 않는 경우를 대비한 호환성 처리
        try:
            schedule_score = schedule_risk.calculate_schedule_risk()
        except Exception:
            schedule_score = 0

    st.metric("일정 기반 위험 점수", f"{schedule_score}%")
    st.markdown("---")

    st.subheader("Google Calendar 연동")
    try:
        # modules/google_calendar.py의 함수 호출
        events = google_calendar.fetch_events() 
        if events:
            # 최근 5개 이벤트만 표시
            st.markdown("##### 최근 5개 캘린더 이벤트")
            for e in events[:5]:
                # 이벤트 시작 시간 표시 (구체적인 파싱 로직은 google_calendar 모듈에 의존)
                start_time = e.get('start', '시간 정보 없음')
                if isinstance(start_time, dict):
                     start_time = start_time.get('dateTime') or start_time.get('date', '시간 정보 없음')
                     
                st.write(f"- **{e.get('summary', '제목 없음')}**: {start_time}")
        else:
            st.info("최근 이벤트가 없거나 연동 설정이 필요합니다.")
    except Exception as e:
        # 모듈이 더미 함수일 경우 발생하는 예외 처리
        st.error(f"Google Calendar 연동 실패: {e}. (모듈 구현 필요)")


elif st.session_state.active_page == "ai":
# =================================================================
# Page 3: AI 분석 (Gemini)
# =================================================================
    st.subheader("AI 기반 심층 분석 및 개인화 개선안")
    st.write("현재 상태(기본 분석):")
    st.info(basic_text)

    st.markdown("### Gemini 요약 / 권고 생성")
    prompt_area = st.text_area("추가 컨텍스트(선택)", height=80, placeholder="추가로 알고 싶은 점이나 상황을 입력하세요.")
    
    if st.button("AI에게 요약/개선안 요청", use_container_width=True):
        st.info("AI 분석을 요청 중입니다... 잠시만 기다려 주세요.")
        
        # 스트레스 데이터를 추가하여 분석의 깊이를 더함
        stress_data = stress_graph.load_stress_data()
        stress_summary = ""
        if stress_data:
            df_s = pd.DataFrame(stress_data)
            df_s['stress'] = pd.to_numeric(df_s['stress'], errors='coerce')
            df_s = df_s.dropna(subset=['stress'])
            
            if not df_s.empty:
                avg_s = df_s['stress'].mean()
                max_s = df_s['stress'].max()
                stress_summary = f"최근 스트레스 기록 {len(stress_data)}건: 평균 {avg_s:.1f}점, 최고 {max_s:.1f}점."
            else:
                 stress_summary = "최근 스트레스 기록은 있으나 유효한 스트레스 점수가 없습니다."
        else:
            stress_summary = "최근 스트레스 기록이 없습니다."


        full_prompt = f"""
        당신은 전문적인 인생 위험 분석가입니다. 아래는 사용자의 현재 위험 브리핑과 추가 데이터입니다.

        --- 기본 위험 브리핑 ---
        {basic_text}

        --- 추가 데이터 ---
        {stress_summary}
        추가 컨텍스트: {prompt_area}
        ---

        위 정보를 바탕으로 **5가지 구체적인 개선 방안**을 한국어로, 각 항목에 실행 가능한 단계(예: 시간/횟수/구체 행동)를 포함하여 **150단어 내외**로 제시해 주세요.
        """
        ai_reply = None
        
        # Exponential Backoff 적용
        for attempt in range(3):
            try:
                # modules/gemini_client.py의 함수 호출
                ai_reply = gemini_client.ask_gemini(model, full_prompt)
                break
            except Exception as e:
                time.sleep(2 ** attempt)
                # 최종 시도 후에도 실패하면 에러 메시지 할당
                if attempt == 2:
                    ai_reply = f"Gemini 호출 실패: {e}" 

        if ai_reply and not ai_reply.startswith("Gemini 호출 실패"):
            st.markdown("#### AI 권고안")
            st.success(ai_reply)
        else:
            st.error(ai_reply)


elif st.session_state.active_page == "chatbot":
# =================================================================
# Page 4: 챗봇
# =================================================================
    st.subheader("AI 챗봇")
    chat_col1, chat_col2 = st.columns([3,1])
    
    # 챗봇 상태 초기화 버튼 추가
    with chat_col2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("대화 초기화", use_container_width=True, key="reset_chat"):
            st.session_state.chat_history = [{"role": "assistant", "text": "안녕하세요! ZeroDeadline에 오신 것을 환영합니다."}]
            st.rerun()

    with chat_col1:
        # 기존 대화 기록 출력
        for msg in st.session_state.chat_history:
            st.chat_message(msg["role"]).write(msg["text"])

        # 사용자 입력 처리
        if user_q := st.chat_input("질문을 입력하세요..."):
            st.session_state.chat_history.append({"role": "user", "text": user_q})
            # 사용자의 질문을 화면에 즉시 출력
            st.chat_message("user").write(user_q)

            full_prompt = f"""
            당신은 사용자의 위험 분석 데이터에 접근할 수 있는 친절한 상담 AI입니다.
            사용자의 기본 위험 브리핑:
            {basic_text}

            사용자 질문:
            {user_q}

            위 컨텍스트를 바탕으로 100단어 이내로 친절하고 구체적인 답변을 한국어로 작성해 주세요. 질문이 데이터와 관련이 없더라도 친절하게 응대하세요.
            """

            bot_reply = None
            # Exponential Backoff 적용
            for attempt in range(3):
                try:
                    # modules/gemini_client.py의 함수 호출
                    bot_reply = gemini_client.ask_gemini(model, full_prompt)
                    break
                except Exception as e:
                    time.sleep(2 ** attempt)
                    # 최종 시도 후에도 실패하면 에러 메시지 할당
                    if attempt == 2:
                        bot_reply = f"Gemini 호출 실패: {e}"
                        
            if bot_reply and not bot_reply.startswith("Gemini 호출 실패"):
                st.session_state.chat_history.append({"role": "assistant", "text": bot_reply})
                st.chat_message("assistant").write(bot_reply)
            else:
                error_msg = "죄송합니다. 현재 AI 응답을 받아오는데 실패했습니다. 잠시 후 다시 시도해 주세요."
                st.session_state.chat_history.append({"role": "assistant", "text": error_msg})
                st.chat_message("assistant").write(error_msg)

# =================================================================
# 메인 컨텐츠 (조건부 렌더링 끝)
# =================================================================