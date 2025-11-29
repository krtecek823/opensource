import datetime

# 상수로 정의하여 유지 보수 용이하게 변경
DEFAULT_DAYS_TO_DEADLINE = 365
MAX_IMPORTANCE = 10
BASE_RISK_WEIGHT_FOR_ZERO_DAYS = 100

def calculate_days_to_deadline(schedule):
    """
    일정의 마감일까지 남은 일수를 계산합니다.
    마감일이 지난 경우, 0을 반환합니다.
    """
    try:
        # 마감일 형식은 "%Y-%m-%d"라고 가정합니다.
        # 영어 키(deadline) 또는 한글 키(마감일)를 모두 지원
        deadline_str = schedule.get("deadline") or schedule.get("마감일")
        if not deadline_str:
            return DEFAULT_DAYS_TO_DEADLINE # 마감일이 없으면 기본값으로 위험도 낮춤

        deadline = datetime.datetime.strptime(deadline_str, "%Y-%m-%d").date()
        today = datetime.date.today()
        
        days_diff = (deadline - today).days
        
        # 디버깅 코드는 생략 또는 주석 처리
        # print(f"DEBUG: Deadline={deadline_str}, Today={today}, Days Diff={days_diff}")
        
        # 마감일이 오늘이거나 이미 지난 경우 0을 반환 (가장 위험)
        return max(0, days_diff)
        
    except Exception as e:
        # print(f"Error calculating deadline days: {e}") 
        return DEFAULT_DAYS_TO_DEADLINE # 에러 발생 시 기본값으로 위험도 낮춤

def calculate_schedule_risk(schedules):
    """
    일정 목록을 기반으로 전체 일정 위험 지수를 계산합니다.
    중요도와 마감일 근접성을 함께 고려합니다. (0-100)
    """
    if not schedules:
        # 일정이 없으면 위험도 0으로 간주
        return 0

    max_possible_risk = 0
    total_calculated_risk = 0
    
    # 1. 개별 위험 점수 합산
    for schedule in schedules:
        # 중요도 가져오기 (영어 키 또는 한글 키를 모두 지원, 없으면 최소값 1로 가정)
        try:
            importance = int(schedule.get('importance') or schedule.get('중요도', 1))
        except ValueError:
            importance = 1
            
        # 1-10 범위를 벗어나지 않도록 보정
        importance = max(1, min(MAX_IMPORTANCE, importance))
        
        # 마감일까지 남은 일수 계산
        days_to_deadline = calculate_days_to_deadline(schedule)
        
        # 근접성 가중치: 마감일이 가까울수록 높아집니다.
        # D-0일(마감) = 1.0, D-1일 = 0.5, D-7일 = 0.125
        closeness_weight = 1.0 / (days_to_deadline + 1)
        
        # 개별 일정 위험 점수 = 중요도 * 근접성 가중치 * 기본 위험 가중치
        schedule_risk = importance * closeness_weight * BASE_RISK_WEIGHT_FOR_ZERO_DAYS
        
        total_calculated_risk += schedule_risk
        
        # 최대 가능한 위험 합계: (최대 중요도 * 마감일 0일 가중치 * 기본 위험 가중치) * 일정 개수
        max_possible_risk += MAX_IMPORTANCE * 1.0 * BASE_RISK_WEIGHT_FOR_ZERO_DAYS

    # 2. 전체 위험 지수 정규화 (0-100% 스케일로 조정)
    if max_possible_risk > 0:
        overall_risk_score = (total_calculated_risk / max_possible_risk) * 100
        
        # 디버깅 코드는 생략 또는 주석 처리
        # print(f"DEBUG: Total Risk={total_calculated_risk:.2f}, Max Risk={max_possible_risk:.2f}, Score={overall_risk_score:.2f}%")
        
    else:
        overall_risk_score = 0

    # 최종 점수를 0-100% 범위 내에서 반환
    return min(100, int(round(overall_risk_score)))


# 기존 app.py에서 호출되는 메인 함수를 일정 분석 함수로 대체
def analyze_basic_risk(user_data):
    """
    user_data 내의 일정 목록을 기반으로 기본 위험 지수와 텍스트를 분석합니다.
    """
    schedules = user_data.get('schedules', [])
    
    score = calculate_schedule_risk(schedules)
    
    if score >= 80:
        text = "매우 높음: 중요한 마감일이 임박했거나 이미 지나간 일정이 많습니다. 즉시 확인이 필요합니다."
    elif score >= 50:
        text = "높음: 중요한 일정들이 곧 마감됩니다. 일정 관리에 주의가 필요합니다."
    elif score >= 20:
        text = "보통: 대부분의 일정이 안정적으로 관리되고 있습니다. 정기적인 점검을 유지하세요."
    else:
        text = "낮음: 현재 일정 위험도는 매우 낮습니다. 여유 있게 계획을 진행하세요."
        
    # 결과가 100을 초과하지 않도록 보장
    return min(100, score), text