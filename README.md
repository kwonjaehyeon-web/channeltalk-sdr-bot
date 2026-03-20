# 채널톡 SDR 고객 분석 자동화 봇

> **"기업명 하나로 SDR 리서치 끝"**
> Slack에서 기업명을 입력하면 AI가 자동으로 ICP 분석 → 페인포인트 도출 → 채널톡 솔루션 매칭 → Notion DB 저장까지 처리합니다.

<br>

## 왜 만들었나

B2B SDR은 콜/메일 전 기업 리서치에 평균 30~60분을 쓴다.
홈페이지, 뉴스, 채용공고, 링크드인을 각각 열어보고 손으로 정리하는 과정을 자동화하고 싶었다.
특히 **채널톡** SDR 관점에서 "이 회사에 챗봇/CRM/팀채팅 중 뭐가 맞는지"를 바로 판단할 수 있는 도구가 필요했다.

<br>

## 데모

```
/회사 무신사
```

**Slack 출력:**

```
📊 무신사 SDR 분석 리포트
────────────────────────────
🎯 ICP 분석
• 산업: 커머스 - 패션/스트릿
• 규모/매출: 연매출 약 4,000억, 임직원 1,000명+
• 적합도: 🟢 High — 급성장 커머스 플랫폼으로 CS 자동화 수요 높음

🔥 회사의 문제 (Problem)
CS 인력 대규모 채용 중 + 고객문의 폭증 예상
근거: "CS 매니저 00명 채용" JD 다수 확인

💬 채널톡 솔루션 매칭
서포트봇으로 단순 문의 70% 자동화 제안.
CRM 마케팅으로 구매 이력 기반 재구매 캠페인 연동 가능.

👤 의사결정자
CX팀장 또는 마케팅 본부장
이유: 커머스 규모에서 CS/마케팅 양쪽 모두 채널톡 도입 주도 가능
📎 Notion에서 보기
```

<br>

## 아키텍처

```
Slack /회사 커맨드
        │
        ▼
  [Serper API]  ← Google 검색 (뉴스 + 채용공고 + 기업개요)
        │
        ▼
  [GPT-4o]  ← 채널톡 SDR 특화 프롬프트
        │
   ┌────┴────┐
   ▼         ▼
[Slack]   [Notion DB]
간결 리포트  영구 저장
```

**데이터 수집**: Serper API로 구글 검색 3종 (최신 뉴스 / 채용공고 / 기업개요)
**분석**: GPT-4o가 검색 결과를 읽고 ICP·Problem·Solution·의사결정자 판단
**출력**: Slack Block Kit 리포트 + Notion DB 자동 저장

<br>

## 분석 항목

| 항목 | 분석 소스 | LLM 판단 기준 |
|---|---|---|
| ICP: 산업 | 기업 개요 검색 | 커머스/SaaS/오프라인 서비스 등 분류 |
| ICP: 규모/매출 | 뉴스, 기업 정보 | "Series B 100억 투자유치" → 성장기 스타트업 |
| 회사의 문제 | 채용 공고(JD) | "CS 인력 대규모 채용" → 고객 문의 폭증 |
| 채널톡 솔루션 | 매칭 로직 | CS 폭주 → 서포트봇 / 마케팅팀 채용 → CRM |
| 의사결정자 | 산업·규모 추론 | 커머스 → CX팀장 / SaaS → CS 리드 |

<br>

## 기술 스택

| 역할 | 기술 |
|---|---|
| 인터페이스 | Slack Bolt (Socket Mode) |
| 웹 프레임워크 | FastAPI |
| 검색 | Serper API (Google Search) |
| LLM | OpenAI GPT-4o |
| 저장 | Notion API |
| 언어 | Python 3.11+ |

<br>

## 실행 방법

### 1. 환경변수 설정

```bash
cp .env.example .env
```

```env
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
SLACK_SIGNING_SECRET=...
OPENAI_API_KEY=sk-...
SERPER_API_KEY=...
NOTION_TOKEN=ntn_...
NOTION_DATABASE_ID=...
```

### 2. 패키지 설치

```bash
pip install -r requirements.txt
```

### 3. 봇 실행

```bash
python app.py
```

### 4. Slack에서 사용

```
/회사 기업명
```

<br>

## Notion DB 구조

자동 저장되는 항목:

| 컬럼 | 내용 |
|---|---|
| 기업명 | 분석 대상 |
| 산업 | ICP 산업군 |
| 규모/매출 | 추정 규모 |
| ICP 적합도 | High / Medium / Low |
| 문제 (Problem) | 도출된 페인포인트 |
| 채널톡 솔루션 | 기능 매칭 결과 |
| 의사결정자 | 추론된 직함 |
| 분석일시 | 자동 기록 |

<br>

## 프로젝트 구조

```
sales-strategy/
├── app.py                      # Slack Socket Mode 진입점
├── app/
│   ├── main.py                 # FastAPI 서버
│   ├── models/schema.py        # 데이터 모델
│   ├── routes/slack.py         # Slack 커맨드 처리 + Block Kit 리포트
│   └── services/
│       ├── serper.py           # Serper API (구글 검색)
│       ├── llm.py              # GPT-4o 분석 (채널톡 SDR 특화 프롬프트)
│       └── notion.py           # Notion DB 저장
└── requirements.txt
```

<br>

## 배운 점 / 한계

**잘 된 것**
- 채용공고에서 페인포인트를 추론하는 로직이 생각보다 정확하게 동작함
- GPT-4o가 산업별 의사결정자 구조를 꽤 잘 맞춤 (커머스 CX팀장, SaaS CS 리드 등)

**한계 및 개선 방향**
- 비상장 소기업은 검색 결과가 적어 분석 품질 낮음
- Serper snippet만으로는 정보 깊이가 얕음 → 추후 실제 페이지 크롤링 고려
- 의사결정자 직접 확인(링크드인 등) 기능 미구현
