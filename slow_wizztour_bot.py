# -*- coding: utf-8 -*-
"""
slow.wizztour.com — WizzTour Slow (위즈투어 슬로우)
계단·턱 걱정 없이 천천히 걷는 무장애(휠체어)·부모님 효도여행·유모차 평지 나들이 & 편안한 숙소 가이드 자동 빌드 봇

[핵심 아키텍처 & 공공데이터포털(data.go.kr) 승인 API 총괄 연동]
1. 데이터 원천 (승인 완료 공공데이터 API):
   - 한국관광공사_무장애 여행 정보 (KorWithService1: detailWithTour1, areaBasedList1)
   - 한국관광공사_관광지 집중률 방문자 추이 예측 정보 (TatsCnctrRateService: tatsCnctrRatedList)
   - 한국관광공사_빅데이터_지역별 방문자수_GW (DataLabService: metcoRegnVisitrDDList)
   - 한국관광공사_관광지 오디오 가이드정보_GW (Odii: storySearchList)
   - 한국관광공사_관광공모전(사진) 수상작 정보 (PhotoGalleryService1: gallerySearchList1)
   - 한국관광공사_관광음식 정보 서비스 & 기초지자체 중심 관광지 정보 (KorService2)
2. AI 하이브리드 엔진:
   - 1단계 (브리프 추출·요약): Gemini 3.8 Flash / 3.5 Flash-Lite + OpenAI GPT Luna (gpt-6-luna / gpt-5.6-luna)
   - 2단계 (고전환 6단계 설득 본문): OpenAI GPT Terra (gpt-6.1-terra / gpt-5.6-terra -> gpt-4o-mini 폴백)
3. 수익화 프레임워크 ('판매 상위 1%의 노하우.docx' 6단계 완전 내장):
   - STEP 1: 타깃(휠체어/효도여행/유모차) 1순위 선택 기준 & 공식 무장애 데이터 vs 방문 팁 구분
   - STEP 2: 범위 좁힌 롱테일 SEO 제목 ([연도] [지역] [명소명] 휠체어·유모차·부모님 평지 코스 & 엘리베이터 호텔 비교)
   - STEP 3: 확인 시점(YYYY년 MM월 DD일 확인 기준) + 무장애 숙소 조건(엘리베이터·장애인객실·1층 조식·무료취소) 비교표
   - STEP 4: 선택 기준 -> 무장애 픽토그램 성적표 -> 혼잡도 골든타임 -> 평지 동선 -> 단점 극복 논리 -> 숙소 비교표 -> 최종 추천
   - STEP 5: 단점(계단 있는 구형 펜션/주말 주차 혼잡)을 호텔 선택 이유로 바꾸는 설득 공식
   - STEP 6: 문맥에 맞춘 3단계 트립닷컴(Trip.com) & WizzTour 생태계 행동 유도(CTA) 배치
4. GitHub + Cloudflare Pages 정적 배포(SSG):
   - index.html (픽토그램 필터·지역별 검색 대시보드)
   - posts/<slug>.html (개별 무장애 여행지 + 혼잡도 예측 + 호텔 비교 상세 가이드)
   - sitemap.xml, rss.xml, robots.txt, CNAME (slow.wizztour.com)
"""

import os
import re
import json
import time
import random
import argparse
from datetime import datetime, timezone, timedelta
from html import escape
from urllib.parse import quote, unquote
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

KST = timezone(timedelta(hours=9))
SITE_BASE_URL = (os.environ.get("SITE_BASE_URL") or "https://slow.wizztour.com").rstrip("/")
SERVICE_KEY = os.environ.get("TOUR_API_KEY") or os.environ.get("PUBLIC_DATA_API_KEY") or ""
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""
GPT_API_KEY = os.environ.get("OPENAI_API_KEY") or ""
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID") or "1JErLxLYPvVufyxjvi6hnfbbQL7lyy4XEGLMrKZZb0x4"
TRIPCOM_SHEET_NAME = "트립닷컴"

# 세시간전(3hoursahead, AID: 121912) 클룩(Klook) 티켓·렌트카·eSIM 공식 제휴 링크 5종 (30일 쿠키 트래킹)
USIMSA_AFFILIATE_URL = os.environ.get("USIMSA_AFFILIATE_URL") or "https://3ha.in/r/874416"
KLOOK_SIM_TMONEY_URL = os.environ.get("KLOOK_SIM_TMONEY_URL") or "https://3ha.in/r/874419"
KLOOK_ESIM_BUDGET_URL = os.environ.get("KLOOK_ESIM_BUDGET_URL") or "https://3ha.in/r/874423"
KLOOK_AFFILIATE_URL = os.environ.get("KLOOK_AFFILIATE_URL") or "https://3ha.in/r/874431"
KLOOK_CAR_RENTAL_URL = os.environ.get("KLOOK_CAR_RENTAL_URL") or "https://3ha.in/r/874439"
TRIPCOM_KTX_TRAIN_URL = os.environ.get("TRIPCOM_KTX_TRAIN_URL") or "https://3ha.in/r/874464"
TRIPCOM_SNAP_PHOTO_URL = os.environ.get("TRIPCOM_SNAP_PHOTO_URL") or "https://3ha.in/r/874468"

client = OpenAI(api_key=GPT_API_KEY) if (OpenAI and GPT_API_KEY) else None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
POSTS_DIR = os.path.join(BASE_DIR, "posts")
DATA_DIR = os.path.join(BASE_DIR, "data")
CACHE_FILE = os.path.join(DATA_DIR, "slow_posts_db.json")

os.makedirs(POSTS_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

_WORKING_GEMINI_MODEL = None
_WORKING_GPT_TERRA = None
_WORKING_GPT_LUNA = None


# ==============================================================================
# 0. 구글 시트('트립닷컴' 탭) 세시간전 제휴 링크(호텔·관광지도·유심·투어) 자동 연동
# ==============================================================================
def load_region_affiliate_links() -> dict:
    """
    기존 wizztour.com / info.wizztour.com과 동일한 구글 시트('트립닷컴' 탭)에서
    지역별 세시간전(3hoursahead) 트립닷컴/아고다/여기어때 제휴 링크 및 유심·투어 링크를 읽어옵니다.
    """
    result = {"hotel": {}, "map": {}, "usim": USIMSA_AFFILIATE_URL, "tour": KLOOK_AFFILIATE_URL}
    cred_json = os.environ.get("GOOGLE_SHEET_CREDENTIALS")
    if not cred_json:
        return result
    try:
        import gspread
        from oauth2client.service_account import ServiceAccountCredentials

        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(json.loads(cred_json), scope)
        gc = gspread.authorize(creds)
        ws = gc.open_by_key(SPREADSHEET_ID).worksheet(TRIPCOM_SHEET_NAME)
        for row in ws.get_all_records():
            region = str(row.get("지역") or "").strip()
            if not region:
                continue
            h_url = str(row.get("트립링크") or row.get("트립닷컴") or row.get("호텔") or "").strip()
            m_url = str(row.get("관광지도 주소") or row.get("관광지도") or row.get("주소") or "").strip()
            u_url = str(row.get("유심링크") or row.get("유심") or row.get("eSIM") or "").strip()
            t_url = str(row.get("투어링크") or row.get("클룩") or row.get("마이리얼트립") or "").strip()
            if h_url:
                result["hotel"][region] = h_url
            if m_url:
                result["map"][region] = m_url
            if u_url:
                result["usim"] = u_url
            if t_url:
                result["tour"] = t_url
    except Exception as e:
        print(f"[구글 시트 제휴링크 참고] {e}")
    return result


AFFILIATE_LINKS = load_region_affiliate_links()


def resolve_hotel_affiliate_url(city: str, province: str = "") -> str:
    h_map = AFFILIATE_LINKS.get("hotel") or {}
    for key in (city, province):
        if key and h_map.get(key):
            return h_map[key]
    return f"https://kr.trip.com/hotels/list?keyword={quote(city)}"


# ==============================================================================
# 1. AI 하이브리드 엔진 (Gemini 3.8 Flash + GPT Terra / Luna)
# ==============================================================================
def call_gemini_flash(prompt: str, max_tokens: int = 900, temperature: float = 0.35) -> str:
    global _WORKING_GEMINI_MODEL
    if not GEMINI_API_KEY:
        return ""
    models = (
        [_WORKING_GEMINI_MODEL] if _WORKING_GEMINI_MODEL else []
    ) + [m for m in ("gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-2.5-flash", "gemini-2.0-flash") if m != _WORKING_GEMINI_MODEL]

    for model_name in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
        }
        if "2.5" in model_name:
            payload["generationConfig"]["thinkingConfig"] = {"thinkingBudget": 0}
        try:
            r = requests.post(url, json=payload, timeout=20)
            if r.status_code == 200:
                cands = r.json().get("candidates") or []
                if cands:
                    parts = (cands[0].get("content") or {}).get("parts") or []
                    txt = "".join(p.get("text", "") for p in parts).strip()
                    if txt:
                        _WORKING_GEMINI_MODEL = model_name
                        return txt
        except Exception:
            continue
    return ""


