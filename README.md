# 🐢 WizzTour Slow (`slow.wizztour.com`)

**계단·문턱 걱정 없이 천천히 걷는 무장애(휠체어)·부모님 효도여행·유모차 평지 나들이 & 편안한 숙소 비교 포털**

## 1. 프로젝트 개요
- **도메인**: `https://slow.wizztour.com` (GitHub + Cloudflare Pages 정적 배포)
- **연동 공공데이터포털(`data.go.kr`) 승인 API**:
  1. `한국관광공사_무장애 여행 정보` (`KorWithService1`) — 12대 무장애 편의시설 픽토그램 성적표
  2. `한국관광공사_관광지 집중률 방문자 추이 예측 정보` (`TatsCnctrRateService`) & `빅데이터_지역별 방문자수_GW` — 덜 붐비는 시간대(골든타임) 안내
  3. `한국관광공사_관광지 오디오 가이드정보_GW` (`Odii`) — 음성 스토리텔링
  4. `한국관광공사_관광음식 정보 서비스` — 1층 무경사 입식 보양식 맛집 매칭
- **수익화 프레임워크**: `판매 상위 1%의 노하우.docx` 6단계 고전환 설계 (엘리베이터·장애인객실·1층 조식·무료취소 조건 비교표 + 문맥형 3단계 Trip.com CTA)

## 2. 로컬 실행 및 빌드 방법
```bash
python slow_wizztour_bot.py --build-once
```
실행 시 `index.html`, `posts/*.html`, `sitemap.xml`, `rss.xml`, `robots.txt`, `CNAME` 파일이 즉시 생성됩니다.