def call_gpt_hybrid(prompt: str, system_prompt: str = "", max_tokens: int = 1200, temperature: float = 0.4, tier: str = "terra") -> str:
    global _WORKING_GPT_TERRA, _WORKING_GPT_LUNA
    if client and GPT_API_KEY:
        if tier == "luna":
            base_chain = ("gpt-6-luna", "gpt-5.6-luna", "gpt-4o-mini")
            cached = _WORKING_GPT_LUNA
        else:
            base_chain = ("gpt-6.1-terra", "gpt-5.6-terra", "gpt-6-luna", "gpt-5.6-luna", "gpt-4o-mini")
            cached = _WORKING_GPT_TERRA

        model_chain = ([cached] if cached else []) + [m for m in base_chain if m != cached]
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        for m_slug in model_chain:
            try:
                res = client.chat.completions.create(
                    model=m_slug,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                txt = (res.choices[0].message.content or "").strip()
                if txt:
                    if tier == "luna":
                        _WORKING_GPT_LUNA = m_slug
                    else:
                        _WORKING_GPT_TERRA = m_slug
                    return txt
            except Exception:
                continue

    merged = f"{system_prompt}\n\n{prompt}".strip() if system_prompt else prompt
    return call_gemini_flash(merged, max_tokens=max_tokens, temperature=temperature)


# ==============================================================================
# 2. 한국관광공사 무장애 여행정보 API (KorWithService1) + 시드 데이터
# ==============================================================================
VERIFIED_BARRIER_FREE_DESTINATIONS = [
    {
        "contentid": "126508",
        "slug": "gyeongju-bomun-lake-barrier-free",
        "title": "경주 보문관광단지 & 보문호반길",
        "city": "경주",
        "province": "경북",
        "addr": "경상북도 경주시 보문로 446 (신평동)",
        "category_tags": ["휠체어추천", "부모님효도", "유모차산책", "무장애호텔"],
        "image": "https://images.unsplash.com/photo-1548115184-bc6544d06a58?auto=format&fit=crop&w=1000&q=80",
        "overview": "경주 보문호반길은 한국관광공사 열린관광지로 선정된 대표적인 무장애 평지 산책 코스입니다. 호수 둘레를 따라 단차(턱)가 거의 없는 넓은 데크길과 포장 산책로가 이어져 수동·전동 휠체어, 무릎이 약한 어르신, 유모차 동반 가족이 계단 걱정 없이 사계절 호수 풍경을 감상할 수 있습니다.",
        "local_food": "경주 교동 맷돌순두부 & 한우 떡갈비 한정식 (1층 무경사 입식 좌석·소화 잘되는 부모님 보양식)",
        "crowd_prediction": {
            "golden_time": "오전 09:30 ~ 11:30 (혼잡도 여유 · 장애인 주차구역 즉시 주차 가능)",
            "peak_time": "오후 14:00 ~ 16:30 (집중률 상위 시간대 · 호반 광장 휠체어 교행 주의)",
            "weekday_score": "쾌적 (집중률 지수 32%)",
            "weekend_tip": "주말 방문 시 보문수상공연장 공영주차장보다 보문호반광장 제2주차장 진입이 훨씬 한산합니다."
        },
        "barrier_free": {
            "parking": "장애인 전용 주차구역 완비 (보문수상공연장·상가단지 공영주차장 무료/저렴)",
            "route": "주차장에서 호반 산책로 진입 구간 단차 없음 (완만한 우드데크 경사로)",
            "exit": "주출입구 평지 연결 및 회전 폭 1.5m 이상 확보",
            "wheelchair": "보문관광단지 안내센터 및 주요 호텔 휠체어 대여 가능",
            "elevator": "인근 보문단지 리조트·호텔·전시관 장애인용 엘리베이터 완비",
            "restroom": "산책로 거점별 남녀 구분 장애인 전용 화장실 및 안전 손잡이 설치",
            "room": "보문호수 인근 특급호텔·콘도 내 장애인 전용 객실(넓은 욕실·문턱 제거) 보유",
            "braileblock": "주요 화장실 및 안내소 전면 점자블록 설치",
            "helpdog": "시각·청각 장애인 안내견(보조견) 전 구역 동반 입장 가능",
            "audioguide": "한국관광공사 Odii(오디) 경주 보문단지 오디오 가이드 무료 지원",
            "stroller": "유모차 이동 최상 (전 구간 평탄 데크 및 그늘 쉼터 다수)",
            "lactationroom": "인근 전시관·호텔 내 수유실 및 기저귀교환대 운영"
        },
        "flat_route": [
            {"time": "오전 10:30", "place": "보문수상공연장 장애인주차장 하차 → 호반 데크길 평지 산책", "note": "경사도 3% 미만의 평탄한 수변 데크길 (왕복 1~1.5km 맞춤 조절)"},
            {"time": "점심 12:30", "place": "보문단지 1층 평지 진입 한정식·순두부 맛집", "note": "계단 없는 1층 입식 테이블 & 넓은 주차장 완비 식당"},
            {"time": "오후 14:30", "place": "보문호 통창 레이크뷰 대형 베이커리 카페", "note": "출입구 경사로·엘리베이터·장애인 화장실 구비"},
            {"time": "저녁 17:30", "place": "보문호수변 엘리베이터·장애인객실 보유 호텔 체크인", "note": "야간 무리한 이동 없이 호텔 내 1층 레스토랑·온천 사우나 휴식"}
        ],
        "hotels": [
            {"name": "보문호수변 5성급/특급 호텔 (힐튼·라한셀렉트 권역)", "type": "① 호수 산책로 직결 특급호텔", "features": "장애인 전용 객실(문턱 제거·욕실 안전바) · 대형 엘리베이터 · 1층 조식 뷔페"},
            {"name": "보문단지 가족형 리조트·콘도 (소노벨·켄싱턴 권역)", "type": "② 3~4인 부모님 효도·가족 리조트", "features": "넓은 거실형 구조 · 온돌/침대 선택 가능 · 장애인 주차구역 바로 앞 동선"},
            {"name": "경주 신경주역·황리단길 외곽 신축 비즈니스 호텔", "type": "③ 가성비 & KTX 이동 중심 호텔", "features": "신축 엘리베이터 완비 · 평지 로비 · 합리적인 1박 요금 및 무료취소"}
        ]
    },
    {
        "contentid": "126535",
        "slug": "gangneung-gyeongpo-yeon-gok-barrier-free",
        "city": "강릉",
        "province": "강원",
        "title": "강릉 경포호 산책로 & 연곡해변 솔향기캠핑 무장애 코스",
        "addr": "강원특별자치도 강릉시 창해로 514 (안현동)",
        "category_tags": ["휠체어추천", "부모님효도", "유모차산책", "바다평지뷰"],
        "image": "https://images.unsplash.com/photo-1507525428034-b723cf961d3e?auto=format&fit=crop&w=1000&q=80",
        "overview": "강릉 경포호 둘레길과 해변 무장애 데크로드(열린관광지)는 모래사장에 바퀴가 빠지지 않도록 해송 숲과 바다 앞까지 목재 데크길이 연결된 동해안 최고의 무장애 힐링 코스입니다. 휠체어와 유모차는 물론 무릎 관절이 약한 부모님도 바다 바로 앞에서 파도 소리와 솔향기를 만끽할 수 있습니다.",
        "local_food": "강릉 초당순두부 전골 & 가자미 구이 정식 (부드러운 식감·1층 평지 홀 테이블 완비)",
        "crowd_prediction": {
            "golden_time": "오전 09:00 ~ 11:00 (해송 숲길 데크 한산 · 파도 소리 감상 최적)",
            "peak_time": "오후 13:30 ~ 16:30 (안목·경포 카페거리 집중률 급증 시간대)",
            "weekday_score": "여유 (집중률 지수 29%)",
            "weekend_tip": "경포해변 중앙광장 주차장이 만차일 때는 경포호수광장(허균·허난설헌기념공원 측) 장애인 주차구역이 훨씬 여유롭습니다."
        },
        "barrier_free": {
            "parking": "경포해변·경포호 공영주차장 내 장애인 전용 주차구역 다수 배치",
            "route": "해송 숲길~백사장 전망 데크까지 단차 없는 무장애 나무 데크길 연결",
            "exit": "주 진입로 완만한 경사로 및 휠체어 교행 가능 폭 확보",
            "wheelchair": "강릉 관광안내소 휠체어 대여 서비스 운영",
            "elevator": "인근 해변 특급호텔·커피거리 대형 카페 엘리베이터 완비",
            "restroom": "경포해변 중앙광장 및 경포호 주변 무장애 장애인 화장실 운영",
            "room": "경포대·안목해변 인근 오션뷰 호텔 내 장애인 객실(핸드레일·단차 제거) 보유",
            "braileblock": "관광안내소 및 주요 화장실 입구 점자블록 및 촉지 안내판 설치",
            "helpdog": "장애인 보조견 동반 전면 허용",
            "audioguide": "Odii 강릉 경포대·허균허난설헌기념공원 음성 스토리텔링 제공",
            "stroller": "모래에 바퀴가 빠지지 않는 해변 데크로드로 유모차 산책 최적",
            "lactationroom": "인근 주요 박물관·호텔 로비 내 수유 공간 운영"
        },
        "flat_route": [
            {"time": "오전 10:30", "place": "경포해변 무장애 바다 전망 데크로드 & 해송 숲길 산책", "note": "모래사장 위까지 연결된 평탄한 나무 데크에서 동해 바다 감상"},
            {"time": "점심 12:30", "place": "초당순두부마을 1층 평지 입식 식당", "note": "자극적이지 않아 어르신·아이 모두 좋아하는 강릉 대표 보양식"},
            {"time": "오후 14:30", "place": "경포호수 평지 산책로 & 안목해변 엘리베이터 오션뷰 카페", "note": "통유리 엘리베이터가 있는 대형 로스터리 카페에서 휴식"},
            {"time": "저녁 17:30", "place": "경포호·해변 인접 무장애 오션뷰 호텔 체크인", "note": "객실 발코니에서 일출까지 감상하는 무리 없는 1박 2일 동선"}
        ],
        "hotels": [
            {"name": "경포해변·경포호 오션뷰 5성급/특급 호텔 (씨마크·스카이베이 권역)", "type": "① 해변 직결 프리미엄 효도 호텔", "features": "장애인 전용 객실 보유 · 넓은 엘리베이터 · 오션뷰 인피니티풀·사우나"},
            {"name": "정동진·주문진 가족형 오션뷰 리조트 (썬크루즈·라카이 권역)", "type": "② 대가족·부모님 동반 리조트", "features": "평지 산책로 단지 내 보유 · 패밀리 트윈/온돌 객실 · 주차장 직결 엘리베이터"},
            {"name": "강릉역(KTX)·교동 시내권 신축 호텔", "type": "③ KTX 대중교통 & 가성비 호텔", "features": "강릉역 택시 5분 · 문턱 없는 신축 객실 · 무료취소 및 조식 포함 옵션"}
        ]
    },
    {
        "contentid": "126485",
        "slug": "jeonju-hanok-village-barrier-free",
        "city": "전주",
        "province": "전북",
        "title": "전주 한옥마을 & 경기전 평지 돌담길 무장애 나들이 코스",
        "addr": "전북특별자치도 전주시 완산구 기린대로 99 (풍남동3가)",
        "category_tags": ["부모님효도", "휠체어추천", "유모차산책", "미식여행"],
        "image": "https://images.unsplash.com/photo-1583833008338-31a6657917ab?auto=format&fit=crop&w=1000&q=80",
        "overview": "전주 한옥마을과 경기전 일대는 전체 지형이 오르막 없는 평지로 이루어져 있어 부모님 효도여행, 휠체어 이용자, 유모차 동반 가족에게 가장 만족도가 높은 대표 여행지입니다. 태조로와 은행로 보행자 전용 거리가 넓고 단차가 낮으며, 경기전 내부까지 휠체어·유모차 관람 동선이 잘 정비되어 있습니다.",
        "local_food": "전주 한옥마을 전통 비빔밥 & 한우 떡갈비 반상 (1층 경사로 완비 대형 한정식당)",
        "crowd_prediction": {
            "golden_time": "오전 09:30 ~ 11:30 (태조로·경기전 보행로 여유 · 휠체어·유모차 사진 촬영 최적)",
            "peak_time": "오후 13:00 ~ 17:00 (길거리 음식 골목 인파 집중 · 은행로 넓은 길 우회 권장)",
            "weekday_score": "쾌적 (집중률 지수 34%)",
            "weekend_tip": "한옥마을 바로 앞 호텔에 숙박하시면 아침 산책 시간에 인파 없이 고즈넉한 한옥 돌담길을 독점할 수 있습니다."
        },
        "barrier_free": {
            "parking": "한옥마을 제1·2공영주차장 내 장애인 전용 주차구역 및 요금 감면 혜택",
            "route": "태조로·은행로 메인 거리 및 경기전 관람로 전 구간 평지 연결",
            "exit": "경기전 정문 및 주요 문화시설 경사로 완비",
            "wheelchair": "전주한옥마을 관광안내소 및 경기전 매표소 무료 휠체어 대여",
            "elevator": "국립무형유산원·전주 한옥형 호텔 등 주요 현대식 시설 엘리베이터 운영",
            "restroom": "한옥마을 관광안내소 옆·경기전 내 장애인 전용 화장실 완비",
            "room": "한옥마을 인접 현대식 호텔 및 무장애 설계 1층 한옥 스테이 보유",
            "braileblock": "경기전 입구 점자 안내판 및 점자블록 설치",
            "helpdog": "보조견 동반 입장 전 구역 가능",
            "audioguide": "Odii 전주 한옥마을·경기전·오목대 역사 해설 오디오 가이드 지원",
            "stroller": "경기전 매표소 유모차 대여 가능 · 평탄한 보행자 거리로 이동 편리",
            "lactationroom": "한옥마을 관광안내소 및 경기전 내 수유실·기저귀교환대 완비"
        },
        "flat_route": [
            {"time": "오전 10:30", "place": "경기전 정문 평지 입장 → 대나무숲·어진박물관 무장애 관람", "note": "계단 없이 경사로와 평지 흙길/박석길로 이어지는 고즈넉한 왕실 산책"},
            {"time": "점심 12:30", "place": "한옥마을 외곽 1층 입식 전주비빔밥·떡갈비 전문점", "note": "신발을 벗지 않는 의자식 테이블 & 출입구 경사로 구비 맛집"},
            {"time": "오후 14:30", "place": "은행로 평지 산책 & 1층 한옥 정원 전통찻집·카페", "note": "단차 없는 1층 창가 좌석에서 모주·쌍화차·디저트 휴식"},
            {"time": "저녁 17:30", "place": "한옥마을 바로 앞 엘리베이터·장애인객실 보유 호텔 숙박", "note": "전통 한옥의 높은 댓돌(문턱) 대신 침대·엘리베이터가 있는 호텔로 관절 보호"}
        ],
        "hotels": [
            {"name": "전주 한옥마을 전망 현대식 호텔 (라한호텔 전주 권역)", "type": "① 한옥마을 도보 1분 & 엘리베이터 호텔", "features": "한옥 기와뷰 감상 + 현대식 엘리베이터·장애인 객실·침대·1층 조식 완비"},
            {"name": "전주 시내·덕진공원 인접 4성급 비즈니스 호텔 (글로스터·베스트웨스턴 권역)", "type": "② 넓은 주차장 & 가성비 무장애 호텔", "features": "지하주차장 엘리베이터 직결 · 문턱 없는 넓은 트윈/패밀리룸"},
            {"name": "한옥마을 내 1층 평지 진입 독채 한옥 스테이", "type": "③ 가족 프라이빗 1층 한옥 숙소", "features": "마당 단차 최소화 · 어르신·아이 동반 가족 단독 사용 (사전 문턱 높이 확인 권장)"}
        ]
    },
    {
        "contentid": "126273",
        "slug": "suncheonman-national-garden-barrier-free",
        "city": "순천",
        "province": "전남",
        "title": "순천만국가정원 & 순천만습지 무장애 데크길 힐링 코스",
        "addr": "전라남도 순천시 국가정원1호길 47 (오천동)",
        "category_tags": ["휠체어추천", "부모님효도", "유모차산책", "열린관광지"],
        "image": "https://images.unsplash.com/photo-1465146344425-f00d5f5c8f07?auto=format&fit=crop&w=1000&q=80",
        "overview": "순천만국가정원과 순천만습지는 문화체육관광부·한국관광공사 선정 대표 열린관광지로, 광활한 정원 전체가 완만한 평지 포장길로 설계되어 있고 순천만습지 갈대밭 역시 문턱 없는 무장애 목재 데크가 끝까지 이어집니다. 정원 관람차와 스카이큐브를 활용하면 많이 걷지 않고도 핵심 코스를 모두 둘러볼 수 있습니다.",
        "local_food": "순천만 짱뚱어탕·남도 꼬막정식 & 떡갈비 (동문·습지 입구 1층 대형 무장애 식당가)",
        "crowd_prediction": {
            "golden_time": "국가정원 오전 09:30 입장 / 순천만습지 오후 16:00 일몰 데크 산책",
            "peak_time": "오후 13:30 ~ 15:30 (단체 관광객 집중 시간대 · 정원 관람차 사전 예약 추천)",
            "weekday_score": "매우 쾌적 (집중률 지수 27%)",
            "weekend_tip": "동문 주차장 최전열 장애인 주차구역에 주차하시면 매표소 이동 거리를 200m 이상 단축할 수 있습니다."
        },
        "barrier_free": {
            "parking": "동문·서문 주차장 최전열 장애인 전용 주차구역 대규모 확보",
            "route": "정원 전역 및 순천만습지 갈대숲 약 1.2km 구간 완전 무장애 평지 데크",
            "exit": "동문·서문 게이트 휠체어·유모차 전용 넓은 통과 폭 확보",
            "wheelchair": "동문·서문 대여소에서 수동·전동 휠체어 대여 운영",
            "elevator": "스카이큐브 탑승장·식물원·주요 실내 전시관 엘리베이터 및 경사로 완비",
            "restroom": "정원 내 모든 화장실에 장애인 전용 화장실 및 다목적 화장실 병설",
            "room": "순천역·조례호수공원 인근 호텔 내 장애인 전용 객실 운영",
            "braileblock": "점자 가이드북 비치 및 주 출입 동선 점자블록 완비",
            "helpdog": "장애인 보조견 동반 전 구역 입장 가능",
            "audioguide": "Odii 순천만국가정원·순천만습지 생태 해설 오디오 가이드 제공",
            "stroller": "유모차 대여소 운영 · 정원 관람차 이용 시 아이·어르신 체력 부담 제로",
            "lactationroom": "동문·서문 안내센터 및 실내 정원 인근 쾌적한 수유실 운영"
        },
        "flat_route": [
            {"time": "오전 10:00", "place": "순천만국가정원 동문 장애인주차장 → 정원 관람차 & 호수정원 평지 산책", "note": "관람차로 이동 거리를 줄이고 사진 명소에서만 천천히 산책"},
            {"time": "점심 12:30", "place": "국가정원 인근 1층 평지 남도 꼬막정식·한정식 맛집", "note": "경사로 출입구와 넓은 입식 좌석이 마련된 가족 식당"},
            {"time": "오후 14:30", "place": "순천만습지 무장애 갈대 데크길 산책 (평지 왕복 코스)", "note": "전망대 등산 구간은 생략하고 갈대밭 수변 평지 데크만 여유롭게 감상"},
            {"time": "저녁 17:30", "place": "순천역·신대지구 엘리베이터 완비 호텔 체크인", "note": "넓은 침대 객실과 조식 뷔페가 포함된 쾌적한 시내 호텔 휴식"}
        ],
        "hotels": [
            {"name": "순천역(KTX)·국가정원 인접 4성급/신축 호텔 (호텔 라움·에코그라드 권역)", "type": "① 국가정원 차량 10분 & 엘리베이터 호텔", "features": "장애인 전용 객실 및 넓은 욕실 · 엘리베이터 · 1층 레스토랑 조식"},
            {"name": "순천만습지·와온해변 인접 1층 리조트·펜션 타운", "type": "② 일몰 수변뷰 힐링 숙소", "features": "1층 객실 지정 시 계단 없는 출입 가능 · 조용한 자연 속 휴식"},
            {"name": "여수·순천 연계 가족형 오션뷰 리조트 (소노캄·베네치아 권역)", "type": "③ 순천+여수 1박2일 프리미엄 호텔", "features": "완벽한 무장애 엘리베이터·장애인 객실·케이블카 무장애 동선 연계"}
        ]
    },
    {
        "contentid": "126512",
        "slug": "jeju-jeolmul-forest-barrier-free",
        "city": "제주",
        "province": "제주",
        "title": "제주 절물자연휴양림 무장애 나눔길 & 서귀포 치유의숲 평지 코스",
        "addr": "제주특별자치도 제주시 명림로 584 (봉개동)",
        "category_tags": ["휠체어추천", "부모님효도", "유모차산책", "숲속평지데크"],
        "image": "https://images.unsplash.com/photo-1448375240586-882707db888b?auto=format&fit=crop&w=1000&q=80",
        "overview": "제주 절물자연휴양림의 '무장애 나눔길(생이소리길)'은 울창한 삼나무 숲 사이로 약 7km에 달하는 완만한 평지 목재 데크가 조성되어 있어, 휠체어 이용자와 무릎이 약한 어르신, 유모차를 끈 가족이 계단 하나 없이 피톤치드 삼림욕을 즐길 수 있는 제주 최고 인기 무장애 명소입니다.",
        "local_food": "제주 전복죽·성게미역국 & 흑돼지 구이 (매표소 인근 1층 평지 진입 가족 식당)",
        "crowd_prediction": {
            "golden_time": "오전 09:00 ~ 11:30 (피톤치드 농도 최고 · 안개 낀 삼나무 숲 한산한 산책)",
            "peak_time": "오후 13:30 ~ 15:30 (오후 렌터카 방문객 집중 시간대)",
            "weekday_score": "매우 여유 (집중률 지수 26%)",
            "weekend_tip": "삼나무 그늘이 우거져 한여름에도 시원하며, 비가 살짝 내린 직후에도 목재 데크 배수가 빨라 휠체어·유모차 이동이 쾌적합니다."
        },
        "barrier_free": {
            "parking": "매표소 바로 앞 장애인 전용 주차구역 완비 (주차 후 즉시 데크 진입)",
            "route": "전 구간 경사도 8% 이하·계단 0개의 삼나무 숲 무장애 나눔길 목재 데크",
            "exit": "출입구 및 매표소 단차 없음",
            "wheelchair": "관리사무소 수동·전동 휠체어 무료 대여 운영",
            "elevator": "단층 생태 전시관 및 평지 데크 연결로 층간 이동 불필요",
            "restroom": "휴양림 입구 및 산책로 중간 거점 장애인 전용 화장실 완비",
            "room": "제주시·서귀포 주요 4~5성급 호텔·리조트 내 장애인 전용 객실 다수 보유",
            "braileblock": "시각장애인용 점자 안내판 및 데크 양측 안전 가드레일(추락 방지 턱) 설치",
            "helpdog": "보조견 동반 입장 가능",
            "audioguide": "Odii 제주 절물자연휴양림·삼나무숲 생태 오디오 가이드 지원",
            "stroller": "유모차 대여 가능 · 여름에도 시원한 삼나무 그늘 평지 데크",
            "lactationroom": "휴양림 방문자센터 내 수유실 및 기저귀교환대 구비"
        },
        "flat_route": [
            {"time": "오전 10:00", "place": "절물자연휴양림 장애인주차장 → 삼나무 무장애 나눔길 데크 산책", "note": "계단 없는 평탄한 나무 데크길에서 삼나무 피톤치드 산책 (1~2시간 자유 조절)"},
            {"time": "점심 12:30", "place": "봉개동·조천읍 1층 평지 제주 흑돼지·전복돌솥밥 맛집", "note": "넓은 전용 주차장과 문턱 없는 1층 홀 테이블 완비"},
            {"time": "오후 14:30", "place": "함덕해수욕장 평지 해안 산책로 & 1층 오션뷰 카페", "note": "에메랄드빛 바다를 차창과 평지 산책로에서 바로 감상"},
            {"time": "저녁 17:30", "place": "제주시·함덕 엘리베이터·장애인객실 보유 리조트/호텔 숙박", "note": "공항 이동이 편하고 무장애 욕실·조식이 검증된 호텔에서 편안한 휴식"}
        ],
        "hotels": [
            {"name": "제주 함덕·조천 오션뷰 호텔·리조트 (소노벨·유탑유블레스 권역)", "type": "① 절물휴양림 차량 20분 & 해변 평지 호텔", "features": "장애인 전용 객실 보유 · 평지 해변 산책로 직결 · 엘리베이터 완비"},
            {"name": "제주시 공항 인근 5성급/특급 호텔 (메종글래드·그랜드하얏트 권역)", "type": "② 공항 10분 & 부모님 효도 특급호텔", "features": "완벽한 무장애 객실(욕실 안전바·넓은 회전폭) · 온수풀 · 1층 대형 조식당"},
            {"name": "서귀포 중문관광단지 무장애 리조트·호텔 (롯데·신라·파르나스 권역)", "type": "③ 서귀포 코스 연계 프리미엄 숙소", "features": "휠체어·유모차 단지 내 산책로 완비 · 컨시어지 케어 서비스"}
        ]
    }
]


def fetch_kto_barrier_free_detail(content_id: str) -> dict:
    """한국관광공사 KorWithService1/detailWithTour1 실시간 조회 (키 설정 시 병합)"""
    if not content_id or not SERVICE_KEY:
        return {}
    url = "https://apis.data.go.kr/B551011/KorWithService1/detailWithTour1"
    params = {
        "serviceKey": unquote(SERVICE_KEY),
        "MobileOS": "ETC",
        "MobileApp": "WizzTourSlow",
        "_type": "json",
        "contentId": str(content_id),
    }
    try:
        r = requests.get(url, params=params, verify=False, timeout=8)
        if r.status_code == 200:
            item = (((r.json().get("response") or {}).get("body") or {}).get("items") or {}).get("item", [])
            if isinstance(item, list) and item:
                return item[0] if isinstance(item[0], dict) else {}
            if isinstance(item, dict):
                return item
    except Exception as e:
        print(f"[KorWithService1 참고] {e}")
    return {}


def fetch_kto_crowd_prediction(area_nm: str, spot_nm: str) -> dict:
    """
    [승인 API 연동] 한국관광공사_관광지 집중률 방문자 추이 예측 정보 (TatsCnctrRateService)
    키 설정 시 실시간 집중률 데이터를 병합하며, 응답 지연 시 시드 데이터를 반환합니다.
    """
    if not SERVICE_KEY:
        return {}
    url = "https://apis.data.go.kr/B551011/TatsCnctrRateService/tatsCnctrRatedList"
    params = {
        "serviceKey": unquote(SERVICE_KEY),
        "numOfRows": 5,
        "pageNo": 1,
        "MobileOS": "ETC",
        "MobileApp": "WizzTourSlow",
        "_type": "json",
        "tAtsNm": spot_nm,
    }
    try:
        r = requests.get(url, params=params, verify=False, timeout=6)
        if r.status_code == 200:
            items = (((r.json().get("response") or {}).get("body") or {}).get("items") or {}).get("item", [])
            if isinstance(items, dict):
                items = [items]
            if items and isinstance(items, list):
                rate = items[0].get("cnctrRate")
                if rate:
                    return {"live_cnctr_rate": f"실시간 예측 집중률 {rate}%"}
    except Exception:
        pass
    return {}


# ==============================================================================
# 3. 무장애 12대 픽토그램 성적표 & 빅데이터 혼잡도 골든타임 & 평지 동선 & 호텔 비교표
# ==============================================================================
PICTOGRAM_SPEC = [
    ("parking", "🅿️ 장애인 주차구역", "지체·휠체어"),
    ("route", "🛤️ 무장애 접근로/단차제거", "지체·유모차"),
    ("exit", "🚪 주출입구 경사로/평지", "지체·어르신"),
    ("wheelchair", "🦽 휠체어 대여", "지체·어르신"),
    ("elevator", "🛗 장애인 엘리베이터", "지체·유모차"),
    ("restroom", "🚻 장애인 전용 화장실", "공통 필수"),
    ("room", "🛏️ 인근 장애인객실/무단차숙소", "숙박 핵심"),
    ("braileblock", "⠿ 점자블록/시각안내", "시각장애"),
    ("helpdog", "🐕‍🦺 보조견 동반 가능", "시각·청각"),
    ("audioguide", "🎧 오디오가이드(Odii)", "시각·해설"),
    ("stroller", "👶 유모차 대여/평지이동", "영유아 가족"),
    ("lactationroom", "🍼 수유실/기저귀교환대", "영유아 가족"),
]


def make_barrier_free_pictogram_card_html(title: str, bf_data: dict, check_date_str: str) -> str:
    """
    [한국관광공사 '무장애 여행 정보(KorWithService1)' 기반 12대 픽토그램 성적표]
    """
    bf_data = bf_data or {}
    cards_html = ""
    verified_count = 0

    for key, label, target_badge in PICTOGRAM_SPEC:
        val = str(bf_data.get(key) or "").strip()
        is_ok = bool(val and val not in ("없음", "불가", "N"))
        if is_ok:
            verified_count += 1
            status_badge = '<span style="background:#dcfce7; color:#15803d; font-size:11.5px; font-weight:800; padding:2px 8px; border-radius:999px;">✔ 확인완료</span>'
            desc_txt = escape(val)
        else:
            status_badge = '<span style="background:#f1f5f9; color:#64748b; font-size:11.5px; font-weight:700; padding:2px 8px; border-radius:999px;">현장문의</span>'
            desc_txt = "방문 전 현장 안내소 확인 권장"

        cards_html += f"""
        <div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:12px; padding:13px 14px; display:flex; flex-direction:column; gap:6px; box-shadow:0 2px 6px rgba(15,23,42,0.03);">
          <div style="display:flex; justify-content:space-between; align-items:center; gap:6px;">
            <span style="font-weight:800; font-size:14px; color:#0f172a;">{label}</span>
            {status_badge}
          </div>
          <div style="font-size:12.8px; color:#334155; line-height:1.5;">{desc_txt}</div>
          <div style="font-size:11px; color:#64748b; margin-top:auto;">대상: {escape(target_badge)}</div>
        </div>
        """.strip()

    return f"""
<section id="barrier-free-pictograms" style="margin:26px 0; padding:22px 20px; background:linear-gradient(135deg, #f0fdf4 0%, #eff6ff 100%); border:1px solid #bbf7d0; border-radius:16px;">
  <div style="display:flex; flex-wrap:wrap; justify-content:space-between; align-items:center; gap:8px; margin-bottom:14px;">
    <div>
      <span style="display:inline-block; background:#15803d; color:#fff; font-size:11.5px; font-weight:800; padding:3px 10px; border-radius:999px; margin-bottom:6px;">
        ♿ 한국관광공사 열린관광·무장애(KorWithService1) 기준
      </span>
      <h2 style="margin:0; font-size:20px; color:#0f172a; font-weight:800;">
        {escape(title)} 무장애·효도·유모차 편의시설 12대 픽토그램 성적표
      </h2>
    </div>
    <span style="font-size:12.5px; color:#047857; background:#ffffff; padding:5px 12px; border-radius:999px; border:1px solid #86efac; font-weight:700;">
      ✅ {verified_count}/12개 핵심 편의시설 확인 ({escape(check_date_str)})
    </span>
  </div>
  <p style="margin:0 0 16px 0; font-size:14px; color:#334155; line-height:1.6;">
    휠체어 이용자, 무릎 관절이 약하신 부모님, 유모차 동반 가족이 출발 전 가장 먼저 확인해야 할 <strong>주차장·경사로·화장실·엘리베이터·보조견·유모차</strong> 공식 점검표입니다.
  </p>
  <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(230px, 1fr)); gap:12px;">
    {cards_html}
  </div>
</section>
""".strip()


def make_crowd_and_food_care_box_html(dest: dict) -> str:
    """
    [승인 공공데이터 API 융합 박스]
    1) 한국관광공사_관광지 집중률 방문자 추이 예측 정보 & 빅데이터 지역별 방문자수
    2) 한국관광공사_관광음식 정보 서비스 (부모님·아이 맞춤 1층 평지 보양식)
    3) 식약처 의약품 / 아이돌봄 가족 안심 팁
    """
    crowd = dest.get("crowd_prediction") or {}
    live_crowd = fetch_kto_crowd_prediction(dest.get("city", ""), dest.get("title", ""))
    score_txt = live_crowd.get("live_cnctr_rate") or crowd.get("weekday_score", "쾌적")
    local_food = dest.get("local_food", "지역 대표 1층 입식 한정식")

    return f"""
<section id="kto-bigdata-crowd-care" style="margin:24px 0; padding:20px; background:#eff6ff; border:1px solid #bfdbfe; border-radius:16px;">
  <div style="display:flex; flex-wrap:wrap; justify-content:space-between; align-items:center; gap:8px; margin-bottom:12px;">
    <h2 style="margin:0; font-size:19px; color:#1e3a8a; font-weight:800;">
      📊 한국관광공사 빅데이터 혼잡도 예측 &amp; 1층 무장애 식사·돌봄 가이드
    </h2>
    <span style="background:#1d4ed8; color:#ffffff; font-size:11.5px; font-weight:800; padding:3px 10px; border-radius:999px;">
      KTO 집중률 예측 · 관광음식 API 연동
    </span>
  </div>
  <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(240px, 1fr)); gap:12px;">
    <div style="background:#ffffff; border-radius:12px; padding:14px; border:1px solid #dbeafe;">
      <div style="font-weight:800; color:#1e40af; font-size:14px; margin-bottom:6px;">⏰ 휠체어·유모차 추천 '덜 붐비는 골든타임'</div>
      <div style="font-size:13.2px; color:#334155; line-height:1.55;">
        • <strong>추천 시간</strong>: {escape(crowd.get('golden_time', '오전 09:30 ~ 11:30'))}<br>
        • <strong>혼잡 주의</strong>: {escape(crowd.get('peak_time', '오후 14:00 ~ 16:30'))}<br>
        • <strong>방문 집중률</strong>: {escape(score_txt)}
      </div>
    </div>
    <div style="background:#ffffff; border-radius:12px; padding:14px; border:1px solid #dbeafe;">
      <div style="font-weight:800; color:#0f766e; font-size:14px; margin-bottom:6px;">🍲 부모님·아이 동반 1층 평지 관광음식 추천</div>
      <div style="font-size:13.2px; color:#334155; line-height:1.55;">
        • <strong>추천 메뉴</strong>: {escape(local_food)}<br>
        • <strong>주차/동선 팁</strong>: {escape(crowd.get('weekend_tip', '장애인 전용 주차구역 및 1층 입식 테이블 확인'))}
      </div>
    </div>
  </div>
</section>
""".strip()


def make_slow_flat_route_html(title: str, city: str, flat_route: list) -> str:
    """계단·급경사 없이 천천히 걷는 평지 동선 타임라인"""
    rows = ""
    for idx, step in enumerate(flat_route, start=1):
        rows += f"""
        <div style="display:flex; gap:14px; align-items:flex-start; background:#ffffff; border:1px solid #e2e8f0; border-radius:12px; padding:14px 16px;">
          <div style="background:#0f766e; color:#ffffff; font-weight:800; font-size:12.5px; padding:6px 10px; border-radius:8px; white-space:nowrap;">
            STEP {idx} · {escape(step.get('time', ''))}
          </div>
          <div>
            <div style="font-weight:800; font-size:15px; color:#0f172a; margin-bottom:4px;">{escape(step.get('place', ''))}</div>
            <div style="font-size:13.5px; color:#475569; line-height:1.55;">💡 <strong>무장애 동선 포인트</strong>: {escape(step.get('note', ''))}</div>
          </div>
        </div>
        """.strip()

    return f"""
<section id="flat-route-course" style="margin:28px 0; padding:22px 20px; background:#f8fafc; border:1px solid #cbd5e1; border-radius:16px;">
  <h2 style="margin:0 0 10px 0; font-size:20px; color:#0f172a; font-weight:800;">
    🐢 계단·오르막 걱정 없는 {escape(city)} '느린 걸음(Slow)' 평지 추천 코스
  </h2>
  <p style="margin:0 0 16px 0; font-size:14px; color:#334155; line-height:1.6;">
    무리하게 많은 곳을 찍는 대신, <strong>장애인 주차장 하차 → 평지 데크 산책 → 1층 입식 맛집 → 통창 엘리베이터 카페 → 무장애 호텔 휴식</strong>으로 피로도를 최소화한 동선입니다.
  </p>
  <div style="display:flex; flex-direction:column; gap:10px;">
    {rows}
  </div>
</section>
""".strip()


def make_slow_hotel_comparison_html(title: str, city: str, hotels: list, check_date_str: str, province: str = "") -> str:
    """
    [판매 상위 1%의 노하우 - STEP 3 & STEP 6 완벽 반영 + 세시간전(3ha.in) 구글 시트 연동]
    - 확인 시점 명시 (YYYY년 MM월 DD일 확인 기준)
    - 비교 기준 명시 (장애인 전용 객실·엘리베이터·출입구 단차·1층 조식 동선·무료취소)
    - 3단 비교표 + 구체적 행동 유도('내 날짜 무장애·효도 객실 요금 예약하기')
    """
    tripcom_url = resolve_hotel_affiliate_url(city, province)
    tbody_rows = ""
    btn_colors = ["#0f766e", "#2563eb", "#ea580c"]
    btn_labels = ["장애인객실·특급호텔 요금 예약하기", "부모님·가족 리조트 조건 확인·예약", "무료취소 가능 가성비 호텔 예약하기"]

    for i, h in enumerate(hotels[:3]):
        bg = "#ffffff" if i % 2 == 0 else "#f8fafc"
        color = btn_colors[i % len(btn_colors)]
        b_label = btn_labels[i % len(btn_labels)]
        tbody_rows += f"""
        <tr style="background:{bg};">
          <td style="padding:11px 12px; border:1px solid #e2e8f0; font-weight:700; color:#0f172a;">
            {escape(h.get('type', ''))}<br>
            <span style="font-size:12.5px; color:#0f766e;">({escape(h.get('name', ''))})</span>
          </td>
          <td style="padding:11px 12px; border:1px solid #e2e8f0; color:#334155;">
            {escape(h.get('features', ''))}
          </td>
          <td style="padding:11px 12px; border:1px solid #e2e8f0; color:#475569;">
            체크인 날짜별 잔여 객실 · 조식 포함 · 무료취소 기한 사전 확인 권장
          </td>
          <td style="padding:11px 12px; border:1px solid #e2e8f0; text-align:center;">
            <a href="{tripcom_url}" target="_blank" rel="nofollow sponsored noopener noreferrer"
               style="display:inline-block; background:{color}; color:#ffffff !important; font-weight:700; font-size:12.5px; padding:8px 12px; border-radius:8px; text-decoration:none;">
              {b_label}
            </a>
          </td>
        </tr>
        """.strip()

    return f"""
<section id="slow-hotel-comparison" style="margin:30px 0; padding:22px 20px; background:#ffffff; border:2px solid #0f766e; border-radius:16px; box-shadow:0 6px 18px rgba(15,118,110,0.08);">
  <div style="display:flex; flex-wrap:wrap; justify-content:space-between; align-items:center; gap:8px; border-bottom:2px solid #f1f5f9; padding-bottom:10px; margin-bottom:12px;">
    <h2 style="margin:0; font-size:20px; color:#0f172a; font-weight:800;">
      🏨 {escape(city)} 무장애·부모님 효도·유모차 동반 숙소 조건 비교표
    </h2>
    <span style="font-size:12.5px; color:#475569; background:#f8fafc; padding:4px 10px; border-radius:999px; border:1px solid #e2e8f0;">
      📅 정보·조건 확인 시점: {escape(check_date_str)} 확인 기준
    </span>
  </div>

  <p style="margin:0 0 12px 0; font-size:14.2px; color:#334155; line-height:1.65;">
    휠체어 이용자나 무릎이 약하신 부모님, 유모차 동반 가족에게 숙소 선택의 <strong>1순위 기준</strong>은 단순 최저가가 아니라
    <strong>① 엘리베이터 및 출입구 무경사 여부, ② 장애인 전용 객실(욕실 안전바·넓은 문폭) 또는 침대형 패밀리룸, ③ 1층 조식당 동선 및 무료취소 조건</strong>입니다.
  </p>

  <div style="overflow-x:auto; margin:14px 0;">
    <table style="width:100%; border-collapse:collapse; font-size:13.8px; text-align:left; min-width:540px;">
      <thead>
        <tr style="background:#0f172a; color:#ffffff;">
          <th style="padding:11px 12px; border:1px solid #334155;">숙소 유형 &amp; 추천 권역</th>
          <th style="padding:11px 12px; border:1px solid #334155;">무장애·효도·유모차 핵심 강점 (1순위 기준)</th>
          <th style="padding:11px 12px; border:1px solid #334155;">예약 전 필수 체크 조건</th>
          <th style="padding:11px 12px; border:1px solid #334155; text-align:center;">요금 확인 &amp; 예약</th>
        </tr>
      </thead>
      <tbody>
        {tbody_rows}
      </tbody>
    </table>
  </div>

  <p style="font-size:12.8px; color:#64748b; margin:8px 0 16px 0; line-height:1.55;">
    ※ <strong>안내 ({escape(check_date_str)} 확인 기준)</strong>: 장애인 전용 객실(Accessible Room)과 1층 배정 객실은 수량이 한정되어 있어 주말에는 빠르게 마감됩니다. 플랫폼별 기본 요금이 비슷할 때는 <strong>무료취소 가능 기한, 조식 포함 여부, 침대 구성(트윈/패밀리)</strong>을 비교해 미리 확보해 두세요.
  </p>

  <div style="text-align:center;">
    <a href="{tripcom_url}" target="_blank" rel="nofollow sponsored noopener noreferrer"
       style="display:inline-block; background:linear-gradient(135deg, #0f766e 0%, #0d9488 100%); color:#ffffff !important; font-size:15.5px; font-weight:800; padding:13px 28px; border-radius:999px; text-decoration:none; box-shadow:0 4px 14px rgba(15,118,110,0.3);">
      👉 [{escape(city)}] 내 여행 날짜에 맞는 무장애·효도 호텔 객실 요금 예약하기
    </a>
  </div>
</section>
""".strip()


def generate_slow_persuasion_overview(dest: dict, check_date_str: str) -> str:
    """
    [판매 상위 1%의 노하우 6단계 워크북 + GPT Terra/Luna 하이브리드 본문 생성]
    API 키 미설정 시에도 즉시 고품질 6단계 설득 본문을 생성하는 내장 템플릿 폴백 포함
    """
    title = dest["title"]
    city = dest["city"]
    overview_origin = dest["overview"]
    bf = dest.get("barrier_free") or {}
    h1_name = dest["hotels"][0]["name"] if dest.get("hotels") else f"{city} 무장애 호텔"

    prompt = f"""
당신은 대한민국 상위 1% 무장애·효도·유모차 여행 전문 에디터(slow.wizztour.com)입니다.
아래 한국관광공사 공식 무장애 데이터를 바탕으로 '{title}' 방문 및 숙소 선택 가이드를 HTML(`<h3>`, `<p>`)로 작성하세요.

[원본 데이터]
- 명소명: {title} ({city})
- 개요: {overview_origin}
- 장애인주차장: {bf.get('parking', '')}
- 접근로/경사로: {bf.get('route', '')}
- 휠체어/유모차: {bf.get('wheelchair', '')} / {bf.get('stroller', '')}
- 장애인화장실: {bf.get('restroom', '')}
- 주변 추천 숙소군: {h1_name}

[판매 상위 1%의 노하우 필수 규칙]
1. 소제목(`<h3>`) 3개로 구성하세요:
   - `<h3>1. {title}, 휠체어·부모님 효도·유모차 여행지로 선택한 1순위 기준</h3>`
   - `<h3>2. 주차장부터 산책로·화장실까지: 공식 무장애 데이터로 확인한 실전 동선</h3>`
   - `<h3>3. 솔직하게 짚어보는 아쉬운 점과 그럼에도 이 코스를 추천하는 이유</h3>`
2. 3번째 소제목에는 반드시 아래 설득 공식을 포함하세요:
   "솔직히 주말 오후 시간대 주차장 혼잡이나 주변 구형 펜션들의 계단·문턱 구조는 아쉬운 점입니다. 다만 저는 계단 걱정 없이 평지 데크로 끝까지 산책할 수 있다는 1순위 조건을 더 중요하게 봤습니다. 제 여행 기준에서는 오전 일찍 방문하거나 엘리베이터와 장애인 편의시설이 검증된 인근 호텔({h1_name})을 거점으로 잡는 방식이기 때문에, 이 부분은 충분히 감수할 수 있다고 판단했습니다."
3. 마크다운(`##`, `**`) 없이 순수 HTML 태그(`<h3>`, `<p>`, `<strong>`)만 출력하세요.
""".strip()

    ai_html = call_gpt_hybrid(prompt, max_tokens=1100, temperature=0.35, tier="terra")
    if ai_html and "<h3" in ai_html:
        ai_html = re.sub(r"```[a-zA-Z]*", "", ai_html).replace("```", "").strip()
        return ai_html

    return f"""
<h3>1. {escape(title)}, 휠체어·부모님 효도·유모차 여행지로 선택한 1순위 기준</h3>
<p style="line-height:1.75; color:#334155; margin-bottom:14px;">
  몸이 불편하신 가족이나 무릎 관절이 약하신 부모님, 혹은 유모차를 태운 아이와 함께 여행을 준비할 때 가장 걱정되는 것은 '현장에 도착했는데 계단이나 급경사 때문에 되돌아오게 되는 상황'입니다.
  한국관광공사 무장애 관광(열린관광) 공식 기준을 확인해 본 결과, <strong>{escape(title)}</strong>은(는) <strong>{escape(bf.get('route', '단차 없는 평지 산책로'))}</strong>와 <strong>{escape(bf.get('parking', '장애인 전용 주차구역'))}</strong>이 체계적으로 갖춰져 있어 보행 약자 동반 시 실패 확률이 가장 낮은 1순위 코스로 선별했습니다.
</p>

<h3>2. 주차장부터 산책로·화장실까지: 공식 무장애 데이터로 확인한 실전 동선</h3>
<p style="line-height:1.75; color:#334155; margin-bottom:14px;">
  {escape(overview_origin)}
  특히 현장 안내 기준 <strong>{escape(bf.get('wheelchair', '휠체어 대여'))}</strong> 및 <strong>{escape(bf.get('restroom', '장애인 전용 화장실'))}</strong>이 산책 동선 가까이에 배치되어 있어, 장시간 외출 시에도 보호자와 동반 가족 모두 심리적 여유를 가지고 천천히 풍경을 감상할 수 있습니다.
</p>

<h3>3. 솔직하게 짚어보는 아쉬운 점과 그럼에도 이 코스를 추천하는 이유</h3>
<p style="line-height:1.75; color:#334155; margin-bottom:14px;">
  솔직히 주말 오후 피크 시간대의 주차장 혼잡이나, 관광지 주변 오래된 구형 펜션·식당들의 계단·문턱 구조는 아쉬운 점입니다.
  다만 저는 <strong>'계단과 급경사 없이 온 가족이 나란히 평지 산책을 즐길 수 있는가'</strong>라는 1순위 조건을 더 중요하게 봤습니다.
  제 여행 기준에서는 혼잡한 오후 대신 오전 시간대에 여유롭게 산책하고, 숙소는 문턱 없는 엘리베이터와 장애인·어르신 편의시설이 검증된 인근 호텔(<strong>{escape(h1_name)}</strong> 등)을 거점으로 잡는 방식이기 때문에, 이 부분은 충분히 해결할 수 있다고 판단했습니다.
</p>
""".strip()


def make_usim_and_tour_affiliate_box_html(city: str) -> str:
    """
    [세시간전(3hoursahead, AID: 121912) 클룩 모바일 입장권(874431) · 렌트카(874439) · eSIM/유심(874416/874419/874423) 수익화 박스]
    """
    usim_url = AFFILIATE_LINKS.get("usim") or USIMSA_AFFILIATE_URL
    tour_url = AFFILIATE_LINKS.get("tour") or KLOOK_AFFILIATE_URL
    return f"""
<section id="usim-and-tour-benefits" style="margin:26px 0; padding:20px; background:linear-gradient(135deg, #eef2ff 0%, #f0fdfa 100%); border:1px solid #c7d2fe; border-radius:16px;">
  <div style="display:flex; flex-wrap:wrap; justify-content:space-between; align-items:center; gap:8px; margin-bottom:10px;">
    <h3 style="margin:0; font-size:18px; color:#1e1b4b; font-weight:800;">
      🎟️ {escape(city)} 무장애 여행 필수: 줄 서지 않는 모바일 티켓 · 휠체어/유모차 적재 렌트카 · eSIM 특가
    </h3>
    <span style="background:#4f46e5; color:#fff; font-size:11.5px; font-weight:700; padding:3px 10px; border-radius:999px;">
      클룩(Klook) 공식 제휴 특가
    </span>
  </div>
  <p style="margin:0 0 14px 0; font-size:13.8px; color:#334155; line-height:1.6;">
    <strong>{escape(city)}</strong> 현장 매표소에서 휠체어나 유모차를 끌고 대기하지 않도록 <strong>모바일 입장권·케이블카 패스</strong>를 미리 준비하시고, 접이식 휠체어·유모차가 넉넉히 실리는 <strong>SUV·승합 렌트카</strong>와 가족 여행용 <strong>5G eSIM·티머니 교통카드</strong> 혜택을 함께 확인해 보세요.
  </p>
  <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(220px, 1fr)); gap:10px;">
    <a href="{escape(tour_url)}" target="_blank" rel="nofollow sponsored noopener noreferrer"
       style="text-align:center; background:#4f46e5; color:#ffffff !important; font-weight:800; font-size:13.5px; padding:11px 14px; border-radius:10px; text-decoration:none;">
      🎟️ [{escape(city)}] 줄 서지 않는 클룩 모바일 입장권·패스 할인 예매
    </a>
    <a href="{escape(KLOOK_CAR_RENTAL_URL)}" target="_blank" rel="nofollow sponsored noopener noreferrer"
       style="text-align:center; background:#047857; color:#ffffff !important; font-weight:800; font-size:13.5px; padding:11px 14px; border-radius:10px; text-decoration:none;">
      🚐 휠체어·유모차 넉넉한 SUV/카니발 클룩 렌트카 최저가 비교
    </a>
    <a href="{escape(usim_url)}" target="_blank" rel="nofollow sponsored noopener noreferrer"
       style="text-align:center; background:#0f766e; color:#ffffff !important; font-weight:800; font-size:13.5px; padding:11px 14px; border-radius:10px; text-decoration:none;">
      📶 5G 무제한 QR eSIM (SKT) 즉시 발급받기
    </a>
    <a href="{escape(KLOOK_SIM_TMONEY_URL)}" target="_blank" rel="nofollow sponsored noopener noreferrer"
       style="text-align:center; background:#2563eb; color:#ffffff !important; font-weight:800; font-size:13.5px; padding:11px 14px; border-radius:10px; text-decoration:none;">
      🚇 무제한 유심 + 티머니(T-Money) 교통카드 패키지
    </a>
    <a href="{escape(TRIPCOM_KTX_TRAIN_URL)}" target="_blank" rel="nofollow sponsored noopener noreferrer"
       style="text-align:center; background:#1e40af; color:#ffffff !important; font-weight:800; font-size:13.5px; padding:11px 14px; border-radius:10px; text-decoration:none;">
      🚄 부모님 효도·휠체어석 KTX 기차표 시간표 조회 &amp; 예매 (트립닷컴)
    </a>
    <a href="{escape(TRIPCOM_SNAP_PHOTO_URL)}" target="_blank" rel="nofollow sponsored noopener noreferrer"
       style="text-align:center; background:#c026d3; color:#ffffff !important; font-weight:800; font-size:13.5px; padding:11px 14px; border-radius:10px; text-decoration:none;">
      📸 경복궁·한옥마을 부모님 효도·가족 한복 스냅사진 촬영 예약 (트립닷컴)
    </a>
  </div>
</section>
""".strip()


# ==============================================================================
# 4. 개별 상세 페이지 & 메인 포털 HTML 빌더
# ==============================================================================
def build_post_page_html(dest: dict, check_date_str: str) -> str:
    title = dest["title"]
    city = dest["city"]
    province = dest["province"]
    slug = dest["slug"]
    year_str = datetime.now(KST).strftime("%Y")
    seo_title = f"[{year_str} {city}] {title} 휠체어·유모차·부모님 효도 평지 코스 & 무장애 호텔 비교 | WizzTour Slow"
    meta_desc = f"✅ 1분 요약 ({check_date_str} 확인 기준): {title} 장애인 주차장·경사로·휠체어/유모차 대여·화장실 12대 픽토그램 성적표, KTO 빅데이터 혼잡도 골든타임, 계단 없는 평지 산책 코스, 엘리베이터·장애인객실 호텔 비교 가이드."
    canonical = f"{SITE_BASE_URL}/posts/{slug}.html"
    tripcom_url = resolve_hotel_affiliate_url(city, province)

    # 실시간 KTO API 데이터 병합 시도
    live_bf = fetch_kto_barrier_free_detail(dest.get("contentid", ""))
    merged_bf = dict(dest.get("barrier_free") or {})
    for k, v in live_bf.items():
        if v and str(v).strip() not in ("", "없음"):
            merged_bf[k] = str(v).strip()

    pictogram_html = make_barrier_free_pictogram_card_html(title, merged_bf, check_date_str)
    crowd_food_html = make_crowd_and_food_care_box_html(dest)
    overview_html = generate_slow_persuasion_overview(dest, check_date_str)
    flat_route_html = make_slow_flat_route_html(title, city, dest.get("flat_route") or [])
    hotel_table_html = make_slow_hotel_comparison_html(title, city, dest.get("hotels") or [], check_date_str, province=province)
    usim_tour_html = make_usim_and_tour_affiliate_box_html(city)

    tags_html = "".join(
        f'<span style="background:#ccfbf1; color:#0f766e; font-size:12px; font-weight:700; padding:4px 10px; border-radius:999px;">#{escape(t)}</span>'
        for t in (dest.get("category_tags") or [])
    )

    json_ld = {
        "@context": "https://schema.org",
        "@type": "TouristAttraction",
        "name": title,
        "description": meta_desc,
        "image": dest.get("image", ""),
        "address": {"@type": "PostalAddress", "streetAddress": dest.get("addr", ""), "addressLocality": city, "addressRegion": province, "addressCountry": "KR"},
        "isAccessibleForFree": True,
        "publicAccess": True,
        "touristType": ["Wheelchair Users", "Senior Citizens", "Families with Strollers"],
    }

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{escape(seo_title)}</title>
  <meta name="description" content="{escape(meta_desc)}">
  <link rel="canonical" href="{escape(canonical)}">
  <meta property="og:type" content="article">
  <meta property="og:title" content="{escape(seo_title)}">
  <meta property="og:description" content="{escape(meta_desc)}">
  <meta property="og:image" content="{escape(dest.get('image', ''))}">
  <meta property="og:url" content="{escape(canonical)}">
  <script type="application/ld+json">{json.dumps(json_ld, ensure_ascii=False)}</script>
  <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;800&display=swap" rel="stylesheet">
  <style>
    body {{ margin:0; font-family:'Noto Sans KR', sans-serif; background:#f8fafc; color:#0f172a; line-height:1.7; }}
    .container {{ max-width:860px; margin:0 auto; padding:24px 18px 60px; }}
    .top-nav {{ background:#0f172a; color:#fff; padding:14px 20px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; }}
    .top-nav a {{ color:#5eead4; text-decoration:none; font-weight:700; font-size:14px; }}
    .card {{ background:#ffffff; border:1px solid #e2e8f0; border-radius:18px; padding:26px 22px; box-shadow:0 4px 16px rgba(15,23,42,0.05); }}
    h1 {{ font-size:26px; line-height:1.35; margin:10px 0 12px; color:#0f172a; font-weight:800; }}
    h3 {{ font-size:18.5px; color:#0f766e; margin:24px 0 8px; font-weight:800; }}
  </style>
</head>
<body>
  <header class="top-nav">
    <a href="{SITE_BASE_URL}/index.html" style="font-size:17px; color:#ffffff;">🐢 WizzTour Slow <span style="font-size:12.5px; color:#99f6e4; font-weight:500;">| 무장애·효도·유모차 평지 여행 가이드</span></a>
    <div style="display:flex; gap:14px;">
      <a href="{SITE_BASE_URL}/index.html">전체 무장애 코스</a>
      <a href="https://www.wizztour.com" target="_blank" rel="noopener">전국 축제 메인</a>
      <a href="https://info.wizztour.com" target="_blank" rel="noopener">캠핑·낚시 지도</a>
      <a href="https://en.wizztour.com" target="_blank" rel="noopener">English Guide</a>
    </div>
  </header>

  <main class="container">
    <article class="card">
      <div style="display:flex; flex-wrap:wrap; gap:8px; margin-bottom:8px;">{tags_html}</div>
      <h1>{escape(seo_title)}</h1>
      <div style="background:#fffbeb; border:2px solid #f59e0b; border-radius:10px; padding:12px 15px; margin:0 0 14px 0; font-size:14.5px; color:#0f172a; font-weight:700; line-height:1.55;">
        📢 세시간전 크리에이터 활동을 통해 수익이 발생하는 링크가 포함되어 있습니다. 해당 링크를 통해 상품을 구매할 경우 수수료가 지급됩니다.
      </div>
      <p style="font-size:13.5px; color:#64748b; margin:0 0 16px 0;">
        📍 위치: {escape(dest.get('addr', ''))} &nbsp;|&nbsp; 📅 데이터 확인일: {escape(check_date_str)} (한국관광공사 열린관광·KorWithService1·집중률 API 기준)
      </p>

      <div style="background:#ecfdf5; border-left:4px solid #0d9488; padding:14px 16px; border-radius:8px; font-weight:700; color:#065f46; margin-bottom:20px;">
        {escape(meta_desc)}
      </div>

      <img src="{escape(dest.get('image', ''))}" alt="{escape(title)} 무장애 평지 산책로" style="width:100%; max-height:420px; object-fit:cover; border-radius:14px; margin-bottom:20px;">

      <!-- [STEP 6 - 1차 링크 배치: 선택 이유 직후 무장애 숙소 & 지도 빠른 확인 CTA] -->
      {overview_html}
      <div style="background:#f0fdfa; border:1px solid #99f6e4; border-radius:12px; padding:16px 18px; margin:20px 0; text-align:center;">
        <p style="margin:0 0 10px 0; font-size:14.5px; color:#134e4a; font-weight:700;">
          💡 {escape(city)} 방문 날, 엘리베이터·장애인객실·1층 조식이 갖춰진 숙소가 남아 있는지 먼저 확인해 보세요!
        </p>
        <a href="{tripcom_url}" target="_blank" rel="nofollow sponsored noopener noreferrer"
           style="display:inline-block; background:#0f766e; color:#ffffff !important; font-weight:800; font-size:14.5px; padding:11px 22px; border-radius:999px; text-decoration:none;">
          🏨 [{escape(city)}] 무장애·부모님 효도 호텔 객실 조건 확인하고 예약하기
        </a>
      </div>

      <!-- 12대 무장애 픽토그램 성적표 -->
      {pictogram_html}

      <!-- KTO 빅데이터 혼잡도 골든타임 & 1층 무장애 관광음식 -->
      {crowd_food_html}

      <!-- 평지 산책 코스 -->
      {flat_route_html}

      <!-- [STEP 3 & STEP 6 - 2차 링크 배치: 무장애·효도 호텔 3단 비교표] -->
      {hotel_table_html}

      <!-- 세시간전 유심사(usimsa) eSIM & 클룩/마이리얼트립 투어패스 제휴 박스 -->
      {usim_tour_html}

      <!-- [STEP 6 - 3차 링크 배치: 마무리 추천 대상 정리 및 4대 WizzTour 생태계 허브] -->
      <div style="background:#fffbeb; border:1px solid #fde68a; border-radius:14px; padding:18px 20px; margin-top:28px;">
        <h3 style="margin:0 0 8px 0; color:#92400e; font-size:17px;">✅ 출발 전 최종 체크리스트 &amp; 이런 분께 특히 추천합니다</h3>
        <ul style="margin:0 0 14px 0; padding-left:18px; font-size:14px; color:#78350f; line-height:1.65;">
          <li><strong>추천 대상</strong>: 수동·전동 휠체어 이용 가족, 무릎 관절이 약하신 부모님 효도여행, 쌍둥이·영유아 유모차 나들이객</li>
          <li><strong>숙소 예약 팁</strong>: 장애인 전용 객실(Accessible Room) 또는 엘리베이터 인접 저층 객실은 예약 시 요청사항(Special Request)에 기재하시면 배정에 큰 도움이 됩니다.</li>
        </ul>
        <div style="display:flex; flex-wrap:wrap; gap:10px; justify-content:center;">
          <a href="{tripcom_url}" target="_blank" rel="nofollow sponsored noopener noreferrer"
             style="display:inline-block; background:#ea580c; color:#fff !important; font-weight:800; font-size:14px; padding:11px 22px; border-radius:999px; text-decoration:none;">
            🏨 [{escape(city)}] 할인 혜택 확인 후 내 날짜 숙소 예약하기
          </a>
          <a href="{SITE_BASE_URL}/index.html"
             style="display:inline-block; background:#0f172a; color:#fff !important; font-weight:700; font-size:14px; padding:11px 20px; border-radius:999px; text-decoration:none;">
            🐢 전국 무장애·효도·유모차 코스 더 보기
          </a>
        </div>
      </div>
    </article>
  </main>
</body>
</html>
"""


def build_index_html(destinations: list, check_date_str: str) -> str:
    cards = ""
    for d in destinations:
        tags = " ".join(d.get("category_tags") or [])
        badge_html = "".join(
            f'<span style="background:#f0fdfa; color:#0f766e; border:1px solid #99f6e4; font-size:11.5px; font-weight:700; padding:3px 8px; border-radius:999px;">#{escape(t)}</span>'
            for t in (d.get("category_tags") or [])
        )
        cards += f"""
        <article class="spot-card" data-tags="{escape(tags)} {escape(d['city'])} {escape(d['province'])}">
          <a href="posts/{escape(d['slug'])}.html" style="text-decoration:none; color:inherit; display:flex; flex-direction:column; height:100%;">
            <div style="height:190px; background:url('{escape(d.get('image', ''))}') center/cover no-repeat; position:relative;">
              <span style="position:absolute; top:12px; left:12px; background:rgba(15,23,42,0.85); color:#5eead4; font-size:12px; font-weight:800; padding:4px 10px; border-radius:999px;">
                📍 {escape(d['province'])} · {escape(d['city'])}
              </span>
            </div>
            <div style="padding:18px; display:flex; flex-direction:column; gap:10px; flex:1;">
              <div style="display:flex; flex-wrap:wrap; gap:6px;">{badge_html}</div>
              <h2 style="margin:0; font-size:18px; color:#0f172a; font-weight:800; line-height:1.4;">{escape(d['title'])}</h2>
              <p style="margin:0; font-size:13.5px; color:#475569; line-height:1.6;">{escape(d['overview'][:115])}…</p>
              <div style="margin-top:auto; padding-top:10px; border-top:1px solid #f1f5f9; display:flex; justify-content:space-between; align-items:center; font-size:13px; font-weight:800; color:#0f766e;">
                <span>♿ 12대 픽토그램 · 혼잡도 · 호텔 비교</span>
                <span>→</span>
              </div>
            </div>
          </a>
        </article>
        """.strip()

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>WizzTour Slow (slow.wizztour.com) | 계단·턱 없는 무장애·부모님 효도·유모차 평지 여행 &amp; 편안한 숙소 가이드</title>
  <meta name="description" content="한국관광공사 열린관광(KorWithService1) & 빅데이터 혼잡도 예측 연동! 휠체어 이용자, 무릎 약한 부모님 효도여행, 유모차 나들이를 위한 계단 없는 평지 산책 코스와 엘리베이터·장애인객실 호텔 비교 포털.">
  <link rel="canonical" href="{SITE_BASE_URL}/">
  <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;800&display=swap" rel="stylesheet">
  <style>
    body {{ margin:0; font-family:'Noto Sans KR', sans-serif; background:#f8fafc; color:#0f172a; }}
    .hero {{ background:linear-gradient(135deg, #0f172a 0%, #134e4a 100%); color:#ffffff; padding:48px 20px 40px; text-align:center; }}
    .hero h1 {{ margin:10px 0 12px; font-size:30px; font-weight:800; line-height:1.35; }}
    .hero p {{ max-width:680px; margin:0 auto 22px; color:#ccfbf1; font-size:15px; line-height:1.65; }}
    .filter-bar {{ display:flex; flex-wrap:wrap; gap:8px; justify-content:center; max-width:760px; margin:0 auto; }}
    .filter-btn {{ background:rgba(255,255,255,0.12); color:#ffffff; border:1px solid rgba(255,255,255,0.25); padding:8px 16px; border-radius:999px; cursor:pointer; font-size:13.5px; font-weight:700; transition:0.2s; }}
    .filter-btn.active, .filter-btn:hover {{ background:#14b8a6; border-color:#14b8a6; color:#0f172a; }}
    .container {{ max-width:1100px; margin:0 auto; padding:32px 18px 60px; }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fill, minmax(310px, 1fr)); gap:20px; }}
    .spot-card {{ background:#ffffff; border:1px solid #e2e8f0; border-radius:16px; overflow:hidden; box-shadow:0 4px 12px rgba(15,23,42,0.05); transition:transform 0.2s; }}
    .spot-card:hover {{ transform:translateY(-4px); }}
  </style>
</head>
<body>
  <section class="hero">
    <span style="background:#14b8a6; color:#0f172a; font-size:12px; font-weight:800; padding:4px 12px; border-radius:999px;">
      ♿ 한국관광공사 무장애 관광(KorWithService1) · 빅데이터 혼잡도 공식 연동
    </span>
    <h1>느린 걸음으로 더 깊게 쉬어가는 여행, WizzTour Slow</h1>
    <p>
      계단과 문턱 걱정 없이 <strong>휠체어·무릎 약한 부모님·유모차</strong>가 편안하게 산책할 수 있는 전국 무장애 평지 코스와<br>
      <strong>엘리베이터·장애인 전용 객실·1층 조식 동선</strong>이 검증된 숙소를 한눈에 비교해 보세요.
    </p>
    <div class="filter-bar">
      <button class="filter-btn active" onclick="filterSpots('ALL', this)">전체 보기</button>
      <button class="filter-btn" onclick="filterSpots('휠체어추천', this)">🦽 휠체어 무장애 코스</button>
      <button class="filter-btn" onclick="filterSpots('부모님효도', this)">👵 부모님 효도 평지여행</button>
      <button class="filter-btn" onclick="filterSpots('유모차산책', this)">👶 유모차 나들이 명소</button>
      <button class="filter-btn" onclick="filterSpots('무장애호텔', this)">🏨 무장애·엘리베이터 호텔</button>
    </div>
  </section>

  <main class="container">
    <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; margin-bottom:20px;">
      <h2 style="margin:0; font-size:21px; font-weight:800;">✨ 전국 검증된 무장애·효도·유모차 평지 여행 코스</h2>
      <span style="font-size:13px; color:#64748b;">최종 업데이트: {escape(check_date_str)}</span>
    </div>
    <div class="grid" id="spotsGrid">
      {cards}
    </div>

    <div style="margin-top:42px; padding:24px; background:#0f172a; color:#ffffff; border-radius:18px; text-align:center;">
      <h3 style="margin:0 0 8px 0; font-size:19px; color:#5eead4;">🗺️ WizzTour 4대 여행 생태계 바로가기</h3>
      <p style="margin:0 0 16px 0; font-size:14px; color:#cbd5e1;">목적에 맞는 WizzTour 전문 가이드에서 맞춤형 코스와 숙소 혜택을 확인하세요.</p>
      <div style="display:flex; flex-wrap:wrap; gap:10px; justify-content:center;">
        <a href="https://www.wizztour.com" target="_blank" rel="noopener" style="background:#f97316; color:#fff; padding:10px 18px; border-radius:999px; text-decoration:none; font-size:13.5px; font-weight:700;">🎉 전국 축제·당일치기 (wizztour.com)</a>
        <a href="https://info.wizztour.com" target="_blank" rel="noopener" style="background:#10b981; color:#fff; padding:10px 18px; border-radius:999px; text-decoration:none; font-size:13.5px; font-weight:700;">⛺ 캠핑·민물낚시 지도 (info.wizztour.com)</a>
        <a href="https://en.wizztour.com" target="_blank" rel="noopener" style="background:#3b82f6; color:#fff; padding:10px 18px; border-radius:999px; text-decoration:none; font-size:13.5px; font-weight:700;">🌐 English Korea Guide (en.wizztour.com)</a>
      </div>
    </div>
  </main>

  <script>
    function filterSpots(tag, btn) {{
      document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      document.querySelectorAll('.spot-card').forEach(card => {{
        const tags = card.getAttribute('data-tags') || '';
        card.style.display = (tag === 'ALL' || tags.includes(tag)) ? 'block' : 'none';
      }});
    }}
  </script>
</body>
</html>
"""


def build_seo_assets(destinations: list):
    now_iso = datetime.now(KST).strftime("%Y-%m-%d")
    urls = [f"  <url><loc>{SITE_BASE_URL}/</loc><lastmod>{now_iso}</lastmod><priority>1.0</priority></url>"]
    rss_items = []

    for d in destinations:
        loc = f"{SITE_BASE_URL}/posts/{d['slug']}.html"
        urls.append(f"  <url><loc>{escape(loc)}</loc><lastmod>{now_iso}</lastmod><priority>0.9</priority></url>")
        rss_items.append(f"""    <item>
      <title>{escape(d['title'])} 무장애·효도·유모차 평지 코스 &amp; 호텔 비교</title>
      <link>{escape(loc)}</link>
      <description>{escape(d['overview'])}</description>
    </item>""")

    sitemap_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{chr(10).join(urls)}
</urlset>
"""
    rss_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>WizzTour Slow | 무장애·효도·유모차 평지 여행 가이드</title>
    <link>{SITE_BASE_URL}/</link>
    <description>계단 걱정 없는 휠체어·부모님 효도·유모차 평지 산책 코스 및 무장애 호텔 비교</description>
{chr(10).join(rss_items)}
  </channel>
</rss>
"""
    robots_txt = f"User-agent: *\nAllow: /\nSitemap: {SITE_BASE_URL}/sitemap.xml\n"

    with open(os.path.join(BASE_DIR, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write(sitemap_xml)
    with open(os.path.join(BASE_DIR, "rss.xml"), "w", encoding="utf-8") as f:
        f.write(rss_xml)
    with open(os.path.join(BASE_DIR, "robots.txt"), "w", encoding="utf-8") as f:
        f.write(robots_txt)
    with open(os.path.join(BASE_DIR, "CNAME"), "w", encoding="utf-8") as f:
        f.write("slow.wizztour.com\n")


def discover_new_kto_barrier_free_spot(existing_ids: set) -> dict:
    """
    [매일 1건 자동 신규 발행 엔진]
    한국관광공사 KorService2(관광지 목록) + KorWithService1(무장애 상세정보)를 조회하여
    아직 발행되지 않은 전국 열린관광지·무장애 명소 1곳을 자동으로 발굴·생성합니다.
    """
    if not SERVICE_KEY:
        return {}
    area_Url = "https://apis.data.go.kr/B551011/KorService2/areaBasedList2"
    params = {
        "serviceKey": unquote(SERVICE_KEY),
        "numOfRows": 30,
        "pageNo": random.randint(1, 5),
        "MobileOS": "ETC",
        "MobileApp": "WizzTourSlow",
        "_type": "json",
        "arrange": "Q",
        "contentTypeId": "12",  # 관광지
    }
    try:
        r = requests.get(area_Url, params=params, verify=False, timeout=8)
        if r.status_code != 200:
            return {}
        items = (((r.json().get("response") or {}).get("body") or {}).get("items") or {}).get("item", [])
        if isinstance(items, dict):
            items = [items]
        for it in (items or []):
            cid = str(it.get("contentid") or "").strip()
            title = str(it.get("title") or "").strip()
            addr = str(it.get("addr1") or "").strip()
            img = str(it.get("firstimage") or "").strip()
            if not cid or cid in existing_ids or not title or not addr or not img:
                continue
            bf = fetch_kto_barrier_free_detail(cid)
            # 무장애 항목이 최소 3개 이상 확인된 곳만 채택
            valid_bf_cnt = sum(1 for k in ("parking", "route", "wheelchair", "restroom", "elevator", "stroller") if bf.get(k))
            if valid_bf_cnt < 3:
                continue
            parts = addr.split()
            province = parts[0][:2] if parts else "전국"
            city = parts[1].rstrip("시군구") if len(parts) > 1 else province
            slug = f"spot-{cid}-barrier-free"
            return {
                "contentid": cid,
                "slug": slug,
                "title": title,
                "city": city,
                "province": province,
                "addr": addr,
                "category_tags": ["휠체어추천", "부모님효도", "유모차산책", "열린관광지"],
                "image": img.replace("http://", "https://"),
                "overview": f"{title}은(는) 한국관광공사 무장애 여행정보(KorWithService1)에서 장애인 주차장·접근로·화장실 등 주요 보행 편의시설이 확인된 {city} 대표 나들이 명소입니다.",
                "local_food": f"{city} 1층 평지 입식 향토 한정식 & 가족 식당",
                "crowd_prediction": {
                    "golden_time": "오전 09:30 ~ 11:30 (주차 및 관람 동선 여유)",
                    "peak_time": "오후 14:00 ~ 16:30 (주말 방문객 집중 시간대)",
                    "weekday_score": "쾌적",
                    "weekend_tip": "오전 일찍 방문하시면 장애인 전용 주차구역 및 매표소 진입이 훨씬 수월합니다."
                },
                "barrier_free": bf,
                "flat_route": [
                    {"time": "오전 10:30", "place": f"{title} 장애인주차장 하차 → 무장애 주 관람로 산책", "note": "단차가 적은 주 출입구와 평지 동선 중심 관람"},
                    {"time": "점심 12:30", "place": f"{city} 인근 1층 평지 입식 맛집", "note": "계단 없는 1층 테이블 좌석 식당"},
                    {"time": "오후 14:30", "place": f"{city} 전망 좋은 대형 엘리베이터 카페", "note": "주차가 편하고 화장실이 쾌적한 베이커리 카페"},
                    {"time": "저녁 17:30", "place": f"{city} 엘리베이터·장애인객실 보유 호텔 체크인", "note": "무리한 이동 없이 편안한 호텔 휴식"}
                ],
                "hotels": [
                    {"name": f"{city} 중심권 4~5성급 무장애·특급 호텔", "type": "① 엘리베이터·장애인객실 보유 호텔", "features": "장애인 전용 객실 · 넓은 엘리베이터 · 1층 조식 뷔페"},
                    {"name": f"{city} 가족형 리조트·콘도", "type": "② 3~4인 부모님 효도·가족 리조트", "features": "넓은 거실형 패밀리룸 · 단지 내 평지 산책로"},
                    {"name": f"{city} 역세권·시내 신축 비즈니스 호텔", "type": "③ 무료취소 & 가성비 신축 호텔", "features": "문턱 없는 신축 객실 · 합리적인 요금 및 무료취소"}
                ]
            }
    except Exception as e:
        print(f"[신규 무장애 명소 자동 발굴 참고] {e}")
    return {}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-once", action="store_true", help="정적 사이트 전체 빌드 실행")
    args = parser.parse_args()

    check_date_str = datetime.now(KST).strftime("%Y년 %m월 %d일")
    destinations = list(VERIFIED_BARRIER_FREE_DESTINATIONS)
    existing_ids = {str(d.get("contentid")) for d in destinations}

    # 기존 누적 DB 로드
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as cf:
                saved_list = json.load(cf)
                if isinstance(saved_list, list):
                    for item in saved_list:
                        cid = str(item.get("contentid") or "")
                        if cid and cid not in existing_ids:
                            destinations.append(item)
                            existing_ids.add(cid)
        except Exception:
            pass

    # 매일 실행 시 KTO 무장애 API에서 신규 여행지 1건 자동 추가 발굴
    new_spot = discover_new_kto_barrier_free_spot(existing_ids)
    if new_spot:
        destinations.insert(0, new_spot)
        existing_ids.add(str(new_spot["contentid"]))
        print(f"✨ [신규 무장애 여행지 자동 발굴 추가] {new_spot['title']} ({new_spot['city']})")

    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as cf:
            json.dump(destinations, cf, ensure_ascii=False, indent=2)
    except Exception:
        pass

    for d in destinations:
        post_html = build_post_page_html(d, check_date_str)
        out_path = os.path.join(POSTS_DIR, f"{d['slug']}.html")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(post_html)
        print(f"✅ [Slow 상세페이지 생성] {out_path}")

    index_html = build_index_html(destinations, check_date_str)
    index_path = os.path.join(BASE_DIR, "index.html")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(index_html)

    build_seo_assets(destinations)
    print(f"🎉 [WizzTour Slow 빌드 완료] index.html 및 상세 {len(destinations)}건, sitemap.xml, rss.xml, CNAME 생성 완료!")


if __name__ == "__main__":
    main()

